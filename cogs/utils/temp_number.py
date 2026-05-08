"""
Temporary Number System - Discord Components V2
Sistema de número telefônico temporário usando OnlineSMS API
Mesmo estilo e padrão do sistema de email temporário
"""

import discord
from discord.ext import commands
import aiohttp
import asyncio
import random
import re
import logging
import functools
from datetime import datetime, timedelta
import traceback
from typing import Optional, List, Dict, Any, Tuple

from pool.redis import redis_pool


# =========================
# CONFIGURAÇÃO DE LOGGING
# =========================

logger = logging.getLogger('TempNumber')
logger.setLevel(logging.DEBUG)

# Handler para console
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(handler)


# =========================
# CONFIGURAÇÃO
# =========================

SESSION_DURATION = 1800  # 30 minutos


# =========================
# LOG
# =========================

def log(tag: str, msg: str):
    logger.info(f"[{tag}] {msg}")

def err(tag: str, e: Exception):
    logger.error(f"[{tag}] {repr(e)}")
    traceback.print_exc()


# =========================
# API DO ONLINESMS
# =========================

class OnlineSMSAPI:
    """Cliente para API do OnlineSMS"""
    
    BASE_URL = "https://online-sms.org"
    TIMEOUT = 30
    
    def __init__(self):
        self.session: aiohttp.ClientSession = None
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.TIMEOUT)
            self.session = aiohttp.ClientSession(headers=self._headers, timeout=timeout)
        return self.session
    
    async def get_random_number(self, country: str = "US") -> Tuple[bool, Optional[str], Optional[str]]:
        """Obtém um número aleatório para o país"""
        country_names = {
            "US": "US", "BR": "Brazil", "CA": "Canada", 
            "UK": "UK", "AU": "Australia", "DE": "Germany",
            "FR": "France", "ES": "Spain", "IT": "Italy"
        }
        country_name = country_names.get(country.upper(), "US")
        url = f"{self.BASE_URL}/Free-{country_name}-Phone-Number"
        
        session = await self._get_session()
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return False, None, f"HTTP {resp.status}"
                
                html = await resp.text()
                numbers = self._parse_numbers(html)
                
                if numbers:
                    return True, random.choice(numbers), None
                return False, None, "Nenhum número encontrado"
        except Exception as e:
            return False, None, str(e)
    
    def _parse_numbers(self, html: str) -> List[str]:
        """Extrai números de telefone do HTML"""
        numbers = set()
        pattern = r'\+(\d{10,15})'
        matches = re.findall(pattern, html)
        for match in matches:
            if len(match) >= 10:
                numbers.add(match)
        
        link_pattern = r'/free-phone-number-(\d{10,15})'
        link_matches = re.findall(link_pattern, html)
        for match in link_matches:
            if len(match) >= 10:
                numbers.add(match)
        
        return list(numbers)[:20]
    
    async def get_messages(self, phone_number: str) -> Tuple[bool, List[Dict], Optional[str]]:
        """Obtém mensagens SMS para um número específico"""
        url = f"{self.BASE_URL}/free-phone-number-{phone_number}"
        
        session = await self._get_session()
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return False, [], f"HTTP {resp.status}"
                
                html = await resp.text()
                messages = self._parse_messages(html)
                return True, messages, None
        except Exception as e:
            return False, [], str(e)
    
    def _parse_messages(self, html: str) -> List[Dict]:
        """Extrai mensagens SMS do HTML"""
        messages = []
        
        # Buscar por números de telefone (remetentes)
        phone_pattern = r'\+(\d{10,15})'
        phones = re.findall(phone_pattern, html)
        
        # Buscar por textos de mensagem
        text_pattern = r'<div[^>]*>([^<]*(?:SMS|Message|Texto|Mensagem)[^<]*)</div>'
        texts = re.findall(text_pattern, html, re.IGNORECASE)
        
        for i, phone in enumerate(phones[:5]):
            msg_text = texts[i] if i < len(texts) else f"Mensagem de {phone}"
            messages.append({
                'sender': phone,
                'message': re.sub(r'\s+', ' ', msg_text).strip()[:300],
                'timestamp': datetime.now().isoformat()
            })
        
        if not messages:
            # Fallback: criar mensagem genérica
            messages.append({
                'sender': 'Desconhecido',
                'message': 'Mensagem SMS recebida',
                'timestamp': datetime.now().isoformat()
            })
        
        return messages
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


