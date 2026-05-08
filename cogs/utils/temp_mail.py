"""
Temporary Email System - Discord Components V2
Sistema de email temporário usando API mail.tm
COM BOTÃO "MEU EMAIL" NO PAINEL PRINCIPAL
"""

import discord
from discord.ext import commands
import aiohttp
import asyncio
from datetime import datetime, timedelta
import traceback
import random
import string

from pool.redis import redis_pool


# =========================
# CONFIGURAÇÃO
# =========================

SESSION_DURATION = 3600 * 6  # 6 horas


# =========================
# LOG
# =========================

def log(tag: str, msg: str):
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}][TempMail:{tag}] {msg}")

def err(tag: str, e: Exception):
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}][TempMail:{tag}:ERROR] {repr(e)}")
    traceback.print_exc()


# =========================
# API DO MAIL.TM
# =========================

class MailTMAPI:
    """Cliente para API do mail.tm"""
    
    BASE_URL = "https://api.mail.tm"
    
    def __init__(self):
        self.session: aiohttp.ClientSession = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def get_domain(self) -> str:
        """Obtém um domínio disponível da API"""
        session = await self._get_session()
        async with session.get(f"{self.BASE_URL}/domains") as resp:
            domains = await resp.json()
            domain_list = domains.get('hydra:member', [])
            if domain_list:
                domain = random.choice(domain_list)['domain']
                log("DOMAIN", f"Domínio obtido: {domain}")
                return domain
        log("DOMAIN", "Usando domínio fallback: mail.tm")
        return "mail.tm"
    
    async def create_account(self, email: str, password: str) -> bool:
        """Cria uma nova conta de email"""
        session = await self._get_session()
        async with session.post(
            f"{self.BASE_URL}/accounts",
            json={"address": email, "password": password}
        ) as resp:
            log("CREATE_ACCOUNT", f"Status: {resp.status} - Email: {email}")
            return resp.status in [200, 201]
    
    async def get_token(self, email: str, password: str) -> str:
        """Obtém token de autenticação"""
        session = await self._get_session()
        async with session.post(
            f"{self.BASE_URL}/token",
            json={"address": email, "password": password}
        ) as resp:
            data = await resp.json()
            return data.get("token")
    
    async def get_messages(self, token: str) -> list:
        """Obtém lista de mensagens"""
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(f"{self.BASE_URL}/messages", headers=headers) as resp:
            data = await resp.json()
            return data.get("hydra:member", [])
    
    async def get_message(self, token: str, message_id: str) -> dict:
        """Obtém uma mensagem específica"""
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(f"{self.BASE_URL}/messages/{message_id}", headers=headers) as resp:
            return await resp.json()
    
    async def delete_account(self, email: str, password: str) -> bool:
        """Deleta a conta de email"""
        try:
            token = await self.get_token(email, password)
            if token:
                session = await self._get_session()
                headers = {"Authorization": f"Bearer {token}"}
                async with session.get(f"{self.BASE_URL}/accounts", headers=headers) as resp:
                    accounts = await resp.json()
                    if accounts.get("hydra:member"):
                        account_id = accounts["hydra:member"][0]["id"]
                        async with session.delete(
                            f"{self.BASE_URL}/accounts/{account_id}",
                            headers=headers
                        ) as del_resp:
                            return del_resp.status == 204
            return False
        except Exception as e:
            log("DELETE", f"Erro: {e}")
            return False
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


# =========================
# REDIS OPERATIONS
# =========================

def get_session_key(guild_id: int, user_id: int) -> str:
    return f"tempmail:{guild_id}:{user_id}"

def get_session(guild_id: int, user_id: int) -> dict:
    return redis_pool.get(get_session_key(guild_id, user_id))

def save_session(guild_id: int, user_id: int, data: dict):
    redis_pool.set(get_session_key(guild_id, user_id), data, ex=SESSION_DURATION)

def delete_session(guild_id: int, user_id: int):
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
# VIEW DE VISUALIZAÇÃO DE MENSAGEM (COM CONTAINER)
# =========================

