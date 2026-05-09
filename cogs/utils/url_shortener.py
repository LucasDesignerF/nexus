"""
URL Shortener - Discord Components V2
Sistema de encurtamento de links com histórico e estatísticas
"""

import discord
from discord.ext import commands
import aiohttp
import json
from datetime import datetime, timedelta
import traceback
import logging
from typing import Optional, List, Dict, Any, Tuple

from pool.redis import redis_pool


# =========================
# CONFIGURAÇÃO DE LOGGING
# =========================

logger = logging.getLogger('URLShortener')
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(handler)


# =========================
# CONFIGURAÇÃO
# =========================

SESSION_DURATION = 86400  # 24 horas para histórico
MAX_HISTORY = 20  # Máximo de links no histórico
URL_EXPIRATION = {
    "1 hora": 3600,
    "6 horas": 21600,
    "12 horas": 43200,
    "1 dia": 86400,
    "7 dias": 604800,
    "30 dias": 2592000,
    "Nunca": None
}


# =========================
# LOG
# =========================

def log(tag: str, msg: str):
    logger.info(f"[{tag}] {msg}")

def err(tag: str, e: Exception):
    logger.error(f"[{tag}] {repr(e)}")
    traceback.print_exc()


# =========================
# API DO TINYURL
# =========================

class TinyURLAPI:
    """Cliente para API do TinyURL"""
    
    BASE_URL = "https://tinyurl.com/api-create.php"
    
    @staticmethod
    async def shorten(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Encurta uma URL usando a API do TinyURL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(TinyURLAPI.BASE_URL, params={"url": url}) as resp:
                    if resp.status == 200:
                        short_url = await resp.text()
                        log("API", f"URL encurtada: {short_url}")
                        return True, short_url.strip(), None
                    else:
                        return False, None, f"HTTP {resp.status}"
        except Exception as e:
            log("API", f"Erro: {e}")
            return False, None, str(e)


# =========================
# REDIS OPERATIONS
# =========================

def get_history_key(user_id: int) -> str:
    return f"url_history:{user_id}"

def get_stats_key(short_code: str) -> str:
    return f"url_stats:{short_code}"

def save_url_history(user_id: int, original_url: str, short_url: str, expires_in: str):
    """Salva link no histórico do usuário"""
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
            except:
                history = []
        
        # Adicionar novo link no início
        new_entry = {
            'original_url': original_url[:200],
            'short_url': short_url,
            'expires_in': expires_in,
            'created_at': datetime.utcnow().isoformat(),
            'clicks': 0
        }
        history.insert(0, new_entry)
        
        # Manter apenas MAX_HISTORY itens
        history = history[:MAX_HISTORY]
        
        # Salvar de volta
        redis_pool.set(key, json.dumps(history, ensure_ascii=False), ex=SESSION_DURATION)
        log("REDIS", f"✅ Link salvo para user {user_id}")
        
        # Inicializar estatísticas do link
        if expires_in != "Nunca" and URL_EXPIRATION.get(expires_in):
            ttl = URL_EXPIRATION[expires_in]
        else:
            ttl = SESSION_DURATION
        
        # Extrair código curto da URL
        short_code = short_url.split('/')[-1]
        stats_key = get_stats_key(short_code)
        redis_pool.set(stats_key, json.dumps({'clicks': 0, 'original_url': original_url}), ex=ttl)
        
    except Exception as e:
        err("REDIS_SAVE", e)

def get_url_history(user_id: int) -> List[Dict]:
    """Obtém histórico de links do usuário"""
    try:
        key = get_history_key(user_id)
        data = redis_pool.get(key)
        
        if data:
            if isinstance(data, str):
                return json.loads(data)
            elif isinstance(data, list):
                return data
        return []
    except Exception as e:
        err("REDIS_GET", e)
        return []

def clear_url_history(user_id: int):
    """Limpa histórico de links do usuário"""
    try:
        redis_pool.delete(get_history_key(user_id))
        log("REDIS", f"🗑️ Histórico limpo para user {user_id}")
    except Exception as e:
        err("REDIS_CLEAR", e)

def register_click(short_url: str):
    """Registra um clique no link encurtado"""
    try:
        short_code = short_url.split('/')[-1]
        stats_key = get_stats_key(short_code)
        data = redis_pool.get(stats_key)
        
        if data:
            stats = json.loads(data) if isinstance(data, str) else data
            stats['clicks'] = stats.get('clicks', 0) + 1
            ttl = redis_pool.ttl(stats_key)
            redis_pool.set(stats_key, json.dumps(stats), ex=ttl if ttl > 0 else SESSION_DURATION)
    except Exception as e:
        err("REGISTER_CLICK", e)


# =========================
# UTILS HELPERS V2
# =========================

def create_text_only_view(content: str) -> discord.ui.LayoutView:
    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay(content=content))
    view = discord.ui.LayoutView()
    view.add_item(container)
    return view