# =========================
# REDIS OPERATIONS
# =========================

def get_session_key(guild_id: int, user_id: int) -> str:
    return f"tempnumber:{guild_id}:{user_id}"

def get_number_session(guild_id: int, user_id: int) -> dict:
    return redis_pool.get(get_session_key(guild_id, user_id))

def save_number_session(guild_id: int, user_id: int, data: dict):
    redis_pool.set(get_session_key(guild_id, user_id), data, ex=SESSION_DURATION)

def delete_number_session(guild_id: int, user_id: int):
    redis_pool.delete(get_session_key(guild_id, user_id))


# =========================
# UTILS HELPERS V2
# =========================

def create_text_only_view(content: str) -> discord.ui.LayoutView:
    """Cria uma view V2 apenas com texto"""
    container = discord.ui.Container()
    container.add_item(discord.ui.TextDisplay(content=content))
    view = discord.ui.LayoutView()
    view.add_item(container)
    return view


# =========================
# VIEW DE VISUALIZAÇÃO DE MENSAGEM SMS
# =========================

class MensagemSMSView(discord.ui.LayoutView):
    """View para exibir mensagem SMS completa em um Container"""
    
    def __init__(self, sender: str, message: str, date: str):
        super().__init__(timeout=120)
        self.sender = sender
        self.message = message
        self.date = date
        self.build_container()
        log("VIEW", f"MensagemSMSView criada para sender: {sender}")
    
    def build_container(self):
        """Constrói o container com a mensagem completa"""
        container = discord.ui.Container()
        container.accent = 0x5865F2
        
        container.add_item(discord.ui.TextDisplay(content="# 📱 Mensagem SMS"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**De:** +{self.sender}"))
        container.add_item(discord.ui.TextDisplay(content=f"**Data:** {self.date}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="### 📝 Conteúdo da Mensagem"))
        container.add_item(discord.ui.TextDisplay(content=self.message[:1900] if self.message else "*(Sem conteúdo)*"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="🔒 Esta mensagem é temporária."))
        
        self.add_item(container)
    
    @discord.ui.button(label="🔙 Voltar", style=discord.ButtonStyle.secondary, custom_id="tempnumber:back", emoji="🔙", row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        log("BUTTON", f"Botão Voltar clicado por {interaction.user}")
        await interaction.response.defer()
        await interaction.delete_original_response()
    
    @discord.ui.button(label="📋 Copiar Remetente", style=discord.ButtonStyle.primary, custom_id="tempnumber:copy", emoji="📋", row=0)
    async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        log("BUTTON", f"Botão Copiar clicado por {interaction.user}")
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content=f"**Número do remetente:** `+{self.sender}`"))
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)
    
    async def on_timeout(self):
        log("VIEW", "MensagemSMSView expirou")
        for item in self.children:
            item.disabled = True


# =========================
# FUNÇÃO PARA CRIAR NÚMERO
# =========================

async def create_new_number(user_id: int, country: str = "US") -> dict:
    """Cria um novo número temporário"""
    log("CREATE", f"Iniciando criação para user {user_id}, país {country}")
    api = OnlineSMSAPI()
    try:
        success, number, error = await api.get_random_number(country)
        
        if not success or not number:
            log("CREATE", f"❌ Falha ao obter número: {error}")
            return None
        
        country_names = {
            "US": "Estados Unidos", "BR": "Brasil", "CA": "Canadá",
            "UK": "Reino Unido", "AU": "Austrália", "DE": "Alemanha",
            "FR": "França", "ES": "Espanha", "IT": "Itália"
        }
        
        log("CREATE", f"✅ Número criado: +{number} ({country})")
        
        return {
            'number': number,
            'country': country_names.get(country, country),
            'country_code': country,
            'created_at': datetime.utcnow().isoformat()
        }
    except Exception as e:
        err("CREATE_NUMBER", e)
        return None
    finally:
        await api.close()


# =========================
# BOTÕES DO PAINEL DE CONTROLE DO NÚMERO
# =========================

class BtnVerificarSMS(discord.ui.Button):
    def __init__(self, phone_number: str, guild_id: int, user_id: int):
        super().__init__(
            label="📱 Verificar SMS",
            style=discord.ButtonStyle.primary,
            custom_id=f"tempnumber:check_{user_id}",
            emoji="📱"
        )
        self.phone_number = phone_number
        self.guild_id = guild_id
        self.user_id = user_id
        log("BUTTON", f"BtnVerificarSMS criado para user {user_id}")

    async def callback(self, interaction: discord.Interaction):
        log("BUTTON", f"BtnVerificarSMS clicado por {interaction.user.id}")
        
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este painel não pertence a você."), ephemeral=True)
            return

        await interaction.response.defer()
        
        api = OnlineSMSAPI()
        try:
            success, messages, error = await api.get_messages(self.phone_number)
            
            if not success or not messages:
                await api.close()
                await interaction.followup.send(
                    view=create_text_only_view(f"📭 Nenhuma mensagem recebida ainda.\n\n💡 Envie um SMS para: +{self.phone_number}"),
                    ephemeral=True
                )
                return
            
            container = discord.ui.Container()
            container.add_item(discord.ui.TextDisplay(content="# 📱 Sua Caixa de Entrada SMS"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(content=f"**Número:** +{self.phone_number}"))
            container.add_item(discord.ui.TextDisplay(content=f"**Total:** {len(messages)} mensagem(ns)"))
            container.add_item(discord.ui.Separator())
            
            for i, msg in enumerate(messages[:10], 1):
                sender = msg.get('sender', 'Desconhecido')
                message_text = msg.get('message', 'Sem conteúdo')
                date_str = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                
                msg_view = MensagemSMSView(sender, message_text, date_str)
                
                btn_view = discord.ui.Button(
                    label=f"📖 Ver SMS {i}",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"tempnumber:view_{i}_{self.user_id}",
                    emoji="📖"
                )
                
                async def view_callback(interaction, v=msg_view):
                    await interaction.response.send_message(view=v, ephemeral=True)
                
                btn_view.callback = view_callback
                
                section = discord.ui.Section(accessory=btn_view)
                section.add_item(discord.ui.TextDisplay(
                    content=f"**De:** +{sender}\n**Hora:** {date_str}\n**Mensagem:** {message_text[:80]}..."
                ))
                container.add_item(section)
                container.add_item(discord.ui.Separator())
            
            await api.close()
            
            view = discord.ui.LayoutView()
            view.add_item(container)
            await interaction.followup.send(view=view, ephemeral=True)
            
        except Exception as e:
            err("VERIFICAR", e)
            await api.close()
            await interaction.followup.send(view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"), ephemeral=True)


class BtnInfoNumero(discord.ui.Button):
    def __init__(self, phone_number: str, country: str, user_id: int):
        super().__init__(
            label="ℹ️ Informações",
            style=discord.ButtonStyle.secondary,
            custom_id=f"tempnumber:info_{user_id}",
            emoji="ℹ️"
        )
        self.phone_number = phone_number
        self.country = country
        self.user_id = user_id
        log("BUTTON", f"BtnInfoNumero criado para user {user_id}")

    async def callback(self, interaction: discord.Interaction):
        log("BUTTON", f"BtnInfoNumero clicado por {interaction.user.id}")
        
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este painel não pertence a você."), ephemeral=True)
            return

        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content="# 📞 Informações do Número"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**Número:** +{self.phone_number}"))
        container.add_item(discord.ui.TextDisplay(content=f"**País:** {self.country}"))
        container.add_item(discord.ui.TextDisplay(content=f"**Validade:** {SESSION_DURATION // 60} minutos"))
        container.add_item(discord.ui.TextDisplay(content=f"**Status:** ✅ Ativo"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="**📌 Dicas:**\n• Use este número para receber SMS\n• O número é compartilhado com outros usuários\n• As mensagens são temporárias"))
        
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)


class BtnCancelarNumero(discord.ui.Button):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(
            label="🗑️ Cancelar Número",
            style=discord.ButtonStyle.danger,
            custom_id=f"tempnumber:cancel_{user_id}",
            emoji="🗑️"
        )
        self.guild_id = guild_id
        self.user_id = user_id
        log("BUTTON", f"BtnCancelarNumero criado para user {user_id}")

    async def callback(self, interaction: discord.Interaction):
        log("BUTTON", f"BtnCancelarNumero clicado por {interaction.user.id}")
        
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este painel não pertence a você."), ephemeral=True)
            return

        session = get_number_session(self.guild_id, self.user_id)
        
        if not session:
            await interaction.response.send_message(view=create_text_only_view("❌ Nenhum número ativo para cancelar."), ephemeral=True)
            return
        
        delete_number_session(self.guild_id, self.user_id)
        
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content="# 🗑️ Número Cancelado"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"O número **+{session['number']}** foi cancelado com sucesso!"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="Use o painel principal para obter um novo número quando precisar."))
        
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)
        
        log("CANCEL", f"Número +{session['number']} cancelado por {interaction.user}")