class MensagemView(discord.ui.LayoutView):
    """View para exibir mensagem completa em um Container"""
    
    def __init__(self, from_addr: str, subject: str, content: str, date: str):
        super().__init__(timeout=120)
        self.from_addr = from_addr
        self.subject = subject
        self.content = content
        self.date = date
        
        self.build_container()
    
    def build_container(self):
        """Constrói o container com a mensagem completa"""
        container = discord.ui.Container()
        container.accent = 0x5865F2
        
        container.add_item(discord.ui.TextDisplay(content=f"# 📧 {self.subject[:50]}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**De:** {self.from_addr}"))
        container.add_item(discord.ui.TextDisplay(content=f"**Data:** {self.date}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="### 📝 Conteúdo da Mensagem"))
        container.add_item(discord.ui.TextDisplay(content=self.content[:1900] if self.content else "*(Sem conteúdo)*"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="🔒 Esta mensagem será apagada em breve."))
        
        self.add_item(container)
    
    @discord.ui.button(label="🔙 Voltar", style=discord.ButtonStyle.secondary, custom_id="tempmail:back", emoji="🔙", row=0)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()
    
    @discord.ui.button(label="📋 Copiar Remetente", style=discord.ButtonStyle.primary, custom_id="tempmail:copy", emoji="📋", row=0)
    async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content=f"**Email do remetente:** `{self.from_addr}`"))
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# =========================
# FUNÇÃO PARA CRIAR EMAIL
# =========================

async def create_new_email(user_id: int) -> dict:
    """Cria um novo email temporário com domínio dinâmico"""
    mail_api = MailTMAPI()
    try:
        domain = await mail_api.get_domain()
        if not domain:
            log("CREATE", "Não foi possível obter domínio")
            return None
        
        username = f"user{user_id}_{int(datetime.utcnow().timestamp())}"
        email = f"{username}@{domain}"
        password = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
        
        log("CREATE", f"📧 Criando email: {email}")
        
        success = await mail_api.create_account(email, password)
        if not success:
            log("CREATE", "❌ Falha ao criar conta")
            return None
        
        token = await mail_api.get_token(email, password)
        if not token:
            log("CREATE", "❌ Falha ao obter token")
            return None
        
        log("CREATE", f"✅ Email criado com sucesso: {email}")
        
        return {
            'email': email,
            'password': password,
            'token': token,
            'domain': domain,
            'created_at': datetime.utcnow().isoformat()
        }
    except Exception as e:
        err("CREATE_EMAIL", e)
        return None
    finally:
        await mail_api.close()


# =========================
# BOTÕES DO PAINEL DE CONTROLE DO EMAIL
# =========================

