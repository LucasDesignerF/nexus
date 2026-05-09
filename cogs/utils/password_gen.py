"""
Temporary Password Generator - Discord Components V2
Sistema de geração de senhas temporárias seguras
Com histórico e opções personalizáveis
"""

import discord
from discord.ext import commands
import secrets
import string
import json
from datetime import datetime, timedelta
import traceback
import logging
from typing import Optional, List, Dict, Any, Tuple

from pool.redis import redis_pool


# =========================
# CONFIGURAÇÃO DE LOGGING
# =========================

logger = logging.getLogger('PasswordGen')
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(handler)


# =========================
# CONFIGURAÇÃO
# =========================

SESSION_DURATION = 3600  # 1 hora para histórico
MAX_HISTORY = 10  # Máximo de senhas no histórico


# =========================
# LOG
# =========================

def log(tag: str, msg: str):
    logger.info(f"[{tag}] {msg}")

def err(tag: str, e: Exception):
    logger.error(f"[{tag}] {repr(e)}")
    traceback.print_exc()


# =========================
# REDIS OPERATIONS (versão compatível)
# =========================

def get_history_key(user_id: int) -> str:
    return f"password_history:{user_id}"

def save_password_history(user_id: int, password: str, strength: str):
    """Salva senha no histórico do usuário"""
    try:
        key = get_history_key(user_id)
        
        # Buscar histórico existente
        existing = redis_pool.get(key)
        history = []
        
        if existing:
            try:
                if isinstance(existing, str):
                    history = json.loads(existing)
                elif isinstance(existing, list):
                    history = existing
                elif isinstance(existing, dict):
                    history = [existing]
            except Exception as e:
                log("REDIS_PARSE", f"Erro ao parsear: {e}")
                history = []
        
        # Garantir que é uma lista
        if not isinstance(history, list):
            history = []
        
        # Adicionar nova senha no início
        new_entry = {
            'password': password,
            'strength': strength,
            'created_at': datetime.utcnow().isoformat()
        }
        history.insert(0, new_entry)
        
        # Manter apenas MAX_HISTORY itens
        history = history[:MAX_HISTORY]
        
        # Salvar de volta como JSON string
        redis_pool.set(key, json.dumps(history, ensure_ascii=False), ex=SESSION_DURATION)
        log("REDIS", f"✅ Senha salva para user {user_id} - Total: {len(history)}")
        
        # Debug: verificar se salvou
        test = redis_pool.get(key)
        if test:
            log("REDIS", f"✅ Verificação: histórico salvo com sucesso")
        else:
            log("REDIS", f"⚠️ Falha na verificação do histórico")
            
    except Exception as e:
        err("REDIS_SAVE", e)

def get_password_history(user_id: int) -> List[Dict]:
    """Obtém histórico de senhas do usuário"""
    try:
        key = get_history_key(user_id)
        data = redis_pool.get(key)
        
        log("REDIS", f"Buscando histórico para user {user_id} - Dados: {data is not None}")
        
        if data:
            if isinstance(data, str):
                result = json.loads(data)
                log("REDIS", f"✅ Histórico encontrado: {len(result)} senhas")
                return result
            elif isinstance(data, list):
                log("REDIS", f"✅ Histórico encontrado (lista): {len(data)} senhas")
                return data
            elif isinstance(data, dict):
                log("REDIS", f"✅ Histórico encontrado (dict): 1 senha")
                return [data]
        else:
            log("REDIS", f"📭 Nenhum histórico encontrado para user {user_id}")
        return []
    except Exception as e:
        err("REDIS_GET", e)
        return []

def clear_password_history(user_id: int):
    """Limpa histórico de senhas"""
    try:
        redis_pool.delete(get_history_key(user_id))
        log("REDIS", f"🗑️ Histórico limpo para user {user_id}")
    except Exception as e:
        err("REDIS_CLEAR", e)


# =========================
# GERADOR DE SENHAS
# =========================

