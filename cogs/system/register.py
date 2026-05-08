"""
Register System with Discord Components V2
Sistema completo de registro com componentes UI modernos
"""

import discord
from discord import app_commands
from discord.ext import commands
import traceback
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

from pool.redis import redis_pool
from pool.connection import mongo_pool


# =========================
# LOG SYSTEM
# =========================

def log(tag: str, msg: str):
    """Log informativo"""
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}][Register:{tag}] {msg}")

def err(tag: str, e: Exception):
    """Log de erro com traceback"""
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}][Register:{tag}:ERROR] {repr(e)}")
    traceback.print_exc()


# =========================
# COMPONENTS V2 HELPERS
# =========================

def create_media_gallery(urls: List[str]) -> Optional[discord.ui.MediaGallery]:
    """Cria Media Gallery de forma compatível com diferentes versões"""
    try:
        if not urls:
            return None
        
        # Verificar se a classe existe (discord.py 2.0+)
        if hasattr(discord, 'MediaGallery') and hasattr(discord, 'MediaGalleryItem'):
            items = [discord.MediaGalleryItem(media=url) for url in urls if url]
            if items:
                return discord.ui.MediaGallery(items=items)
        
        log("MEDIA", "MediaGallery não disponível nesta versão do discord.py")
        return None
    except Exception as e:
        log("MEDIA", f"Erro ao criar MediaGallery: {e}")
        return None


def create_text_only_view(content: str) -> discord.ui.View:
    """Cria view simples apenas com texto em embed"""
    embed = discord.Embed(
        description=content,
        color=discord.Color.blue()
    )
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="✅ OK", style=discord.ButtonStyle.green, disabled=True))
    
    # Criar uma mensagem com embed
    class TextView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
            self.embed = embed
    
    return TextView()