class BtnVerInbox(discord.ui.Button):
    def __init__(self, email: str, token: str, guild_id: int, user_id: int):
        super().__init__(
            label="📥 Ver Inbox",
            style=discord.ButtonStyle.primary,
            custom_id=f"tempmail:inbox_{user_id}",
            emoji="📥"
        )
        self.email = email
        self.token = token
        self.guild_id = guild_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este painel não pertence a você."), ephemeral=True)
            return

        await interaction.response.defer()
        
        mail_api = MailTMAPI()
        try:
            messages = await mail_api.get_messages(self.token)
            
            if not messages:
                await mail_api.close()
                await interaction.followup.send(view=create_text_only_view("📭 Nenhuma mensagem recebida ainda."), ephemeral=True)
                return
            
            container = discord.ui.Container()
            container.add_item(discord.ui.TextDisplay(content="# 📥 Sua Caixa de Entrada"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(content=f"**Email:** `{self.email}`"))
            container.add_item(discord.ui.TextDisplay(content=f"**Total:** {len(messages)} mensagem(ns)"))
            container.add_item(discord.ui.Separator())
            
            for i, msg in enumerate(messages[:10], 1):
                from_addr = msg.get('from', {}).get('address', 'Desconhecido')
                subject = msg.get('subject', 'Sem assunto')
                created_at = datetime.fromisoformat(msg.get('createdAt', '').replace('Z', '+00:00'))
                date_str = created_at.strftime('%d/%m/%Y %H:%M:%S')
                msg_id = msg.get('id', '')
                
                full_msg = await mail_api.get_message(self.token, msg_id)
                full_content = full_msg.get('text', 'Sem conteúdo')
                
                btn_view = discord.ui.Button(
                    label=f"📖 Ver Msg {i}",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"tempmail:view_{msg_id[:16]}",
                    emoji="📖"
                )
                
                async def view_callback(interaction, frm=from_addr, subj=subject, cont=full_content, dt=date_str):
                    msg_view = MensagemView(frm, subj, cont, dt)
                    await interaction.response.send_message(view=msg_view, ephemeral=True)
                
                btn_view.callback = view_callback
                
                section = discord.ui.Section(accessory=btn_view)
                section.add_item(discord.ui.TextDisplay(
                    content=f"**De:** {from_addr}\n**Assunto:** {subject}\n**Data:** {date_str}"
                ))
                container.add_item(section)
                container.add_item(discord.ui.Separator())
            
            await mail_api.close()
            
            view = discord.ui.LayoutView()
            view.add_item(container)
            await interaction.followup.send(view=view, ephemeral=True)
            
        except Exception as e:
            err("INBOX", e)
            await mail_api.close()
            await interaction.followup.send(view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"), ephemeral=True)


class BtnInfoEmail(discord.ui.Button):
    def __init__(self, email: str, user_id: int):
        super().__init__(
            label="ℹ️ Informações",
            style=discord.ButtonStyle.secondary,
            custom_id=f"tempmail:info_{user_id}",
            emoji="ℹ️"
        )
        self.email = email
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este painel não pertence a você."), ephemeral=True)
            return

        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content="# 📧 Informações do Email"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**Email:** `{self.email}`"))
        container.add_item(discord.ui.TextDisplay(content=f"**Válido por:** {SESSION_DURATION // 3600} horas"))
        container.add_item(discord.ui.TextDisplay(content=f"**Status:** ✅ Ativo"))
        
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)


class BtnCriarNovoEmail(discord.ui.Button):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(
            label="🆕 Criar Novo Email",
            style=discord.ButtonStyle.success,
            custom_id=f"tempmail:new_{user_id}",
            emoji="🆕"
        )
        self.guild_id = guild_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este painel não pertence a você."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        old_session = get_session(self.guild_id, self.user_id)
        if old_session:
            mail_api = MailTMAPI()
            await mail_api.delete_account(old_session['email'], old_session['password'])
            await mail_api.close()
            delete_session(self.guild_id, self.user_id)
        
        new_data = await create_new_email(self.user_id)
        
        if new_data:
            save_session(self.guild_id, self.user_id, new_data)
            view = EmailManagementView(new_data['email'], new_data['token'], self.guild_id, self.user_id)
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.followup.send(view=create_text_only_view("❌ Erro ao criar novo email. Tente novamente."), ephemeral=True)


class BtnDeletarEmail(discord.ui.Button):
    def __init__(self, email: str, password: str, guild_id: int, user_id: int):
        super().__init__(
            label="🗑️ Deletar Email",
            style=discord.ButtonStyle.danger,
            custom_id=f"tempmail:delete_{user_id}",
            emoji="🗑️"
        )
        self.email = email
        self.password = password
        self.guild_id = guild_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Este painel não pertence a você."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        mail_api = MailTMAPI()
        try:
            await mail_api.delete_account(self.email, self.password)
            delete_session(self.guild_id, self.user_id)
            await interaction.followup.send(view=create_text_only_view("🗑️ Email deletado com sucesso!"), ephemeral=True)
        except Exception as e:
            err("DELETE", e)
            delete_session(self.guild_id, self.user_id)
            await interaction.followup.send(view=create_text_only_view("⚠️ Email removido da sessão."), ephemeral=True)
        finally:
            await mail_api.close()


# =========================
# PAINEL DE CONTROLE DO EMAIL
# =========================

class EmailManagementView(discord.ui.LayoutView):
    def __init__(self, email: str, token: str, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        self.email = email
        self.token = token
        self.guild_id = guild_id
        self.user_id = user_id

        container = discord.ui.Container()

        container.add_item(
            discord.ui.TextDisplay(
                content="# 📧 SEU EMAIL TEMPORÁRIO\nGerencie seu email descartável"
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                content=f"**Email:** `{self.email}`\n"
                        f"**Válido por:** {SESSION_DURATION // 3600} horas\n"
                        f"**Status:** ✅ Ativo"
            )
        )
        container.add_item(discord.ui.Separator())

        sec_inbox = discord.ui.Section(accessory=BtnVerInbox(email, token, guild_id, user_id))
        sec_inbox.add_item(discord.ui.TextDisplay(content="📥 Ver mensagens recebidas"))
        container.add_item(sec_inbox)

        sec_info = discord.ui.Section(accessory=BtnInfoEmail(email, user_id))
        sec_info.add_item(discord.ui.TextDisplay(content="ℹ️ Informações do email"))
        container.add_item(sec_info)

        sec_new = discord.ui.Section(accessory=BtnCriarNovoEmail(guild_id, user_id))
        sec_new.add_item(discord.ui.TextDisplay(content="🆕 Criar novo email (deleta o atual)"))
        container.add_item(sec_new)

        sec_delete = discord.ui.Section(accessory=BtnDeletarEmail(email, f"temp_{user_id}", guild_id, user_id))
        sec_delete.add_item(discord.ui.TextDisplay(content="🗑️ Deletar email permanentemente"))
        container.add_item(sec_delete)

        self.add_item(container)


# =========================
# BOTÕES DO PAINEL PRINCIPAL
# =========================

class BtnCriarEmailTemp(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="📧 Criar Email Temporário",
            style=discord.ButtonStyle.success,
            custom_id="tempmail:create_main",
            emoji="📧"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        existing = get_session(interaction.guild_id, interaction.user.id)
        
        if existing:
            view = EmailManagementView(existing['email'], existing['token'], interaction.guild_id, interaction.user.id)
            await interaction.followup.send(view=view, ephemeral=True)
            return
        
        new_data = await create_new_email(interaction.user.id)
        
        if new_data:
            save_session(interaction.guild_id, interaction.user.id, new_data)
            view = EmailManagementView(new_data['email'], new_data['token'], interaction.guild_id, interaction.user.id)
            await interaction.followup.send(view=view, ephemeral=True)
        else:
            await interaction.followup.send(view=create_text_only_view("❌ Erro ao criar email. Tente novamente."), ephemeral=True)


class BtnMeuEmail(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="📬 Meu Email",
            style=discord.ButtonStyle.primary,
            custom_id="tempmail:my_email_main",
            emoji="📬"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        session = get_session(interaction.guild_id, interaction.user.id)
        
        if not session:
            await interaction.followup.send(
                view=create_text_only_view("📧 Você não possui um email ativo. Use 'Criar Email Temporário' para criar um!"),
                ephemeral=True
            )
            return
        
        view = EmailManagementView(session['email'], session['token'], interaction.guild_id, interaction.user.id)
        await interaction.followup.send(view=view, ephemeral=True)


class BtnAjudaEmail(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="❓ Como Funciona",
            style=discord.ButtonStyle.secondary,
            custom_id="tempmail:help_main",
            emoji="❓"
        )

    async def callback(self, interaction: discord.Interaction):
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay(content="# 📧 Email Temporário - Guia Rápido"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            content="**1. Criar Email** - Clique no botão 'Criar Email Temporário'\n\n"
                    "**2. Usar o Email** - Copie o email gerado e use onde precisar\n\n"
                    "**3. Verificar Mensagens** - Use 'Meu Email' ou 'Ver Inbox' para acessar suas mensagens\n\n"
                    "**4. Gerenciar**\n"
                    "• Informações: Veja detalhes do seu email\n"
                    "• Criar Novo: Gera um novo email (deleta o atual)\n"
                    "• Deletar: Remove seu email permanentemente\n\n"
                    f"**⚠️ Atenção:** Email expira em {SESSION_DURATION // 3600} horas\n"
                    "• Seus dados são automaticamente removidos"
        ))
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)


# =========================
# PAINEL PRINCIPAL
# =========================

class PainelEmailTemp(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

        container = discord.ui.Container()

        container.add_item(
            discord.ui.TextDisplay(
                content="# 📧 SISTEMA DE EMAIL TEMPORÁRIO\n"
                        "Crie emails descartáveis para receber mensagens anonimamente"
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                content="**✨ Vantagens:**\n"
                        f"• Email válido por {SESSION_DURATION // 3600} horas\n"
                        "• Receba emails anonimamente\n"
                        "• Delete quando quiser\n"
                        "• Perfeito para cadastros temporários"
            )
        )
        container.add_item(discord.ui.Separator())

        container.add_item(
            discord.ui.TextDisplay(
                content="### 🔒 Privacidade Garantida\n"
                        "• Nenhum dado é armazenado permanentemente\n"
                        "• Emails são automaticamente removidos\n"
                        "• Você controla seus dados"
            )
        )
        container.add_item(discord.ui.Separator())

        # Seção Criar Email
        sec_criar = discord.ui.Section(accessory=BtnCriarEmailTemp())
        sec_criar.add_item(discord.ui.TextDisplay(content="📧 Criar um novo email temporário"))
        container.add_item(sec_criar)

        # Seção Meu Email (NOVO)
        sec_meu_email = discord.ui.Section(accessory=BtnMeuEmail())
        sec_meu_email.add_item(discord.ui.TextDisplay(content="📬 Ver/gerenciar seu email atual"))
        container.add_item(sec_meu_email)

        # Seção Ajuda
        sec_ajuda = discord.ui.Section(accessory=BtnAjudaEmail())
        sec_ajuda.add_item(discord.ui.TextDisplay(content="❓ Ver guia rápido e instruções"))
        container.add_item(sec_ajuda)

        self.add_item(container)


# =========================
# COG PRINCIPAL
# =========================

class TempMailSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log("INIT", "TempMailSystem carregado")

    async def cog_load(self):
        self.bot.add_view(PainelEmailTemp())
        log("INIT", "Views persistentes registradas")

    @discord.app_commands.command(name="enviar_painel_email", description="Envia o painel de email temporário")
    async def send_panel(self, interaction: discord.Interaction):
        try:
            view = PainelEmailTemp()
            await interaction.response.send_message(view=view)
            log("PANEL", f"Painel enviado por {interaction.user}")
        except Exception as e:
            err("PANEL", e)
            await interaction.response.send_message(view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"), ephemeral=True)

    @discord.app_commands.command(name="meu_email", description="Mostra seu email temporário atual")
    async def my_email(self, interaction: discord.Interaction):
        session = get_session(interaction.guild_id, interaction.user.id)
        
        if not session:
            await interaction.response.send_message(
                view=create_text_only_view("📧 Você não possui um email ativo. Use `/enviar_painel_email` para criar um!"),
                ephemeral=True
            )
        else:
            view = EmailManagementView(session['email'], session['token'], interaction.guild_id, interaction.user.id)
            await interaction.response.send_message(view=view, ephemeral=True)

    @discord.app_commands.command(name="deletar_email", description="Deleta seu email temporário")
    async def delete_my_email(self, interaction: discord.Interaction):
        session = get_session(interaction.guild_id, interaction.user.id)
        
        if not session:
            await interaction.response.send_message(view=create_text_only_view("❌ Nenhum email ativo."), ephemeral=True)
            return
        
        mail_api = MailTMAPI()
        try:
            await mail_api.delete_account(session['email'], session['password'])
            delete_session(interaction.guild_id, interaction.user.id)
            await interaction.response.send_message(view=create_text_only_view("🗑️ Email deletado com sucesso!"), ephemeral=True)
        except Exception as e:
            err("DELETE_CMD", e)
            delete_session(interaction.guild_id, interaction.user.id)
            await interaction.response.send_message(view=create_text_only_view("⚠️ Email removido da sessão."), ephemeral=True)
        finally:
            await mail_api.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(TempMailSystem(bot))
    log("SETUP", "✅ TempMailSystem carregado!")