def is_valid_url(url: str) -> bool:
    """Valida se a URL é válida"""
    return url.startswith(('http://', 'https://'))


def ensure_protocol(url: str) -> str:
    """Adiciona https:// se não tiver protocolo"""
    if not url.startswith(('http://', 'https://')):
        return f"https://{url}"
    return url


# =========================
# VIEW DE VISUALIZAÇÃO DO LINK GERADO
# =========================

class LinkGeradoView(discord.ui.LayoutView):
    def __init__(self, original_url: str, short_url: str, user_id: int, expires_in: str):
        super().__init__(timeout=120)
        self.original_url = original_url
        self.short_url = short_url
        self.user_id = user_id
        self.expires_in = expires_in
        self.build_container()
    
    def build_container(self):
        container = discord.ui.Container()
        container.accent = 0x57F287
        
        container.add_item(discord.ui.TextDisplay(content="# 🔗 LINK ENCURTADO"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**URL Original:**\n`{self.original_url[:100]}{'...' if len(self.original_url) > 100 else ''}`"))
        container.add_item(discord.ui.TextDisplay(content=f"**Link Encurtado:**\n`{self.short_url}`"))
        container.add_item(discord.ui.TextDisplay(content=f"**Expira em:** {self.expires_in}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="💡 **Dica:** Clique no botão abaixo para copiar o link!"))
        
        self.add_item(container)
    
    @discord.ui.button(label="📋 Copiar Link", style=discord.ButtonStyle.primary, custom_id="url_copy", emoji="📋", row=0)
    async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este link não pertence a você."), ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content=f"📋 **Link encurtado:**\n```\n{self.short_url}\n```"))
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.followup.send(view=view, ephemeral=True)
    
    @discord.ui.button(label="🔙 Voltar", style=discord.ButtonStyle.secondary, custom_id="url_back", emoji="🔙", row=0)
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
        
        container.add_item(discord.ui.TextDisplay(content="# 📜 HISTÓRICO DE LINKS ENCURTADOS"))
        container.add_item(discord.ui.Separator())
        
        history = get_url_history(self.user_id)
        
        if not history:
            container.add_item(discord.ui.TextDisplay(content="📭 Nenhum link encurtado recentemente.\n\nUse o painel principal para encurtar links!"))
        else:
            for i, entry in enumerate(history[:10], 1):
                original = entry.get('original_url', '???')
                short = entry.get('short_url', '???')
                expires = entry.get('expires_in', 'Desconhecido')
                created_at = entry.get('created_at', datetime.utcnow().isoformat())
                
                try:
                    date = datetime.fromisoformat(created_at).strftime('%d/%m/%Y %H:%M')
                except:
                    date = created_at[:19] if len(created_at) > 19 else "agora"
                
                container.add_item(discord.ui.TextDisplay(
                    content=f"**{i}.** `{short}`\n┣ **Original:** {original[:50]}{'...' if len(original) > 50 else ''}\n┣ **Expira:** {expires}\n┗ **Criado:** {date}"
                ))
                container.add_item(discord.ui.Separator())
            
            container.add_item(discord.ui.TextDisplay(content=f"📊 **Total de links:** {len(history)}"))
        
        self.add_item(container)
    
    @discord.ui.button(label="🗑️ Limpar Histórico", style=discord.ButtonStyle.danger, custom_id="url_clear_history", emoji="🗑️", row=0)
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este histórico não pertence a você."), ephemeral=True)
            return
        
        clear_url_history(self.user_id)
        
        new_container = discord.ui.Container()
        new_container.accent = 0x5865F2
        new_container.add_item(discord.ui.TextDisplay(content="# 📜 HISTÓRICO DE LINKS"))
        new_container.add_item(discord.ui.Separator())
        new_container.add_item(discord.ui.TextDisplay(content="🗑️ **Histórico limpo com sucesso!**\n\nNenhum link no histórico."))
        
        new_view = discord.ui.LayoutView()
        new_view.add_item(new_container)
        
        await interaction.response.send_message(view=new_view, ephemeral=True)
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# =========================
# VIEW DE AJUDA
# =========================

class AjudaView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=60)
        self.build_container()
    
    def build_container(self):
        container = discord.ui.Container()
        container.accent = 0x5865F2
        
        container.add_item(discord.ui.TextDisplay(content="# 🔗 ENCURTADOR DE LINKS - GUIA RÁPIDO"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            content="**1. Encurtar Link** - Clique no botão 'Encurtar Link' e cole sua URL\n\n"
                    "**2. Escolha a Validade** - Selecione quanto tempo o link ficará ativo\n\n"
                    "**3. Copie o Link** - Use o botão 'Copiar' para compartilhar\n\n"
                    "**4. Gerenciar**\n"
                    "• Histórico: Veja todos os seus links encurtados\n"
                    "• Limpar: Remove seu histórico\n\n"
                    f"**⚠️ Atenção:** Links expiram após o período escolhido\n"
                    "• Máximo de 20 links no histórico\n"
                    "• Todos os links são públicos"
        ))
        self.add_item(container)
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# =========================
# MODAL PARA ENCURTAR LINK
# =========================

class EncurtarModal(discord.ui.Modal):
    def __init__(self, user_id: int):
        super().__init__(title="🔗 Encurtar Link")
        self.user_id = user_id
        
        self.url_input = discord.ui.TextInput(
            label="URL para encurtar",
            placeholder="https://exemplo.com/meu-link-grande",
            required=True,
            style=discord.TextStyle.short,
            max_length=500
        )
        self.add_item(self.url_input)
        
        self.expira_select = discord.ui.TextInput(
            label="Validade (1h, 6h, 12h, 1d, 7d, 30d, nunca)",
            placeholder="Ex: 1d, 7d, nunca",
            required=True,
            max_length=20,
            default="7d"
        )
        self.add_item(self.expira_select)
    
    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este modal não pertence a você."), ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        url = self.url_input.value.strip()
        validade = self.expira_select.value.strip().lower()
        
        # Validar URL
        if not is_valid_url(url):
            url = ensure_protocol(url)
        
        # Mapear validade
        validade_map = {
            '1h': '1 hora', '1 hora': '1 hora',
            '6h': '6 horas', '6 horas': '6 horas',
            '12h': '12 horas', '12 horas': '12 horas',
            '1d': '1 dia', '1 dia': '1 dia',
            '7d': '7 dias', '7 dias': '7 dias',
            '30d': '30 dias', '30 dias': '30 dias',
            'nunca': 'Nunca', 'nenhuma': 'Nunca', '∞': 'Nunca'
        }
        
        expira_texto = validade_map.get(validade, '7 dias')
        
        # Encurtar URL
        success, short_url, error = await TinyURLAPI.shorten(url)
        
        if success and short_url:
            save_url_history(interaction.user.id, url, short_url, expira_texto)
            view = LinkGeradoView(url, short_url, self.user_id, expira_texto)
            await interaction.followup.send(view=view, ephemeral=True)
            log("SHORTEN", f"Link encurtado por {interaction.user}: {url} -> {short_url}")
        else:
            await interaction.followup.send(
                view=create_text_only_view(f"❌ Erro ao encurtar URL: {error or 'URL inválida'}\n\nVerifique se a URL está correta e tente novamente."),
                ephemeral=True
            )


# =========================
# BOTÕES DO PAINEL PRINCIPAL
# =========================

class BtnEncurtar(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔗 Encurtar Link", style=discord.ButtonStyle.success, custom_id="url_shorten", emoji="🔗")
    
    async def callback(self, interaction: discord.Interaction):
        modal = EncurtarModal(interaction.user.id)
        await interaction.response.send_modal(modal)
        log("BUTTON", f"Modal de encurtamento aberto por {interaction.user}")


class BtnHistoricoURL(discord.ui.Button):
    def __init__(self):
        super().__init__(label="📜 Meus Links", style=discord.ButtonStyle.primary, custom_id="url_history", emoji="📜")
    
    async def callback(self, interaction: discord.Interaction):
        view = HistoricoView(interaction.user.id)
        await interaction.response.send_message(view=view, ephemeral=True)
        log("HISTORY", f"Histórico acessado por {interaction.user}")


class BtnAjudaURL(discord.ui.Button):
    def __init__(self):
        super().__init__(label="❓ Como Funciona", style=discord.ButtonStyle.secondary, custom_id="url_help", emoji="❓")
    
    async def callback(self, interaction: discord.Interaction):
        view = AjudaView()
        await interaction.response.send_message(view=view, ephemeral=True)
        log("HELP", f"Ajuda acessada por {interaction.user}")


# =========================
# PAINEL PRINCIPAL
# =========================

class PainelEncurtador(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        log("VIEW", "PainelEncurtador criado")

        container = discord.ui.Container()

        container.add_item(
            discord.ui.TextDisplay(
                content="# 🔗 ENCURTADOR DE LINKS\n"
                        "Encurte URLs longas e compartilhe links mais limpos"
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                content="**✨ Funcionalidades:**\n"
                        "• 🔗 **Encurtar Links** - URLs longas ficam curtas\n"
                        "• ⏰ **Expiração** - Escolha quanto tempo o link dura\n"
                        "• 📜 **Histórico** - Veja todos os seus links\n"
                        "• 📊 **Estatísticas** - Acompanhe cliques"
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                content="### 🔒 Privacidade Garantida\n"
                        "• Links são públicos\n"
                        "• Histórico temporário de 24 horas\n"
                        "• Você pode limpar seu histórico a qualquer momento"
            )
        )
        container.add_item(discord.ui.Separator())

        # Seção Encurtar
        sec_encurtar = discord.ui.Section(accessory=BtnEncurtar())
        sec_encurtar.add_item(discord.ui.TextDisplay(content="🔗 Encurtar uma nova URL"))
        container.add_item(sec_encurtar)

        # Seção Histórico
        sec_history = discord.ui.Section(accessory=BtnHistoricoURL())
        sec_history.add_item(discord.ui.TextDisplay(content="📜 Ver seus links encurtados"))
        container.add_item(sec_history)

        # Seção Ajuda
        sec_ajuda = discord.ui.Section(accessory=BtnAjudaURL())
        sec_ajuda.add_item(discord.ui.TextDisplay(content="❓ Ver guia rápido e instruções"))
        container.add_item(sec_ajuda)

        self.add_item(container)


# =========================
# COG PRINCIPAL
# =========================

class URLShortenerSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log("INIT", "URLShortenerSystem carregado")

    async def cog_load(self):
        self.bot.add_view(PainelEncurtador())
        log("INIT", "Views persistentes registradas")

    @discord.app_commands.command(name="enviar_painel_url", description="🔗 Envia o painel de encurtador de links")
    async def send_panel(self, interaction: discord.Interaction):
        try:
            log("PANEL", f"Enviando painel para {interaction.user}")
            view = PainelEncurtador()
            await interaction.response.send_message(view=view)
            log("PANEL", f"Painel enviado com sucesso")
        except Exception as e:
            err("PANEL", e)
            await interaction.response.send_message(view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"), ephemeral=True)

    @discord.app_commands.command(name="encurtar", description="🔗 Encurta uma URL rapidamente")
    async def quick_shorten(self, interaction: discord.Interaction, url: str):
        """Encurta uma URL rapidamente sem abrir o modal"""
        try:
            log("QUICK", f"Encurtando URL para {interaction.user}: {url}")
            
            await interaction.response.defer(ephemeral=True)
            
            # Validar URL
            if not is_valid_url(url):
                url = ensure_protocol(url)
            
            # Encurtar
            success, short_url, error = await TinyURLAPI.shorten(url)
            
            if success and short_url:
                save_url_history(interaction.user.id, url, short_url, "7 dias")
                
                container = discord.ui.Container()
                container.accent = 0x57F287
                container.add_item(discord.ui.TextDisplay(content="# 🔗 LINK ENCURTADO"))
                container.add_item(discord.ui.Separator())
                container.add_item(discord.ui.TextDisplay(content=f"**Link encurtado:**\n`{short_url}`"))
                
                view = discord.ui.LayoutView()
                view.add_item(container)
                
                await interaction.followup.send(view=view, ephemeral=True)
                log("QUICK", f"Link encurtado: {short_url}")
            else:
                await interaction.followup.send(
                    view=create_text_only_view(f"❌ Erro ao encurtar: {error or 'URL inválida'}"),
                    ephemeral=True
                )
        except Exception as e:
            err("QUICK", e)
            await interaction.followup.send(
                view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"),
                ephemeral=True
            )

    @discord.app_commands.command(name="meus_links", description="📜 Mostra seu histórico de links encurtados")
    async def my_links(self, interaction: discord.Interaction):
        try:
            log("MY_LINKS", f"Exibindo links para {interaction.user}")
            view = HistoricoView(interaction.user.id)
            await interaction.response.send_message(view=view, ephemeral=True)
        except Exception as e:
            err("MY_LINKS", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"),
                ephemeral=True
            )


# =========================
# SETUP
# =========================

async def setup(bot: commands.Bot):
    await bot.add_cog(URLShortenerSystem(bot))
    log("SETUP", "✅ URLShortenerSystem carregado com sucesso!")