# =========================
# PAINEL DE CONTROLE DO NÚMERO
# =========================

class NumberManagementView(discord.ui.LayoutView):
    def __init__(self, phone_number: str, country: str, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        self.phone_number = phone_number
        self.country = country
        self.guild_id = guild_id
        self.user_id = user_id
        log("VIEW", f"NumberManagementView criada para user {user_id}, número +{phone_number}")

        container = discord.ui.Container()

        container.add_item(
            discord.ui.TextDisplay(
                content="# 📞 SEU NÚMERO TEMPORÁRIO\nGerencie seu número para receber SMS"
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                content=f"**Número:** `+{phone_number}`\n"
                        f"**País:** {country}\n"
                        f"**Validade:** {SESSION_DURATION // 60} minutos\n"
                        f"**Status:** ✅ Ativo"
            )
        )
        container.add_item(discord.ui.Separator())

        sec_check = discord.ui.Section(accessory=BtnVerificarSMS(phone_number, guild_id, user_id))
        sec_check.add_item(discord.ui.TextDisplay(content="📱 Verificar mensagens recebidas"))
        container.add_item(sec_check)

        sec_info = discord.ui.Section(accessory=BtnInfoNumero(phone_number, country, user_id))
        sec_info.add_item(discord.ui.TextDisplay(content="ℹ️ Informações do número"))
        container.add_item(sec_info)

        sec_cancel = discord.ui.Section(accessory=BtnCancelarNumero(guild_id, user_id))
        sec_cancel.add_item(discord.ui.TextDisplay(content="🗑️ Cancelar este número"))
        container.add_item(sec_cancel)

        self.add_item(container)


# =========================
# BOTÕES DO PAINEL PRINCIPAL
# =========================

class BtnCriarNumeroTemp(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="📞 Obter Número",
            style=discord.ButtonStyle.success,
            custom_id="tempnumber:create_main",
            emoji="📞"
        )
        log("BUTTON", "BtnCriarNumeroTemp criado")

    async def callback(self, interaction: discord.Interaction):
        log("BUTTON", f"BtnCriarNumeroTemp clicado por {interaction.user.id}")
        
        # Verificar se já tem número
        existing = get_number_session(interaction.guild_id, interaction.user.id)
        
        if existing:
            view = NumberManagementView(
                existing['number'], 
                existing['country'],
                interaction.guild_id, 
                interaction.user.id
            )
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        
        # Criar container de seleção de país
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content="# 🌍 Selecione o País"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="Escolha o país do número que deseja obter:"))
        container.add_item(discord.ui.Separator())
        
        paises = [
            ("🇺🇸 Estados Unidos", "US"),
            ("🇬🇧 Reino Unido", "UK"),
            ("🇧🇷 Brasil", "BR"),
            ("🇨🇦 Canadá", "CA"),
            ("🇦🇺 Austrália", "AU"),
            ("🇩🇪 Alemanha", "DE"),
            ("🇫🇷 França", "FR"),
            ("🇪🇸 Espanha", "ES"),
            ("🇮🇹 Itália", "IT"),
        ]
        
        for nome, codigo in paises:
            btn = discord.ui.Button(
                label=nome,
                style=discord.ButtonStyle.secondary,
                custom_id=f"tempnumber:select_{codigo}",
                emoji="📞"
            )
            btn.callback = functools.partial(self.pais_selecionado, country=codigo, country_name=nome)
            container.add_item(btn)
        
        view = discord.ui.LayoutView()
        view.add_item(container)
        
        # ENVIA O MENU DE SELEÇÃO
        await interaction.response.send_message(view=view, ephemeral=True)
        log("BUTTON", "Menu de seleção de país enviado")
    
    async def pais_selecionado(self, interaction: discord.Interaction, country: str, country_name: str):
        """Callback quando um país é selecionado"""
        log("BUTTON", f"País {country_name} selecionado por {interaction.user.id}")
        
        # DEFER primeiro para evitar timeout
        await interaction.response.defer(ephemeral=True)
        
        # Busca o número na API
        new_data = await create_new_number(interaction.user.id, country)
        
        if new_data:
            # Salva no Redis
            save_number_session(interaction.guild_id, interaction.user.id, new_data)
            
            # Cria o painel de gerenciamento
            view = NumberManagementView(
                new_data['number'],
                new_data['country'],
                interaction.guild_id,
                interaction.user.id
            )
            
            # Envia o container com os botões
            await interaction.followup.send(view=view, ephemeral=True)
            log("BUTTON", f"Painel de gerenciamento enviado para +{new_data['number']}")
        else:
            await interaction.followup.send(
                view=create_text_only_view(f"❌ Erro ao obter número para {country_name}. Tente novamente."),
                ephemeral=True
            )