def create_embed(title: str, description: str, color: int = 0x5865F2, 
                 fields: List[tuple] = None, thumbnail: str = None) -> discord.Embed:
    """Cria embed formatado"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow()
    )
    
    if fields:
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
    
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    
    embed.set_footer(text="Nexus Register System")
    return embed


# =========================
# DB SAFE OPERATIONS
# =========================

def col():
    """Retorna coleção do MongoDB"""
    return mongo_pool.get_collection("guild_config")

def key(gid: int) -> str:
    """Chave Redis para configuração do servidor"""
    return f"guild:{gid}:config"

def get_config(gid: int) -> Dict[str, Any]:
    """Obtém configuração do servidor com cache Redis"""
    try:
        # Tentar cache do Redis primeiro
        cached = redis_pool.get(key(gid))
        if cached:
            if isinstance(cached, str):
                return json.loads(cached)
            return cached or {}

        # Buscar no MongoDB
        doc = col().find_one({"guild_id": int(gid)}) or {}
        doc.pop("_id", None)
        
        # Cache por 5 minutos
        redis_pool.set(key(gid), doc, ex=300)
        return doc

    except Exception as e:
        err("DB", e)
        return {}

def save_config(gid: int, data: dict):
    """Salva configuração do servidor"""
    try:
        data = dict(data)
        data.pop("_id", None)
        col().update_one({"guild_id": int(gid)}, {"$set": data}, upsert=True)
        redis_pool.set(key(gid), data, ex=300)
        log("DB", f"Config salva para guild {gid}")
    except Exception as e:
        err("DB", e)

def increment_register_count(guild_id: int, user_id: int) -> int:
    """Incrementa contador de registros e retorna total"""
    try:
        redis_key = f"guild:{guild_id}:register_count"
        users_key = f"guild:{guild_id}:registered_users"
        
        # Incrementar contador
        total = redis_pool.incr(redis_key)
        redis_pool.expire(redis_key, 86400)  # Expira em 24h
        
        # Adicionar ao set de usuários únicos
        redis_pool.sadd(users_key, str(user_id))
        redis_pool.expire(users_key, 86400)
        
        return total
    except Exception as e:
        err("DB", e)
        return 0

def get_register_stats(guild_id: int) -> tuple:
    """Retorna (total_registros, total_unicos)"""
    try:
        total = redis_pool.get(f"guild:{guild_id}:register_count") or 0
        unique = redis_pool.scard(f"guild:{guild_id}:registered_users") or 0
        
        return int(total), int(unique)
    except Exception as e:
        err("DB", e)
        return 0, 0


# =========================
# MODAL DE REGISTRO
# =========================

class RegisterModal(discord.ui.Modal):
    """Modal para registro de novos membros"""
    
    def __init__(self, guild_id: int):
        super().__init__(title="🎉 Registro de Novo Membro")
        self.guild_id = guild_id
        
        # Campo de nome
        self.nome = discord.ui.TextInput(
            label="Como prefere ser chamado?",
            placeholder="Ex: João, John, etc...",
            required=True,
            max_length=50,
            style=discord.TextStyle.short
        )
        self.add_item(self.nome)
        
        # Campo de apresentação
        self.apresentacao = discord.ui.TextInput(
            label="Faça uma breve apresentação",
            placeholder="Conte um pouco sobre você...",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.apresentacao)
        
        # Campo de como conheceu
        self.como_conheceu = discord.ui.TextInput(
            label="Como conheceu o servidor?",
            placeholder="Discord, amigo, divulgação...",
            required=False,
            max_length=200,
            style=discord.TextStyle.short
        )
        self.add_item(self.como_conheceu)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Processa o registro"""
        try:
            guild = interaction.guild
            if not guild or guild.id != self.guild_id:
                return await interaction.response.send_message(
                    "❌ Modal inválido para este servidor.",
                    ephemeral=True
                )
            
            member = interaction.user
            config = get_config(self.guild_id)
            
            log("MODAL", f"Registro de {member} em {self.guild_id}")
            
            # Remover cargo não verificado
            if unverified_role_id := config.get("unverified_role"):
                role = guild.get_role(int(unverified_role_id))
                if role and role in member.roles:
                    await member.remove_roles(role, reason="Sistema de Registro")
            
            # Adicionar cargo verificado
            if verified_role_id := config.get("verified_role"):
                role = guild.get_role(int(verified_role_id))
                if role and role not in member.roles:
                    await member.add_roles(role, reason="Sistema de Registro")
            
            # Definir nickname
            if config.get("set_nickname", True):
                try:
                    await member.edit(nick=self.nome.value[:32])
                except discord.Forbidden:
                    log("NICK", "Sem permissão para mudar nickname")
                except:
                    pass
            
            # Atualizar estatísticas
            total, unique = get_register_stats(self.guild_id)
            current_total = increment_register_count(self.guild_id, member.id)
            
            # Criar embed de boas-vindas
            welcome_embed = create_embed(
                title=f"🎉 Bem-vindo(a) ao servidor, {self.nome.value}!",
                description=f"Seu registro foi concluído com sucesso!",
                color=0x57F287,
                fields=[
                    ("📝 Apresentação", self.apresentacao.value or "Não informada", False),
                    ("📢 Como conheceu", self.como_conheceu.value or "Não informado", False),
                    ("📊 Estatísticas", f"Você é o {current_total}º membro a se registrar!\nTotal únicos: {unique}", False)
                ],
                thumbnail=member.display_avatar.url
            )
            
            # Enviar para canal de boas-vindas
            if welcome_channel_id := config.get("welcome_channel"):
                channel = guild.get_channel(int(welcome_channel_id))
                if channel:
                    await channel.send(embed=welcome_embed)
            
            # Resposta para o usuário
            await interaction.response.send_message(
                embed=create_embed(
                    "✅ Registro Concluído!",
                    f"Bem-vindo(a) ao servidor, {self.nome.value}!\nAgora você tem acesso a todos os canais.",
                    0x57F287
                ),
                ephemeral=True
            )
            
            # Log em canal específico
            if log_channel_id := config.get("log_channel"):
                channel = guild.get_channel(int(log_channel_id))
                if channel:
                    log_embed = create_embed(
                        "🟢 NOVO REGISTRO",
                        f"{member.mention} se registrou no servidor",
                        0x57F287,
                        fields=[
                            ("👤 Usuário", f"{member} ({member.id})", True),
                            ("📝 Nome registrado", self.nome.value, True),
                            ("📍 Apresentação", self.apresentacao.value or "Não informada", False),
                            ("📢 Como conheceu", self.como_conheceu.value or "Não informado", False),
                            ("📊 Total de registros", str(current_total), True)
                        ],
                        thumbnail=member.display_avatar.url
                    )
                    await channel.send(embed=log_embed)
            
        except Exception as e:
            err("MODAL", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Erro ao processar registro. Contate um administrador.",
                    ephemeral=True
                )