class PasswordGenerator:
    """Gerador de senhas seguras"""
    
    @staticmethod
    def generate_standard(length: int = 16) -> Tuple[str, str]:
        characters = string.ascii_letters + string.digits + "!@#$%&*+-=?"
        password = ''.join(secrets.choice(characters) for _ in range(length))
        return password, "Forte"
    
    @staticmethod
    def generate_numeric(length: int = 8) -> Tuple[str, str]:
        password = ''.join(secrets.choice(string.digits) for _ in range(length))
        return password, "Média"
    
    @staticmethod
    def generate_alphanumeric(length: int = 12) -> Tuple[str, str]:
        characters = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(characters) for _ in range(length))
        return password, "Forte"
    
    @staticmethod
    def generate_memorable() -> Tuple[str, str]:
        palavras = ["Cafe", "Sol", "Lua", "Estrela", "Fogo", "Agua", "Terra", "Ar",
                    "Vento", "Mar", "Rio", "Montanha", "Vale", "Floresta", "Deserto",
                    "Tigre", "Leao", "Lobo", "Fenix", "Dragao", "Falcao", "Águia"]
        simbolos = "!@#$%&"
        palavra = secrets.choice(palavras)
        numero = secrets.randbelow(999)
        simbolo = secrets.choice(simbolos)
        password = f"{palavra}{numero}{simbolo}"
        return password, "Forte"
    
    @staticmethod
    def generate_secure(length: int = 24) -> Tuple[str, str]:
        characters = string.ascii_letters + string.digits + "!@#$%&*+-=?"
        password = ''.join(secrets.choice(characters) for _ in range(length))
        return password, "Muito Forte"


# =========================
# UTILS HELPERS V2
# =========================

def create_text_only_view(content: str) -> discord.ui.LayoutView:
    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay(content=content))
    view = discord.ui.LayoutView()
    view.add_item(container)
    return view


# =========================
# VIEW DE VISUALIZAÇÃO DA SENHA GERADA
# =========================