class BtnMeuNumero(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="📱 Meu Número",
            style=discord.ButtonStyle.primary,
            custom_id="tempnumber:my_number_main",
            emoji="📱"
        )
        log("BUTTON", "BtnMeuNumero criado")

    async def callback(self, interaction: discord.Interaction):
        log("BUTTON", f"BtnMeuNumero clicado por {interaction.user.id}")
        
        session = get_number_session(interaction.guild_id, interaction.user.id)
        
        if not session:
            await interaction.response.send_message(
                view=create_text_only_view("📞 Você não possui um número ativo. Use 'Obter Número' para criar um!"),
                ephemeral=True
            )
            return
        
        view = NumberManagementView(
            session['number'], 
            session['country'],
            interaction.guild_id, 
            interaction.user.id
        )
        await interaction.response.send_message(view=view, ephemeral=True)


class BtnAjudaNumero(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="❓ Como Funciona",
            style=discord.ButtonStyle.secondary,
            custom_id="tempnumber:help_main",
            emoji="❓"
        )
        log("BUTTON", "BtnAjudaNumero criado")

    async def callback(self, interaction: discord.Interaction):
        log("BUTTON", f"BtnAjudaNumero clicado por {interaction.user.id}")
        
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content="# 📞 Número Temporário - Guia Rápido"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            content="**1. Obter Número** - Clique no botão 'Obter Número' e escolha o país\n\n"
                    "**2. Usar o Número** - Copie o número gerado e use onde precisar\n\n"
                    "**3. Verificar SMS** - Use 'Verificar SMS' para ver mensagens recebidas\n\n"
                    "**4. Gerenciar**\n"
                    "• Informações: Veja detalhes do seu número\n"
                    "• Cancelar: Remove seu número permanentemente\n\n"
                    f"**⚠️ Atenção:** Número expira em {SESSION_DURATION // 60} minutos\n"
                    "• O número é compartilhado com outros usuários\n"
                    "• Funciona para receber SMS de verificação\n\n"
                    "**🌍 Países disponíveis:** US, UK, BR, CA, AU, DE, FR, ES, IT"
        ))
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)