# =========================
# BOTÕES
# =========================

class RegisterButton(discord.ui.Button):
    """Botão de registro"""
    
    def __init__(self, guild_id: int):
        super().__init__(
            label="Registrar-se",
            style=discord.ButtonStyle.green,
            emoji="✅",
            custom_id=f"register:{guild_id}",
            row=0
        )
        self.guild_id = guild_id
    
    async def callback(self, interaction: discord.Interaction):
        """Abre modal de registro"""
        try:
            if not interaction.guild or interaction.guild.id != self.guild_id:
                return await interaction.response.send_message(
                    "❌ Botão inválido para este servidor.",
                    ephemeral=True
                )
            
            # Verificar se já está registrado
            config = get_config(self.guild_id)
            if verified_role_id := config.get("verified_role"):
                role = interaction.guild.get_role(int(verified_role_id))
                if role and role in interaction.user.roles:
                    return await interaction.response.send_message(
                        "⚠️ Você já está registrado neste servidor!",
                        ephemeral=True
                    )
            
            # Abrir modal
            modal = RegisterModal(self.guild_id)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            err("BUTTON", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Erro ao iniciar registro.",
                    ephemeral=True
                )


class StatsButton(discord.ui.Button):
    """Botão de estatísticas"""
    
    def __init__(self, guild_id: int):
        super().__init__(
            label="Estatísticas",
            style=discord.ButtonStyle.secondary,
            emoji="📊",
            custom_id=f"stats:{guild_id}",
            row=0
        )
        self.guild_id = guild_id
    
    async def callback(self, interaction: discord.Interaction):
        """Mostra estatísticas"""
        try:
            if not interaction.guild or interaction.guild.id != self.guild_id:
                return await interaction.response.send_message(
                    "❌ Botão inválido para este servidor.",
                    ephemeral=True
                )
            
            total, unique = get_register_stats(self.guild_id)
            guild = interaction.guild
            
            taxa = (total / guild.member_count * 100) if guild.member_count > 0 else 0
            
            embed = create_embed(
                f"📊 Estatísticas do {guild.name}",
                f"**✅ Registrados:** {total}\n"
                f"**👥 Total Membros:** {guild.member_count}\n"
                f"**📈 Taxa de Registro:** {taxa:.1f}%\n"
                f"**🆔 Servidor ID:** {guild.id}",
                0x5865F2,
                thumbnail=guild.icon.url if guild.icon else None
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            err("STATS", e)
            await interaction.response.send_message(
                "❌ Erro ao carregar estatísticas.",
                ephemeral=True
            )


# =========================
# VIEW DO PAINEL
# =========================

class RegisterPanelView(discord.ui.View):
    """View persistente do painel de registro"""
    
    def __init__(self, guild: discord.Guild, config: dict):
        super().__init__(timeout=None)
        self.guild_id = guild.id
        
        # Adicionar botões
        self.add_item(RegisterButton(guild.id))
        self.add_item(StatsButton(guild.id))


# =========================
# COG PRINCIPAL
# =========================

class RegisterSystem(commands.Cog):
    """Sistema de registro com componentes modernos"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log("INIT", "RegisterSystem carregado")

    # ========================
    # COMANDOS DE CONFIGURAÇÃO
    # ========================
    
    @app_commands.command(name="reg_config", description="Configurar sistema de registro")
    @app_commands.default_permissions(administrator=True)
    async def reg_config(
        self,
        interaction: discord.Interaction,
        verified_role: Optional[discord.Role] = None,
        unverified_role: Optional[discord.Role] = None,
        welcome_channel: Optional[discord.TextChannel] = None,
        log_channel: Optional[discord.TextChannel] = None,
        welcome_message: Optional[str] = None,
        set_nickname: Optional[bool] = None,
        banner_url: Optional[str] = None
    ):
        """Configura o sistema de registro do servidor"""
        
        if not interaction.guild:
            return await interaction.response.send_message(
                "❌ Use este comando dentro de um servidor.",
                ephemeral=True
            )
        
        try:
            config = get_config(interaction.guild.id)
            
            # Atualizar configurações
            if verified_role:
                config["verified_role"] = str(verified_role.id)
            if unverified_role:
                config["unverified_role"] = str(unverified_role.id)
            if welcome_channel:
                config["welcome_channel"] = str(welcome_channel.id)
            if log_channel:
                config["log_channel"] = str(log_channel.id)
            if welcome_message:
                config["welcome_message"] = welcome_message[:1000]
            if set_nickname is not None:
                config["set_nickname"] = set_nickname
            if banner_url:
                config["banner_url"] = banner_url
            
            save_config(interaction.guild.id, config)
            
            # Criar embed de confirmação
            fields = []
            if verified_role:
                fields.append(("✅ Cargo Verificado", verified_role.mention))
            if unverified_role:
                fields.append(("❌ Cargo Não Verificado", unverified_role.mention))
            if welcome_channel:
                fields.append(("📢 Canal de Boas-Vindas", welcome_channel.mention))
            if log_channel:
                fields.append(("📝 Canal de Logs", log_channel.mention))
            if set_nickname is not None:
                fields.append(("✏️ Definir Nickname", "✅ Ativado" if set_nickname else "❌ Desativado"))
            if banner_url:
                fields.append(("🖼️ Banner", f"[Clique aqui]({banner_url})"))
            
            embed = create_embed(
                "✅ Configuração Salva!",
                "As configurações do sistema de registro foram atualizadas.",
                0x57F287,
                fields
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            err("CONFIG", e)
            await interaction.response.send_message(
                "❌ Erro ao salvar configuração.",
                ephemeral=True
            )
    
    # ========================
    # COMANDOS DO PAINEL
    # ========================
    
    @app_commands.command(name="post_register_panel", description="Postar painel de registro")
    @app_commands.default_permissions(administrator=True)
    async def post_panel(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel,
        with_stats: bool = True
    ):
        """Posta o painel de registro em um canal"""
        
        try:
            if not interaction.guild:
                return await interaction.response.send_message(
                    "❌ Use este comando dentro de um servidor.",
                    ephemeral=True
                )
            
            config = get_config(interaction.guild.id)
            
            if not config.get("verified_role"):
                return await interaction.response.send_message(
                    "⚠️ Configure os cargos primeiro!\n"
                    "Use `/reg_config` para configurar o sistema.",
                    ephemeral=True
                )
            
            # Criar embed principal
            embed = create_embed(
                f"🎮 Bem-vindo(a) ao {interaction.guild.name}!",
                "Para ter acesso completo aos canais, realize seu registro clicando no botão abaixo.\n\n"
                "**✨ Benefícios do Registro:**\n"
                "• Acesso a todos os canais\n"
                "• Participar de eventos exclusivos\n"
                "• Ganhar cargos especiais\n"
                "• Receber notificações importantes",
                0x5865F2,
                thumbnail=interaction.guild.icon.url if interaction.guild.icon else None
            )
            
            # Adicionar regras se existirem
            if config.get("welcome_message"):
                embed.add_field(
                    name="📜 Regras e Informações",
                    value=config["welcome_message"][:1024],
                    inline=False
                )
            
            # Criar view com botões
            view = RegisterPanelView(interaction.guild, config)
            
            # Enviar mensagem
            await channel.send(embed=embed, view=view)
            
            # Enviar estatísticas se solicitado
            if with_stats:
                total, unique = get_register_stats(interaction.guild.id)
                stats_embed = create_embed(
                    "📊 Estatísticas Atuais",
                    f"**✅ Registrados:** {total}\n"
                    f"**👥 Total Membros:** {interaction.guild.member_count}\n"
                    f"**📈 Taxa de Registro:** {(total / interaction.guild.member_count * 100):.1f}%\n"
                    f"**🆔 Servidor ID:** {interaction.guild.id}",
                    0x5865F2
                )
                await channel.send(embed=stats_embed)
            
            await interaction.response.send_message(
                f"✅ Painel de registro enviado em {channel.mention}!",
                ephemeral=True
            )
            
        except Exception as e:
            err("POST_PANEL", e)
            await interaction.response.send_message(
                f"❌ Erro ao enviar o painel: {str(e)[:100]}",
                ephemeral=True
            )
    
    # ========================
    # COMANDO DE ESTATÍSTICAS
    # ========================
    
    @app_commands.command(name="reg_stats", description="Ver estatísticas do sistema de registro")
    async def reg_stats(self, interaction: discord.Interaction):
        """Mostra estatísticas de registro do servidor"""
        
        try:
            if not interaction.guild:
                return await interaction.response.send_message(
                    "❌ Use este comando dentro de um servidor.",
                    ephemeral=True
                )
            
            total, unique = get_register_stats(interaction.guild.id)
            
            embed = create_embed(
                f"📊 Estatísticas - {interaction.guild.name}",
                f"**✅ Total de Registros:** {total}\n"
                f"**👥 Usuários Únicos:** {unique}\n"
                f"**📈 Taxa de Registro:** {(total / interaction.guild.member_count * 100):.1f}%\n"
                f"**🆔 Servidor ID:** {interaction.guild.id}",
                0x5865F2,
                thumbnail=interaction.guild.icon.url if interaction.guild.icon else None
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            err("STATS", e)
            await interaction.response.send_message(
                "❌ Erro ao carregar estatísticas.",
                ephemeral=True
            )
    
    # ========================
    # COMANDO DE PREVIEW
    # ========================
    
    @app_commands.command(name="preview_panel", description="Preview do painel de registro")
    @app_commands.default_permissions(administrator=True)
    async def preview_panel(self, interaction: discord.Interaction):
        """Mostra preview do painel de registro"""
        
        try:
            if not interaction.guild:
                return await interaction.response.send_message(
                    "❌ Use este comando dentro de um servidor.",
                    ephemeral=True
                )
            
            config = get_config(interaction.guild.id)
            
            embed = create_embed(
                f"🎮 Preview - {interaction.guild.name}",
                "**✨ Benefícios do Registro:**\n"
                "• Acesso a todos os canais\n"
                "• Participar de eventos exclusivos\n"
                "• Ganhar cargos especiais\n"
                "• Receber notificações importantes",
                0x5865F2
            )
            
            # Adicionar configurações atuais
            config_text = "**⚙️ Configurações Atuais:**\n"
            if config.get("verified_role"):
                config_text += f"✅ Verificado: <@&{config['verified_role']}>\n"
            if config.get("unverified_role"):
                config_text += f"❌ Não verificado: <@&{config['unverified_role']}>\n"
            if config.get("welcome_channel"):
                config_text += f"📢 Boas-vindas: <#{config['welcome_channel']}>\n"
            if config.get("log_channel"):
                config_text += f"📝 Logs: <#{config['log_channel']}>\n"
            config_text += f"✏️ Nickname: {'✅' if config.get('set_nickname', True) else '❌'}"
            
            embed.add_field(name="⚙️ Configurações", value=config_text, inline=False)
            
            if config.get("welcome_message"):
                embed.add_field(name="📜 Mensagem de Boas-Vindas", value=config["welcome_message"][:1024], inline=False)
            
            view = RegisterPanelView(interaction.guild, config)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            err("PREVIEW", e)
            await interaction.response.send_message(
                f"❌ Erro ao mostrar preview: {str(e)[:100]}",
                ephemeral=True
            )


# =========================
# SETUP
# =========================

async def setup(bot: commands.Bot):
    """Setup do cog"""
    await bot.add_cog(RegisterSystem(bot))
    log("SETUP", "✅ RegisterSystem carregado com sucesso!")