class SenhaGeradaView(discord.ui.LayoutView):
    def __init__(self, password: str, strength: str, user_id: int, tipo: str):
        super().__init__(timeout=120)
        self.password = password
        self.strength = strength
        self.user_id = user_id
        self.tipo = tipo
        self.build_container()
    
    def build_container(self):
        container = discord.ui.Container()
        colors = {"Muito Forte": 0x57F287, "Forte": 0x57F287, "Média": 0xFEE75C, "Fraca": 0xED4245}
        container.accent = colors.get(self.strength, 0x5865F2)
        
        container.add_item(discord.ui.TextDisplay(content="# 🔐 SENHA GERADA"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**Tipo:** {self.tipo}"))
        container.add_item(discord.ui.TextDisplay(content=f"**Força:** {self.strength}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"```\n{self.password}\n```"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="🔒 Esta senha será armazenada no histórico por 1 hora."))
        
        self.add_item(container)
    
    @discord.ui.button(label="📋 Copiar", style=discord.ButtonStyle.primary, custom_id="pwd_copy", emoji="📋", row=0)
    async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Esta senha não pertence a você."), ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content=f"📋 **Sua senha:**\n```\n{self.password}\n```"))
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.followup.send(view=view, ephemeral=True)
    
    @discord.ui.button(label="🔙 Voltar", style=discord.ButtonStyle.secondary, custom_id="pwd_back", emoji="🔙", row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# =========================
# VIEW DE HISTÓRICO
# =========================

class HistoricoView(discord.ui.LayoutView):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.build_container()
    
    def build_container(self):
        container = discord.ui.Container()
        container.accent = 0x5865F2
        
        container.add_item(discord.ui.TextDisplay(content="# 📜 HISTÓRICO DE SENHAS"))
        container.add_item(discord.ui.Separator())
        
        history = get_password_history(self.user_id)
        
        if not history:
            container.add_item(discord.ui.TextDisplay(content="📭 Nenhuma senha gerada recentemente.\n\nUse o painel principal para gerar senhas!"))
        else:
            for i, entry in enumerate(history[:5], 1):
                password = entry.get('password', '???')
                strength = entry.get('strength', 'Desconhecida')
                created_at = entry.get('created_at', datetime.utcnow().isoformat())
                
                try:
                    date = datetime.fromisoformat(created_at).strftime('%d/%m/%Y %H:%M:%S')
                except:
                    date = "agora"
                
                container.add_item(discord.ui.TextDisplay(
                    content=f"**{i}.** `{password[:20]}{'...' if len(password) > 20 else ''}`\n┣ **Força:** {strength}\n┗ **Gerada em:** {date}"
                ))
                container.add_item(discord.ui.Separator())
            
            container.add_item(discord.ui.TextDisplay(content=f"📊 **Total de senhas no histórico:** {len(history)}"))
        
        self.add_item(container)
    
    @discord.ui.button(label="🗑️ Limpar Histórico", style=discord.ButtonStyle.danger, custom_id="pwd_clear_history", emoji="🗑️", row=0)
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este histórico não pertence a você."), ephemeral=True)
            return
        
        clear_password_history(self.user_id)
        
        # Atualizar a view para mostrar que foi limpo
        new_container = discord.ui.Container()
        new_container.accent = 0x5865F2
        new_container.add_item(discord.ui.TextDisplay(content="# 📜 HISTÓRICO DE SENHAS"))
        new_container.add_item(discord.ui.Separator())
        new_container.add_item(discord.ui.TextDisplay(content="🗑️ **Histórico limpo com sucesso!**\n\nNenhuma senha no histórico."))
        
        new_view = discord.ui.LayoutView()
        new_view.add_item(new_container)
        
        await interaction.response.send_message(view=new_view, ephemeral=True)
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# =========================
# BOTÕES DO PAINEL PRINCIPAL
# =========================

class BtnGerarPadrao(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔐 Gerar Padrão (16)", style=discord.ButtonStyle.primary, custom_id="pwd_standard", emoji="🔐")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        password, strength = PasswordGenerator.generate_standard(16)
        save_password_history(interaction.user.id, password, strength)
        view = SenhaGeradaView(password, strength, interaction.user.id, "Padrão (16 caracteres)")
        await interaction.followup.send(view=view, ephemeral=True)
        log("GENERATE", f"Senha padrão gerada para {interaction.user}")


class BtnGerarSegura(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🛡️ Gerar Segura (24)", style=discord.ButtonStyle.success, custom_id="pwd_secure", emoji="🛡️")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        password, strength = PasswordGenerator.generate_secure(24)
        save_password_history(interaction.user.id, password, strength)
        view = SenhaGeradaView(password, strength, interaction.user.id, "Segura (24 caracteres)")
        await interaction.followup.send(view=view, ephemeral=True)
        log("GENERATE", f"Senha segura gerada para {interaction.user}")


class BtnGerarAlfanumerica(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📝 Gerar Alfanumérica (12)", style=discord.ButtonStyle.primary, custom_id="pwd_alnum", emoji="📝")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        password, strength = PasswordGenerator.generate_alphanumeric(12)
        save_password_history(interaction.user.id, password, strength)
        view = SenhaGeradaView(password, strength, interaction.user.id, "Alfanumérica (12 caracteres)")
        await interaction.followup.send(view=view, ephemeral=True)
        log("GENERATE", f"Senha alfanumérica gerada para {interaction.user}")


class BtnGerarNumerica(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔢 Gerar Numérica (8)", style=discord.ButtonStyle.secondary, custom_id="pwd_numeric", emoji="🔢")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        password, strength = PasswordGenerator.generate_numeric(8)
        save_password_history(interaction.user.id, password, strength)
        view = SenhaGeradaView(password, strength, interaction.user.id, "Numérica (8 caracteres)")
        await interaction.followup.send(view=view, ephemeral=True)
        log("GENERATE", f"Senha numérica gerada para {interaction.user}")


class BtnGerarMemoravel(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🧠 Gerar Memorável", style=discord.ButtonStyle.primary, custom_id="pwd_memorable", emoji="🧠")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        password, strength = PasswordGenerator.generate_memorable()
        save_password_history(interaction.user.id, password, strength)
        view = SenhaGeradaView(password, strength, interaction.user.id, "Memorável (palavras + números)")
        await interaction.followup.send(view=view, ephemeral=True)
        log("GENERATE", f"Senha memorável gerada para {interaction.user}")


class BtnHistorico(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📜 Ver Histórico", style=discord.ButtonStyle.secondary, custom_id="pwd_history", emoji="📜")
    
    async def callback(self, interaction: discord.Interaction):
        view = HistoricoView(interaction.user.id)
        await interaction.response.send_message(view=view, ephemeral=True)
        log("HISTORY", f"Histórico acessado por {interaction.user}")


# =========================
# PAINEL PRINCIPAL
# =========================

class PainelGeradorSenhas(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        log("VIEW", "PainelGeradorSenhas criado")

        container = discord.ui.Container()

        container.add_item(discord.ui.TextDisplay(content="# 🔐 GERADOR DE SENHAS TEMPORÁRIAS\nCrie senhas seguras e aleatórias para suas contas"))
        container.add_item(discord.ui.Separator())

        container.add_item(discord.ui.TextDisplay(
            content="**✨ Tipos de Senha:**\n"
                    "• 🔐 **Padrão** - Letras, números e símbolos (16 caracteres)\n"
                    "• 🛡️ **Segura** - Alta segurança (24 caracteres)\n"
                    "• 📝 **Alfanumérica** - Apenas letras e números (12 caracteres)\n"
                    "• 🔢 **Numérica** - Apenas números (8 caracteres)\n"
                    "• 🧠 **Memorável** - Palavras + números (fácil de lembrar)"
        ))
        container.add_item(discord.ui.Separator())

        container.add_item(discord.ui.TextDisplay(
            content="### 🔒 Segurança Garantida\n• Senhas geradas localmente\n• Nenhum dado é compartilhado\n• Histórico temporário de 1 hora"
        ))
        container.add_item(discord.ui.Separator())

        sec_padrao = discord.ui.Section(accessory=BtnGerarPadrao())
        sec_padrao.add_item(discord.ui.TextDisplay(content="🔐 Gerar senha padrão (16 caracteres)"))
        container.add_item(sec_padrao)

        sec_segura = discord.ui.Section(accessory=BtnGerarSegura())
        sec_segura.add_item(discord.ui.TextDisplay(content="🛡️ Gerar senha de alta segurança (24 caracteres)"))
        container.add_item(sec_segura)

        sec_alnum = discord.ui.Section(accessory=BtnGerarAlfanumerica())
        sec_alnum.add_item(discord.ui.TextDisplay(content="📝 Gerar senha alfanumérica (12 caracteres)"))
        container.add_item(sec_alnum)

        sec_numerica = discord.ui.Section(accessory=BtnGerarNumerica())
        sec_numerica.add_item(discord.ui.TextDisplay(content="🔢 Gerar senha numérica (8 caracteres)"))
        container.add_item(sec_numerica)

        sec_memoravel = discord.ui.Section(accessory=BtnGerarMemoravel())
        sec_memoravel.add_item(discord.ui.TextDisplay(content="🧠 Gerar senha memorável (fácil de lembrar)"))
        container.add_item(sec_memoravel)

        sec_history = discord.ui.Section(accessory=BtnHistorico())
        sec_history.add_item(discord.ui.TextDisplay(content="📜 Ver histórico de senhas geradas"))
        container.add_item(sec_history)

        self.add_item(container)


# =========================
# COG PRINCIPAL
# =========================

class PasswordGeneratorSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log("INIT", "PasswordGeneratorSystem carregado")

    async def cog_load(self):
        self.bot.add_view(PainelGeradorSenhas())
        log("INIT", "Views persistentes registradas")

    @discord.app_commands.command(name="enviar_painel_senha", description="🔐 Envia o painel de gerador de senhas temporárias")
    async def send_panel(self, interaction: discord.Interaction):
        try:
            log("PANEL", f"Enviando painel para {interaction.user}")
            view = PainelGeradorSenhas()
            await interaction.response.send_message(view=view)
            log("PANEL", f"Painel enviado com sucesso")
        except Exception as e:
            err("PANEL", e)
            await interaction.response.send_message(view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PasswordGeneratorSystem(bot))
    log("SETUP", "✅ PasswordGeneratorSystem carregado com sucesso!")