# =========================
# PAINEL PRINCIPAL
# =========================

class PainelNumeroTemp(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        log("VIEW", "PainelNumeroTemp criado")

        container = discord.ui.Container()

        container.add_item(
            discord.ui.TextDisplay(
                content="# 📞 SISTEMA DE NÚMERO TEMPORÁRIO\n"
                        "Obtenha números de telefone para receber SMS anonimamente"
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                content="**✨ Vantagens:**\n"
                        f"• Número válido por {SESSION_DURATION // 60} minutos\n"
                        "• Receba SMS de verificação\n"
                        "• Cancelar quando quiser\n"
                        "• Perfeito para cadastros temporários"
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                content="### 🔒 Privacidade Garantida\n"
                        "• Nenhum dado é armazenado permanentemente\n"
                        "• Números são automaticamente removidos\n"
                        "• Você controla seus dados"
            )
        )
        container.add_item(discord.ui.Separator())

        # Seção Obter Número
        sec_criar = discord.ui.Section(accessory=BtnCriarNumeroTemp())
        sec_criar.add_item(discord.ui.TextDisplay(content="📞 Obter um novo número temporário"))
        container.add_item(sec_criar)

        # Seção Meu Número
        sec_meu_numero = discord.ui.Section(accessory=BtnMeuNumero())
        sec_meu_numero.add_item(discord.ui.TextDisplay(content="📱 Ver/gerenciar seu número atual"))
        container.add_item(sec_meu_numero)

        # Seção Ajuda
        sec_ajuda = discord.ui.Section(accessory=BtnAjudaNumero())
        sec_ajuda.add_item(discord.ui.TextDisplay(content="❓ Ver guia rápido e instruções"))
        container.add_item(sec_ajuda)

        self.add_item(container)


# =========================
# COG PRINCIPAL
# =========================

class TempNumberSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log("INIT", "TempNumberSystem carregado")

    async def cog_load(self):
        self.bot.add_view(PainelNumeroTemp())
        log("INIT", "Views persistentes registradas")

    @discord.app_commands.command(name="enviar_painel_numero", description="📞 Envia o painel de número temporário")
    async def send_panel(self, interaction: discord.Interaction):
        try:
            log("PANEL", f"Enviando painel para {interaction.user}")
            view = PainelNumeroTemp()
            await interaction.response.send_message(view=view)
            log("PANEL", f"Painel enviado com sucesso para {interaction.user}")
        except Exception as e:
            err("PANEL", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro ao enviar painel: {str(e)[:100]}"),
                ephemeral=True
            )



    @commands.command(name="sync", hidden=True)
    @commands.is_owner()
    async def sync_commands(self, ctx):
        """Sincroniza comandos manualmente (apenas dono)"""
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ {len(synced)} comandos sincronizados!")
            log("SYNC", f"Sincronizados {len(synced)} comandos")
        except Exception as e:
            await ctx.send(f"❌ Erro: {e}")
            err("SYNC", e)

    @discord.app_commands.command(name="meu_numero", description="📱 Mostra seu número temporário atual")
    async def my_number(self, interaction: discord.Interaction):
        log("COMMAND", f"meu_numero executado por {interaction.user}")
        session = get_number_session(interaction.guild_id, interaction.user.id)
        
        if not session:
            await interaction.response.send_message(
                view=create_text_only_view("📞 Você não possui um número ativo. Use `/enviar_painel_numero` para criar um!"),
                ephemeral=True
            )
        else:
            view = NumberManagementView(
                session['number'], 
                session['country'],
                interaction.guild_id, 
                interaction.user.id
            )
            await interaction.response.send_message(view=view, ephemeral=True)

    @discord.app_commands.command(name="cancelar_numero", description="🗑️ Cancela seu número temporário")
    async def cancel_number(self, interaction: discord.Interaction):
        log("COMMAND", f"cancelar_numero executado por {interaction.user}")
        session = get_number_session(interaction.guild_id, interaction.user.id)
        
        if not session:
            await interaction.response.send_message(
                view=create_text_only_view("❌ Você não possui um número ativo para cancelar."),
                ephemeral=True
            )
            return
        
        delete_number_session(interaction.guild_id, interaction.user.id)
        
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content="# 🗑️ Número Cancelado"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"O número **+{session['number']}** foi cancelado com sucesso!"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="Use `/enviar_painel_numero` para obter um novo número quando precisar."))
        
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)
        
        log("CANCEL", f"Número +{session['number']} cancelado por {interaction.user}")


async def setup(bot: commands.Bot):
    await bot.add_cog(TempNumberSystem(bot))
    log("SETUP", "✅ TempNumberSystem carregado com sucesso!")