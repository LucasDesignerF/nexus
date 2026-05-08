import discord
from discord import app_commands
from discord.ext import commands
import datetime
import traceback
import time
import aiohttp
import json
from typing import List, Optional, Dict, Any

# =========================
# LOG SYSTEM
# =========================

def log(prefix: str, msg: str):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}][Moderation:{prefix}] {msg}", flush=True)


def err(prefix: str, e: Exception):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}][Moderation:{prefix}:ERROR] {repr(e)}", flush=True)
    traceback.print_exc()


# =========================
# COMPONENTS V2 VIA API DIRETA
# =========================

class ComponentsV2Message:
    """Envia mensagens com Components V2 usando API direta do Discord"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.api_url = "https://discord.com/api/v10"
    
    def create_media_gallery_item(self, url: str, description: str = None) -> Dict:
        """Cria um item para Media Gallery conforme documentação"""
        item = {
            "media": {"url": url}
        }
        if description:
            item["description"] = description
        return item
    
    def create_container(self, accent_color: int = None, spoiler: bool = False) -> Dict:
        """Cria um Container (type 17)"""
        container = {
            "type": 17,
            "components": []
        }
        if accent_color:
            container["accent_color"] = accent_color
        if spoiler:
            container["spoiler"] = True
        return container
    
    def add_text_display(self, container: Dict, content: str) -> None:
        """Adiciona Text Display (type 10) ao container"""
        container["components"].append({
            "type": 10,
            "content": content
        })
    
    def add_media_gallery(self, container: Dict, urls: List[str]) -> None:
        """Adiciona Media Gallery (type 12) ao container"""
        items = [self.create_media_gallery_item(url) for url in urls]
        container["components"].append({
            "type": 12,
            "items": items
        })
    
    def add_separator(self, container: Dict) -> None:
        """Adiciona Separator (type 14) ao container"""
        container["components"].append({
            "type": 14,
            "divider": True,
            "spacing": 1
        })
    
    def add_section(self, container: Dict, text: str, accessory: Dict = None) -> None:
        """Adiciona Section (type 9) ao container"""
        section = {
            "type": 9,
            "components": [{"type": 10, "content": text}]
        }
        if accessory:
            section["accessory"] = accessory
        container["components"].append(section)
    
    def add_button_accessory(self, label: str, custom_id: str, style: int = 1) -> Dict:
        """Cria um botão para usar como accessory em Section"""
        return {
            "type": 2,  # Button
            "label": label,
            "custom_id": custom_id,
            "style": style
        }
    
    def add_thumbnail_accessory(self, url: str) -> Dict:
        """Cria uma thumbnail para usar como accessory em Section"""
        return {
            "type": 11,  # Thumbnail
            "media": {"url": url}
        }
    
    async def send_message(self, interaction: discord.Interaction, components: List[Dict], ephemeral: bool = False):
        """Envia a mensagem via API direta"""
        
        # Prepara o payload
        payload = {
            "components": components,
            "flags": 1 << 15  # IS_COMPONENTS_V2 = 32768
        }
        
        if ephemeral:
            payload["flags"] |= 64  # Adiciona flag ephemeral
        
        # Verifica se a interação já foi respondida
        if not interaction.response.is_done():
            # Primeira resposta: interaction callback
            callback_url = f"{self.api_url}/interactions/{interaction.id}/{interaction.token}/callback"
            callback_payload = {
                "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
                "data": payload
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    callback_url,
                    json=callback_payload,
                    headers={"Authorization": f"Bot {self.bot_token}"}
                ) as resp:
                    if resp.status not in [200, 204]:
                        text = await resp.text()
                        raise Exception(f"Erro {resp.status}: {text}")
                    log("API", f"Mensagem enviada via callback (status {resp.status})")
        else:
            # Followup
            webhook_url = f"{self.api_url}/webhooks/{interaction.application_id}/{interaction.token}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers={"Authorization": f"Bot {self.bot_token}"}
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise Exception(f"Erro {resp.status}: {text}")
                    log("API", "Mensagem enviada via webhook")


# =========================
# COG PRINCIPAL
# =========================

class Moderation(commands.Cog):
    """Cog de moderação com Components V2 via API direta"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.components_api = None
        log("INIT", "=== Cog Moderation inicializada ===")
        log("INIT", f"Discord.py version: {discord.__version__}")

    async def cog_load(self):
        """Inicializa a API quando a cog é carregada"""
        self.components_api = ComponentsV2Message(self.bot.http.token)
        log("INIT", "API Components V2 inicializada")

    # ========================
    # USERINFO VIA API DIRETA
    # ========================
    @app_commands.command(name="userinfo", description="Mostra informações detalhadas de um membro")
    async def userinfo(
        self, 
        interaction: discord.Interaction, 
        membro: Optional[discord.Member] = None
    ):
        """Mostra informações do usuário com avatar como imagem real"""
        
        if membro is None:
            membro = interaction.user
        
        log("USERINFO", f"Exibindo informações de {membro}")
        
        try:
            # Criar containers
            containers = []
            
            # Container principal
            container = self.components_api.create_container(accent_color=membro.color.value if membro.color.value != 0 else 0x5865F2)
            
            # Cabeçalho
            header = f"# 👤 {membro.display_name}"
            if membro.bot:
                header += "\n🤖 **BOT**"
            self.components_api.add_text_display(container, header)
            
            # Avatar em Media Gallery
            self.components_api.add_media_gallery(container, [membro.display_avatar.url])
            self.components_api.add_separator(container)
            
            # Informações
            created_at = discord.utils.format_dt(membro.created_at, 'R')
            joined_at = discord.utils.format_dt(membro.joined_at, 'R') if membro.joined_at else 'N/A'
            
            info_text = f"""**📋 Informações**
┣ **ID:** `{membro.id}`
┣ **Nome global:** {membro.global_name or 'N/A'}
┣ **Conta criada:** {created_at}
┣ **Entrou no servidor:** {joined_at}
┗ **Bot:** {'Sim' if membro.bot else 'Não'}"""
            
            self.components_api.add_text_display(container, info_text)
            self.components_api.add_separator(container)
            
            # Cargos
            role_count = len(membro.roles) - 1
            if role_count > 0:
                role_mentions = [role.name for role in membro.roles if role.name != "@everyone"]
                roles_text = ", ".join(role_mentions[:5])
                if len(role_mentions) > 5:
                    roles_text += f" e +{len(role_mentions)-5}"
                
                roles_display = f"""**🎭 Cargos ({role_count})**
{roles_text if roles_text else 'Nenhum cargo especial'}"""
                self.components_api.add_text_display(container, roles_display)
                
                # Adicionar alguns cargos como sections com thumbnails
                for role in membro.roles[1:4]:  # Pula @everyone, pega até 3
                    if role.display_icon:
                        section_text = f"**{role.name}**"
                        thumbnail = self.components_api.add_thumbnail_accessory(role.display_icon.url)
                        self.components_api.add_section(container, section_text, thumbnail)
            
            self.components_api.add_separator(container)
            
            # Rodapé
            self.components_api.add_text_display(container, f"🕒 {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            
            containers.append(container)
            
            # Enviar
            await self.components_api.send_message(interaction, containers, ephemeral=False)
            log("USERINFO", "✅ Perfil enviado com sucesso")
            
        except Exception as e:
            err("USERINFO", e)
            await interaction.response.send_message(f"❌ Erro: {str(e)[:100]}", ephemeral=True)
    
    # ========================
    # TEST V2
    # ========================
    @app_commands.command(name="test_v2", description="Testa os Components V2")
    async def test_v2(self, interaction: discord.Interaction):
        """Comando de teste para demonstrar Components V2"""
        log("TEST_V2", "=== INICIANDO COMANDO DE TESTE V2 ===")
        
        try:
            containers = []
            
            # Container 1: Boas vindas
            container1 = self.components_api.create_container(accent_color=0x57F287)
            self.components_api.add_text_display(container1, "# 🎉 Components V2 Funcionando!")
            self.components_api.add_text_display(container1, "Este é um exemplo de mensagem usando Components V2 com containers.")
            self.components_api.add_separator(container1)
            
            # Media Gallery com imagens
            self.components_api.add_media_gallery(container1, [
                "https://cdn.discordapp.com/embed/avatars/0.png",
                "https://cdn.discordapp.com/embed/avatars/1.png",
                "https://cdn.discordapp.com/embed/avatars/2.png"
            ])
            
            containers.append(container1)
            
            # Container 2: Informações
            container2 = self.components_api.create_container(accent_color=0x5865F2)
            self.components_api.add_text_display(container2, "## ✅ Recursos disponíveis:")
            self.components_api.add_text_display(container2, """
• **Containers** com cores personalizadas
• **Media Gallery** para imagens/vídeos
• **Text Display** com suporte a Markdown
• **Separators** para organização visual
• **Sections** com acessórios
            """)
            
            containers.append(container2)
            
            # Enviar
            await self.components_api.send_message(interaction, containers, ephemeral=True)
            log("TEST_V2", "✅ Comando test_v2 executado com sucesso!")
            
        except Exception as e:
            err("TEST_V2", e)
            await interaction.response.send_message(f"❌ Erro: {str(e)[:200]}", ephemeral=True)
    
    # ========================
    # BAN
    # ========================
    @app_commands.command(name="ban", description="Bane um membro do servidor")
    @app_commands.default_permissions(ban_members=True)
    async def ban(
        self, 
        interaction: discord.Interaction, 
        membro: discord.Member, 
        motivo: str = "Não especificado"
    ):
        log("BAN", f"Executado contra {membro}")
        try:
            await membro.ban(reason=motivo)
            
            container = self.components_api.create_container(accent_color=0xFF4444)
            self.components_api.add_text_display(container, "# 🔨 Usuário Banido")
            self.components_api.add_media_gallery(container, [membro.display_avatar.url])
            self.components_api.add_separator(container)
            self.components_api.add_text_display(container, f"**Usuário:** {membro.mention}\n**Motivo:** {motivo}")
            
            await self.components_api.send_message(interaction, [container], ephemeral=True)
            
        except Exception as e:
            err("BAN", e)
            await interaction.response.send_message("❌ Erro ao banir", ephemeral=True)
    
    # ========================
    # KICK
    # ========================
    @app_commands.command(name="kick", description="Expulsa um membro do servidor")
    @app_commands.default_permissions(kick_members=True)
    async def kick(
        self, 
        interaction: discord.Interaction, 
        membro: discord.Member, 
        motivo: str = "Não especificado"
    ):
        log("KICK", f"Executado contra {membro}")
        try:
            await membro.kick(reason=motivo)
            
            container = self.components_api.create_container(accent_color=0xFFAA44)
            self.components_api.add_text_display(container, "# 👢 Usuário Expulso")
            self.components_api.add_media_gallery(container, [membro.display_avatar.url])
            self.components_api.add_separator(container)
            self.components_api.add_text_display(container, f"**Usuário:** {membro.mention}\n**Motivo:** {motivo}")
            
            await self.components_api.send_message(interaction, [container], ephemeral=True)
            
        except Exception as e:
            err("KICK", e)
            await interaction.response.send_message("❌ Erro ao expulsar", ephemeral=True)


# =========================
# SETUP
# =========================

async def setup(bot: commands.Bot):
    log("SETUP", "=== Carregando Cog Moderation ===")
    await bot.add_cog(Moderation(bot))
    log("SETUP", "✅ Cog Moderation carregada com sucesso!")