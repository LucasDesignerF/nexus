"""
Ticket System - Discord Components V2
Sistema completo de tickets com UI moderna, persistente e seguro
Com transcripts via GitHub Gist
"""

import asyncio
import aiohttp
import os
from datetime import datetime
import traceback
import logging
import json
from typing import Optional, List, Dict, Any, Tuple

import discord
from discord.ext import commands

from pool.redis import redis_pool
from pool.connection import mongo_pool


# =========================
# LOGGING AVANÇADO
# =========================

class ColoredFormatter(logging.Formatter):
    """Formatter com cores para console"""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Ciano
        'INFO': '\033[92m',      # Verde
        'WARNING': '\033[93m',    # Amarelo
        'ERROR': '\033[91m',     # Vermelho
        'CRITICAL': '\033[95m',   # Magenta
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)


def setup_logging():
    """Configura sistema de logging avançado"""
    
    # Criar logger principal
    ticket_logger = logging.getLogger('TicketSystem')
    ticket_logger.setLevel(logging.DEBUG)
    
    # Limpar handlers existentes
    if ticket_logger.handlers:
        ticket_logger.handlers.clear()
    
    # Handler para console com cores
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_format = ColoredFormatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    ticket_logger.addHandler(console_handler)
    
    # Handler para arquivo (logs detalhados)
    try:
        file_handler = logging.FileHandler('logs/ticket_system.log', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        ticket_logger.addHandler(file_handler)
    except Exception as e:
        print(f"⚠️ Não foi possível criar arquivo de log: {e}")
    
    # Handler para erros separado
    try:
        error_handler = logging.FileHandler('logs/ticket_errors.log', encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(error_format)
        ticket_logger.addHandler(error_handler)
    except Exception as e:
        print(f"⚠️ Não foi possível criar arquivo de erros: {e}")
    
    return ticket_logger


# Criar pasta de logs se não existir
os.makedirs('logs', exist_ok=True)

# Inicializar logging
logger = setup_logging()


def log_event(event_type: str, guild_id: int, user_id: int, details: dict = None):
    """Registra evento no log estruturado"""
    log_data = {
        'event': event_type,
        'guild_id': guild_id,
        'user_id': user_id,
        'timestamp': datetime.utcnow().isoformat(),
        'details': details or {}
    }
    
    # Log no arquivo JSON (para análise posterior)
    try:
        with open('logs/ticket_events.json', 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_data) + '\n')
    except Exception:
        pass
    
    # Log no console
    logger.info(f"[{event_type}] Guild:{guild_id} User:{user_id} - {details}")


class MetricsCollector:
    """Coletor de métricas do sistema de tickets"""
    
    def __init__(self):
        self.metrics = {
            'total_tickets_created': 0,
            'total_tickets_closed': 0,
            'tickets_by_category': {},
            'average_response_time': [],
            'average_close_time': []
        }
    
    def ticket_created(self, category: str):
        self.metrics['total_tickets_created'] += 1
        self.metrics['tickets_by_category'][category] = self.metrics['tickets_by_category'].get(category, 0) + 1
    
    def ticket_closed(self, created_at: datetime, closed_at: datetime):
        self.metrics['total_tickets_closed'] += 1
        duration = (closed_at - created_at).total_seconds()
        self.metrics['average_close_time'].append(duration)
    
    def get_stats(self) -> dict:
        avg_close = sum(self.metrics['average_close_time']) / len(self.metrics['average_close_time']) if self.metrics['average_close_time'] else 0
        return {
            'total_created': self.metrics['total_tickets_created'],
            'total_closed': self.metrics['total_tickets_closed'],
            'open_tickets': self.metrics['total_tickets_created'] - self.metrics['total_tickets_closed'],
            'tickets_by_category': self.metrics['tickets_by_category'],
            'avg_close_time_minutes': round(avg_close / 60, 2)
        }


metrics = MetricsCollector()


class PerformanceTimer:
    """Context manager para medir tempo de execução"""
    
    def __init__(self, operation: str):
        self.operation = operation
        self.start_time = None
    
    async def __aenter__(self):
        self.start_time = datetime.utcnow()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.utcnow() - self.start_time).total_seconds()
        if exc_type:
            logger.error(f"[PERFORMANCE] {self.operation} falhou após {duration:.2f}s")
        else:
            logger.debug(f"[PERFORMANCE] {self.operation} concluído em {duration:.2f}s")


# =========================
# CONFIGURAÇÃO
# =========================

TICKET_TIMEOUT = 86400 * 7  # 7 dias para histórico
MAX_TICKETS_PER_USER = 3  # Máximo de tickets ativos por usuário

# GitHub Gist Configuration (adicione no .env)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")


# =========================
# LOG
# =========================

def log(tag: str, msg: str):
    logger.info(f"[{tag}] {msg}")

def err(tag: str, e: Exception):
    logger.error(f"[{tag}] {repr(e)}")
    traceback.print_exc()


# =========================
# REDIS/MONGODB OPERATIONS
# =========================

def get_config_key(guild_id: int) -> str:
    return f"ticket_config:{guild_id}"

def get_ticket_key(ticket_id: str) -> str:
    return f"ticket:{ticket_id}"

def get_user_tickets_key(guild_id: int, user_id: int) -> str:
    return f"user_tickets:{guild_id}:{user_id}"

def save_config(guild_id: int, config: dict):
    """Salva configuração do sistema de tickets"""
    try:
        key = get_config_key(guild_id)
        redis_pool.set(key, json.dumps(config), ex=None)
        
        from pool.connection import mongo_pool
        col = mongo_pool.get_collection("ticket_config")
        col.update_one({"guild_id": guild_id}, {"$set": config}, upsert=True)
        
        log("CONFIG", f"Config salva para guild {guild_id}")
    except Exception as e:
        err("SAVE_CONFIG", e)

def get_config(guild_id: int) -> dict:
    """Obtém configuração do sistema de tickets"""
    try:
        key = get_config_key(guild_id)
        data = redis_pool.get(key)
        if data:
            return json.loads(data) if isinstance(data, str) else data
        
        from pool.connection import mongo_pool
        col = mongo_pool.get_collection("ticket_config")
        config = col.find_one({"guild_id": guild_id}) or {}
        if config:
            config.pop("_id", None)
            redis_pool.set(key, json.dumps(config), ex=None)
        return config
    except Exception as e:
        err("GET_CONFIG", e)
        return {}

def save_ticket(guild_id: int, ticket_data: dict):
    """Salva dados do ticket"""
    try:
        ticket_id = ticket_data.get('ticket_id')
        key = get_ticket_key(ticket_id)
        redis_pool.set(key, json.dumps(ticket_data), ex=TICKET_TIMEOUT)
        
        user_key = get_user_tickets_key(guild_id, ticket_data['user_id'])
        redis_pool.sadd(user_key, ticket_id)
        redis_pool.expire(user_key, TICKET_TIMEOUT)
        
        log("TICKET", f"Ticket {ticket_id} salvo")
    except Exception as e:
        err("SAVE_TICKET", e)

def get_ticket(ticket_id: str) -> dict:
    """Obtém dados do ticket"""
    try:
        key = get_ticket_key(ticket_id)
        data = redis_pool.get(key)
        if data:
            return json.loads(data) if isinstance(data, str) else data
        return {}
    except Exception as e:
        err("GET_TICKET", e)
        return {}

def delete_ticket(ticket_id: str, guild_id: int, user_id: int):
    """Remove ticket do Redis"""
    try:
        redis_pool.delete(get_ticket_key(ticket_id))
        user_key = get_user_tickets_key(guild_id, user_id)
        redis_pool.srem(user_key, ticket_id)
        log("TICKET", f"Ticket {ticket_id} removido")
    except Exception as e:
        err("DELETE_TICKET", e)

def get_user_active_tickets(guild_id: int, user_id: int) -> int:
    """Retorna número de tickets ativos do usuário"""
    try:
        user_key = get_user_tickets_key(guild_id, user_id)
        return redis_pool.scard(user_key) or 0
    except Exception as e:
        err("USER_TICKETS", e)
        return 0


# =========================
# TRANSCRIPT SYSTEM - GITHUB GIST
# =========================

class TranscriptGenerator:
    """Gera HTML transcripts e envia para GitHub Gist"""
    
    HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcript - Ticket #{ticket_id}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: #36393f;
            color: #dcddde;
            line-height: 1.5;
            padding: 20px;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: #2f3136;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
        }}
        .header {{
            background: #202225;
            padding: 20px;
            border-bottom: 1px solid #292b2f;
        }}
        .header h1 {{ font-size: 24px; margin-bottom: 10px; color: #fff; }}
        .header-info {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            font-size: 14px;
            color: #b9bbbe;
        }}
        .header-info .info-item {{
            background: #2f3136;
            padding: 8px 12px;
            border-radius: 6px;
        }}
        .header-info .info-item strong {{ color: #fff; }}
        .messages {{ padding: 20px; }}
        .message {{
            display: flex;
            margin-bottom: 16px;
            padding: 8px;
            border-radius: 8px;
            transition: background 0.2s;
        }}
        .message:hover {{ background: #2a2c30; }}
        .avatar {{
            width: 40px;
            height: 40px;
            border-radius: 50%;
            margin-right: 16px;
            flex-shrink: 0;
            background: #5865f2;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            color: white;
        }}
        .message-content {{ flex: 1; }}
        .message-header {{
            display: flex;
            align-items: baseline;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 4px;
        }}
        .author-name {{ font-weight: 600; color: #fff; }}
        .timestamp {{ font-size: 12px; color: #72767d; }}
        .message-text {{ color: #dcddde; word-wrap: break-word; }}
        .message-text code {{ background: #2d2f33; padding: 2px 5px; border-radius: 4px; font-family: monospace; }}
        .message-text pre {{ background: #2d2f33; padding: 10px; border-radius: 6px; overflow-x: auto; margin-top: 8px; }}
        .system-message {{
            background: #2f3136;
            border-left: 4px solid #5865f2;
            padding: 12px;
            margin: 16px 0;
            border-radius: 6px;
            color: #b9bbbe;
            font-style: italic;
        }}
        .staff-badge {{
            background: #5865f2;
            color: white;
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 12px;
            margin-left: 8px;
        }}
        .footer {{
            background: #202225;
            padding: 16px 20px;
            text-align: center;
            font-size: 12px;
            color: #72767d;
            border-top: 1px solid #292b2f;
        }}
        .footer a {{ color: #5865f2; text-decoration: none; }}
        hr {{ border: none; border-top: 1px solid #292b2f; margin: 16px 0; }}
        @media (max-width: 600px) {{
            .message {{ flex-direction: column; }}
            .avatar {{ margin-bottom: 8px; }}
            .header-info {{ flex-direction: column; gap: 8px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📜 Transcript do Ticket #{ticket_id}</h1>
            <div class="header-info">
                <div class="info-item"><strong>📌 ID:</strong> #{ticket_id}</div>
                <div class="info-item"><strong>👤 Criador:</strong> {creator_name} ({creator_id})</div>
                <div class="info-item"><strong>📅 Abertura:</strong> {created_at}</div>
                <div class="info-item"><strong>🔒 Fechamento:</strong> {closed_at}</div>
                <div class="info-item"><strong>📊 Total de mensagens:</strong> {total_messages}</div>
                <div class="info-item"><strong>🧑‍💼 Atendente:</strong> {assigned_to}</div>
                <div class="info-item"><strong>🏷️ Categoria:</strong> {category}</div>
            </div>
        </div>
        <div class="messages">
            {messages_html}
        </div>
        <div class="footer">
            <p>🔒 Transcript gerado automaticamente pelo Sistema de Tickets • {generated_at}</p>
            <p>💾 Este arquivo é público e pode ser compartilhado</p>
        </div>
    </div>
</body>
</html>'''
    
    MESSAGE_HTML = '<div class="message {message_class}"><div class="avatar" style="background: {avatar_color};">{avatar_letter}</div><div class="message-content"><div class="message-header"><span class="author-name">{author_name}{staff_badge}</span><span class="timestamp">{timestamp}</span></div><div class="message-text">{message_text}</div></div></div>'
    
    SYSTEM_MESSAGE_HTML = '<div class="system-message">🤖 <strong>Sistema</strong> • {timestamp}<br>{message_text}</div>'
    
    @staticmethod
    def get_avatar_color(user_id: int) -> str:
        colors = ["#5865F2", "#57F287", "#FEE75C", "#ED4245", "#EB459E", "#F47FFF", "#E67E22", "#1ABC9C", "#3498DB", "#9B59B6"]
        return colors[user_id % len(colors)]
    
    @staticmethod
    def get_avatar_letter(name: str) -> str:
        return name[0].upper() if name else "?"
    
    @classmethod
    async def collect_messages(cls, channel: discord.TextChannel, staff_role_id: int = None) -> List[Dict]:
        """Coleta todas as mensagens do canal"""
        messages = []
        staff_ids = set()
        
        if staff_role_id:
            role = channel.guild.get_role(staff_role_id)
            if role:
                staff_ids = {member.id for member in role.members}
        
        async for msg in channel.history(limit=500, oldest_first=True):
            is_staff = msg.author.id in staff_ids or msg.author.guild_permissions.administrator
            
            messages.append({
                'id': msg.id,
                'author_id': msg.author.id,
                'author_name': msg.author.display_name,
                'content': msg.content or "*[Sem conteúdo textuais]*",
                'timestamp': msg.created_at,
                'is_staff': is_staff,
                'is_system': msg.author.bot
            })
        
        return messages
    
    @classmethod
    async def generate_html(cls, channel: discord.TextChannel, ticket_data: dict, closed_by: discord.Member) -> str:
        """Gera o HTML do transcript"""
        ticket_id = ticket_data.get('ticket_id', '???')
        created_at = datetime.fromisoformat(ticket_data.get('created_at', datetime.utcnow().isoformat()))
        closed_at = datetime.utcnow()
        
        staff_role_id = ticket_data.get('staff_role_id')
        messages = await cls.collect_messages(channel, staff_role_id)
        
        messages_html = ""
        
        for msg in messages:
            if msg['is_system']:
                messages_html += cls.SYSTEM_MESSAGE_HTML.format(
                    timestamp=msg['timestamp'].strftime('%d/%m/%Y %H:%M:%S'),
                    message_text=msg['content'][:500]
                )
            else:
                staff_badge = ' <span class="staff-badge">STAFF</span>' if msg['is_staff'] else ''
                message_class = 'staff-message' if msg['is_staff'] else 'user-message'
                
                messages_html += cls.MESSAGE_HTML.format(
                    message_class=message_class,
                    avatar_color=cls.get_avatar_color(msg['author_id']),
                    avatar_letter=cls.get_avatar_letter(msg['author_name']),
                    author_name=msg['author_name'],
                    staff_badge=staff_badge,
                    timestamp=msg['timestamp'].strftime('%d/%m/%Y %H:%M:%S'),
                    message_text=msg['content'][:1000].replace('`', '´')
                )
        
        assigned_to = f"<@{ticket_data.get('assigned_to')}>" if ticket_data.get('assigned_to') else "Não assumido"
        
        return cls.HTML_TEMPLATE.format(
            ticket_id=ticket_id,
            creator_name=channel.guild.get_member(ticket_data['user_id']).display_name if channel.guild.get_member(ticket_data['user_id']) else "Desconhecido",
            creator_id=ticket_data['user_id'],
            created_at=created_at.strftime('%d/%m/%Y %H:%M:%S'),
            closed_at=closed_at.strftime('%d/%m/%Y %H:%M:%S'),
            total_messages=len(messages),
            assigned_to=assigned_to,
            category=ticket_data.get('category', 'Geral'),
            messages_html=messages_html,
            generated_at=closed_at.strftime('%d/%m/%Y %H:%M:%S')
        )
    
    @classmethod
    async def upload_to_gist(cls, html_content: str, ticket_id: str) -> Optional[str]:
        """Faz upload do HTML para GitHub Gist"""
        if not GITHUB_TOKEN or not GITHUB_USERNAME:
            log("GIST", "⚠️ GitHub token não configurado. Usando fallback local.")
            return None
        
        filename = f"transcript_ticket_{ticket_id}.html"
        
        payload = {
            "description": f"Transcript do Ticket #{ticket_id} - Sistema de Tickets Discord",
            "public": True,
            "files": {
                filename: {
                    "content": html_content
                }
            }
        }
        
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.github.com/gists", json=payload, headers=headers) as resp:
                    if resp.status in [200, 201]:
                        data = await resp.json()
                        gist_url = data.get("html_url")
                        log("GIST", f"✅ Transcript enviado: {gist_url}")
                        return gist_url
                    else:
                        text = await resp.text()
                        log("GIST", f"❌ Erro {resp.status}: {text}")
                        return None
        except Exception as e:
            err("GIST_UPLOAD", e)
            return None


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
# VIEW DE AVALIAÇÃO - VERSÃO CORRIGIDA (EMOJIS VÁLIDOS)
# =========================

class AvaliacaoView(discord.ui.LayoutView):
    def __init__(self, ticket_id: str, user_id: int, staff_id: int):
        super().__init__(timeout=300)
        self.ticket_id = ticket_id
        self.user_id = user_id
        self.staff_id = staff_id
        self.build_view()
    
    def build_view(self):
        # Container com o texto
        container = discord.ui.Container()
        container.accent = 0x5865F2
        container.add_item(discord.ui.TextDisplay(content="# ⭐ AVALIE O ATENDIMENTO"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="Como você avalia o atendimento recebido?"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**Ticket:** #{self.ticket_id}"))
        self.add_item(container)
        
        # LINHA 0 - 3 botões
        row0 = discord.ui.ActionRow()
        
        btn_1 = discord.ui.Button(
            label="1 - Muito Ruim",
            style=discord.ButtonStyle.danger,
            custom_id=f"rate_1_{self.ticket_id[:8]}",
            emoji="⭐"
        )
        btn_1.callback = lambda i: self.process_rating(i, 1)
        row0.add_item(btn_1)
        
        btn_2 = discord.ui.Button(
            label="2 - Ruim",
            style=discord.ButtonStyle.danger,
            custom_id=f"rate_2_{self.ticket_id[:8]}",
            emoji="⭐"
        )
        btn_2.callback = lambda i: self.process_rating(i, 2)
        row0.add_item(btn_2)
        
        btn_3 = discord.ui.Button(
            label="3 - Regular",
            style=discord.ButtonStyle.secondary,
            custom_id=f"rate_3_{self.ticket_id[:8]}",
            emoji="⭐"
        )
        btn_3.callback = lambda i: self.process_rating(i, 3)
        row0.add_item(btn_3)
        
        self.add_item(row0)
        
        # LINHA 1 - 2 botões
        row1 = discord.ui.ActionRow()
        
        btn_4 = discord.ui.Button(
            label="4 - Bom",
            style=discord.ButtonStyle.primary,
            custom_id=f"rate_4_{self.ticket_id[:8]}",
            emoji="⭐"
        )
        btn_4.callback = lambda i: self.process_rating(i, 4)
        row1.add_item(btn_4)
        
        btn_5 = discord.ui.Button(
            label="5 - Excelente",
            style=discord.ButtonStyle.success,
            custom_id=f"rate_5_{self.ticket_id[:8]}",
            emoji="⭐"
        )
        btn_5.callback = lambda i: self.process_rating(i, 5)
        row1.add_item(btn_5)
        
        self.add_item(row1)
    
    async def process_rating(self, interaction: discord.Interaction, rating: int):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(view=create_text_only_view("❌ Esta avaliação não pertence a você."), ephemeral=True)
            return
        
        rating_texts = {1: "Muito Ruim", 2: "Ruim", 3: "Regular", 4: "Bom", 5: "Excelente"}
        
        # CORRIGIDO: Usar review_channel, não log_channel
        config = get_config(interaction.guild_id)
        review_channel_id = config.get('review_channel')  # Mudado de log_channel para review_channel
        
        # Registrar avaliação no canal de avaliações
        if review_channel_id:
            channel = interaction.guild.get_channel(review_channel_id)
            if channel:
                log_container = discord.ui.Container()
                log_container.accent = 0x57F287 if rating >= 4 else 0xED4245
                log_container.add_item(discord.ui.TextDisplay(content="# ⭐ NOVA AVALIAÇÃO"))
                log_container.add_item(discord.ui.Separator())
                log_container.add_item(discord.ui.TextDisplay(content=f"**Ticket:** {self.ticket_id}"))
                log_container.add_item(discord.ui.TextDisplay(content=f"**Usuário:** {interaction.user.mention}"))
                log_container.add_item(discord.ui.TextDisplay(content=f"**Atendente:** <@{self.staff_id}>"))
                log_container.add_item(discord.ui.TextDisplay(content=f"**Nota:** {rating} estrelas ({rating_texts[rating]})"))
                
                log_view = discord.ui.LayoutView()
                log_view.add_item(log_container)
                await channel.send(view=log_view)
                logger.info(f"✅ Avaliação enviada para o canal de avaliações: {rating} estrelas")
            else:
                logger.warning(f"⚠️ Canal de avaliações não encontrado: {review_channel_id}")
        else:
            logger.warning("⚠️ Nenhum canal de avaliações configurado")
        
        # Responder ao usuário na DM (CORRIGIDO: usar followup ou response adequadamente)
        result_container = discord.ui.Container()
        result_container.accent = 0x57F287
        result_container.add_item(discord.ui.TextDisplay(content=f"✅ Obrigado pela avaliação!\n\n**Sua nota:** {rating} estrelas ({rating_texts[rating]})\n\n⭐ Agradecemos o feedback!"))
        result_view = discord.ui.LayoutView()
        result_view.add_item(result_container)
        
        # Enviar resposta e fechar a mensagem original
        await interaction.response.send_message(view=result_view, ephemeral=True)
        
        logger.info(f"Avaliação recebida: Ticket {self.ticket_id} - Nota {rating} estrelas")


# =========================
# STAFF PANEL (EPHEMERAL) - VERSÃO COMPLETA
# =========================

class StaffPanelView(discord.ui.LayoutView):
    def __init__(self, ticket_id: str, channel_id: int, user_id: int, staff_role_id: int):
        super().__init__(timeout=120)
        self.ticket_id = ticket_id
        self.channel_id = channel_id
        self.user_id = user_id
        self.staff_role_id = staff_role_id
        
        self.ticket_data = get_ticket(ticket_id) or {}
        self.build_view()
    
    def build_view(self):
        # Container com informações
        container = discord.ui.Container()
        container.accent = 0x5865F2
        
        container.add_item(discord.ui.TextDisplay(content="# 🛠️ PAINEL STAFF - INFORMAÇÕES DO TICKET"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**📌 Ticket ID:** {self.ticket_id}"))
        container.add_item(discord.ui.TextDisplay(content=f"**👤 Usuário:** <@{self.user_id}>"))
        
        assigned_to = self.ticket_data.get('assigned_to')
        if assigned_to:
            container.add_item(discord.ui.TextDisplay(content=f"**🧑‍💼 Atendente:** <@{assigned_to}>"))
        else:
            container.add_item(discord.ui.TextDisplay(content=f"**🧑‍💼 Atendente:** ❌ Ninguém assumiu ainda"))
        
        category = self.ticket_data.get('category', 'Desconhecida')
        container.add_item(discord.ui.TextDisplay(content=f"**🏷️ Categoria:** {category}"))
        
        created_at = self.ticket_data.get('created_at')
        if created_at:
            try:
                created_date = datetime.fromisoformat(created_at)
                container.add_item(discord.ui.TextDisplay(content=f"**📅 Criado em:** {created_date.strftime('%d/%m/%Y %H:%M:%S')}"))
            except:
                container.add_item(discord.ui.TextDisplay(content=f"**📅 Criado em:** {created_at}"))
        
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="**📋 Ações disponíveis:**"))
        
        self.add_item(container)
        
        # Criar Action Row para os botões (como no TicketChannelView)
        # LINHA 0
        row0 = discord.ui.ActionRow()
        
        btn_ban = discord.ui.Button(
            label="🔒 Bloquear Usuário",
            style=discord.ButtonStyle.danger,
            custom_id=f"staff_ban_{self.ticket_id[:8]}",
            emoji="🔒"
        )
        btn_ban.callback = self.ban_user
        row0.add_item(btn_ban)
        
        btn_warn = discord.ui.Button(
            label="⚠️ Advertência",
            style=discord.ButtonStyle.danger,
            custom_id=f"staff_warn_{self.ticket_id[:8]}",
            emoji="⚠️"
        )
        btn_warn.callback = self.warn_user
        row0.add_item(btn_warn)
        
        btn_info = discord.ui.Button(
            label="📋 Informações",
            style=discord.ButtonStyle.primary,
            custom_id=f"staff_info_{self.ticket_id[:8]}",
            emoji="📋"
        )
        btn_info.callback = self.user_info
        row0.add_item(btn_info)
        
        self.add_item(row0)
        
        # LINHA 1
        row1 = discord.ui.ActionRow()
        
        btn_stats = discord.ui.Button(
            label="📊 Estatísticas",
            style=discord.ButtonStyle.secondary,
            custom_id=f"staff_stats_{self.ticket_id[:8]}",
            emoji="📊"
        )
        btn_stats.callback = self.ticket_stats
        row1.add_item(btn_stats)
        
        btn_note = discord.ui.Button(
            label="📝 Nota Interna",
            style=discord.ButtonStyle.secondary,
            custom_id=f"staff_note_{self.ticket_id[:8]}",
            emoji="📝"
        )
        btn_note.callback = self.add_note
        row1.add_item(btn_note)
        
        btn_transfer = discord.ui.Button(
            label="🔁 Transferir",
            style=discord.ButtonStyle.primary,
            custom_id=f"staff_transfer_{self.ticket_id[:8]}",
            emoji="🔁"
        )
        btn_transfer.callback = self.transfer_ticket
        row1.add_item(btn_transfer)
        
        self.add_item(row1)
        
        # LINHA 2
        row2 = discord.ui.ActionRow()
        
        btn_history = discord.ui.Button(
            label="📜 Histórico",
            style=discord.ButtonStyle.secondary,
            custom_id=f"staff_history_{self.ticket_id[:8]}",
            emoji="📜"
        )
        btn_history.callback = self.view_history
        row2.add_item(btn_history)
        
        btn_close = discord.ui.Button(
            label="🔙 Fechar",
            style=discord.ButtonStyle.secondary,
            custom_id=f"staff_close_{self.ticket_id[:8]}",
            emoji="🔙"
        )
        btn_close.callback = self.close_panel
        row2.add_item(btn_close)
        
        self.add_item(row2)
    
    # Todos os callbacks permanecem iguais, apenas sem o decorator
    async def ban_user(self, interaction: discord.Interaction):
        if not self.has_staff_role(interaction):
            await interaction.response.send_message(view=create_text_only_view("❌ Você não tem permissão para isso."), ephemeral=True)
            return
        modal = BanConfirmModal(self.user_id, self.ticket_id)
        await interaction.response.send_modal(modal)
    
    async def warn_user(self, interaction: discord.Interaction):
        if not self.has_staff_role(interaction):
            await interaction.response.send_message(view=create_text_only_view("❌ Você não tem permissão para isso."), ephemeral=True)
            return
        modal = WarnModal(self.user_id, self.ticket_id)
        await interaction.response.send_modal(modal)
    
    async def user_info(self, interaction: discord.Interaction):
        if not self.has_staff_role(interaction):
            await interaction.response.send_message(view=create_text_only_view("❌ Você não tem permissão para isso."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        if member:
            info_container = discord.ui.Container()
            info_container.accent = 0x5865F2
            info_container.add_item(discord.ui.TextDisplay(content="# 📋 INFORMAÇÕES DO USUÁRIO"))
            info_container.add_item(discord.ui.Separator())
            info_container.add_item(discord.ui.TextDisplay(content=f"**Nome:** {member.display_name}"))
            info_container.add_item(discord.ui.TextDisplay(content=f"**ID:** {member.id}"))
            info_container.add_item(discord.ui.TextDisplay(content=f"**Entrou:** {discord.utils.format_dt(member.joined_at, 'R') if member.joined_at else 'N/A'}"))
            info_container.add_item(discord.ui.TextDisplay(content=f"**Conta criada:** {discord.utils.format_dt(member.created_at, 'R')}"))
            roles = [role.mention for role in member.roles if role.name != "@everyone"]
            if roles:
                roles_text = ", ".join(roles[:5])
                if len(roles) > 5:
                    roles_text += f" e +{len(roles)-5}"
                info_container.add_item(discord.ui.TextDisplay(content=f"**Cargos:** {roles_text}"))
            info_container.add_item(discord.ui.Separator())
            info_container.add_item(discord.ui.TextDisplay(content=f"**Ticket:** #{self.ticket_id}"))
            info_view = discord.ui.LayoutView()
            info_view.add_item(info_container)
            await interaction.followup.send(view=info_view, ephemeral=True)
        else:
            await interaction.followup.send(view=create_text_only_view("❌ Usuário não encontrado."), ephemeral=True)
    
    async def ticket_stats(self, interaction: discord.Interaction):
        if not self.has_staff_role(interaction):
            await interaction.response.send_message(view=create_text_only_view("❌ Você não tem permissão para isso."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        channel = interaction.guild.get_channel(self.channel_id)
        message_count = 0
        if channel:
            async for _ in channel.history(limit=None):
                message_count += 1
        created_at = self.ticket_data.get('created_at')
        duration = "Desconhecido"
        if created_at:
            try:
                created_date = datetime.fromisoformat(created_at)
                delta = datetime.utcnow() - created_date
                hours = int(delta.total_seconds() // 3600)
                minutes = int((delta.total_seconds() % 3600) // 60)
                duration = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            except:
                pass
        stats_container = discord.ui.Container()
        stats_container.accent = 0x5865F2
        stats_container.add_item(discord.ui.TextDisplay(content="# 📊 ESTATÍSTICAS"))
        stats_container.add_item(discord.ui.Separator())
        stats_container.add_item(discord.ui.TextDisplay(content=f"**Mensagens:** {message_count}"))
        stats_container.add_item(discord.ui.TextDisplay(content=f"**Tempo de vida:** {duration}"))
        stats_container.add_item(discord.ui.TextDisplay(content=f"**Criador:** <@{self.user_id}>"))
        assigned_to = self.ticket_data.get('assigned_to')
        if assigned_to:
            stats_container.add_item(discord.ui.TextDisplay(content=f"**Atendente:** <@{assigned_to}>"))
        stats_container.add_item(discord.ui.TextDisplay(content=f"**Categoria:** {self.ticket_data.get('category', 'Desconhecida')}"))
        stats_view = discord.ui.LayoutView()
        stats_view.add_item(stats_container)
        await interaction.followup.send(view=stats_view, ephemeral=True)
    
    async def add_note(self, interaction: discord.Interaction):
        if not self.has_staff_role(interaction):
            await interaction.response.send_message(view=create_text_only_view("❌ Você não tem permissão para isso."), ephemeral=True)
            return
        modal = NoteModal(self.ticket_id)
        await interaction.response.send_modal(modal)
    
    async def transfer_ticket(self, interaction: discord.Interaction):
        if not self.has_staff_role(interaction):
            await interaction.response.send_message(view=create_text_only_view("❌ Você não tem permissão para isso."), ephemeral=True)
            return
        guild = interaction.guild
        staff_role = guild.get_role(self.staff_role_id)
        if not staff_role:
            await interaction.response.send_message(view=create_text_only_view("❌ Cargo de staff não encontrado."), ephemeral=True)
            return
        options = []
        for member in staff_role.members:
            if member.id != interaction.user.id:
                options.append(discord.SelectOption(label=member.display_name[:25], value=str(member.id), emoji="👤"))
        if not options:
            await interaction.response.send_message(view=create_text_only_view("❌ Nenhum staff disponível."), ephemeral=True)
            return
        select = discord.ui.Select(placeholder="Selecione o staff", options=options[:25], custom_id="transfer_select")
        async def select_callback(select_interaction: discord.Interaction):
            new_staff_id = int(select.values[0])
            ticket_data = get_ticket(self.ticket_id)
            old_staff = ticket_data.get('assigned_to')
            ticket_data['assigned_to'] = new_staff_id
            save_ticket(interaction.guild_id, ticket_data)
            new_staff = guild.get_member(new_staff_id)
            if new_staff:
                notify_container = discord.ui.Container()
                notify_container.accent = 0x5865F2
                notify_container.add_item(discord.ui.TextDisplay(content="# 🔄 TRANSFERÊNCIA"))
                notify_container.add_item(discord.ui.Separator())
                notify_container.add_item(discord.ui.TextDisplay(content=f"Ticket **#{self.ticket_id}** transferido por {interaction.user.mention}"))
                notify_container.add_item(discord.ui.TextDisplay(content=f"📁 Canal: <#{self.channel_id}>"))
                notify_view = discord.ui.LayoutView()
                notify_view.add_item(notify_container)
                await new_staff.send(view=notify_view)
            await select_interaction.response.send_message(view=create_text_only_view(f"✅ Transferido para <@{new_staff_id}>!"), ephemeral=True)
            channel = guild.get_channel(self.channel_id)
            if channel:
                await channel.send(view=create_text_only_view(f"🔄 Ticket transferido de <@{old_staff}> para <@{new_staff_id}>"))
        select.callback = select_callback
        view = discord.ui.LayoutView()
        view.add_item(select)
        await interaction.response.send_message(view=view, ephemeral=True)
    
    async def view_history(self, interaction: discord.Interaction):
        if not self.has_staff_role(interaction):
            await interaction.response.send_message(view=create_text_only_view("❌ Você não tem permissão para isso."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        history_key = f"ticket_history:{self.ticket_id}"
        history_data = redis_pool.get(history_key)
        history_container = discord.ui.Container()
        history_container.accent = 0x5865F2
        history_container.add_item(discord.ui.TextDisplay(content="# 📜 HISTÓRICO"))
        history_container.add_item(discord.ui.Separator())
        if history_data:
            try:
                history = json.loads(history_data) if isinstance(history_data, str) else history_data
                for entry in history[-10:]:
                    timestamp = entry.get('timestamp', '')[:19]
                    action = entry.get('action', '')
                    staff = entry.get('staff', '')
                    history_container.add_item(discord.ui.TextDisplay(content=f"`{timestamp}` - {action} por {staff}"))
            except:
                history_container.add_item(discord.ui.TextDisplay(content="Nenhum histórico disponível."))
        else:
            history_container.add_item(discord.ui.TextDisplay(content="Nenhum histórico disponível."))
        history_view = discord.ui.LayoutView()
        history_view.add_item(history_container)
        await interaction.followup.send(view=history_view, ephemeral=True)
    
    async def close_panel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.delete_original_response()
    
    def has_staff_role(self, interaction: discord.Interaction) -> bool:
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return False
        role = interaction.guild.get_role(self.staff_role_id)
        return role in member.roles if role else False


# =========================
# MODAL PARA DESCRIÇÃO DO PAINEL
# =========================

class PanelDescriptionModal(discord.ui.Modal):
    def __init__(self, current_description: str):
        super().__init__(title="📝 Editar Descrição do Painel")
        
        self.descricao = discord.ui.TextInput(
            label="Descrição do Painel",
            placeholder="Digite a descrição que aparecerá no painel de tickets...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
            default=current_description
        )
        self.add_item(self.descricao)
    
    async def on_submit(self, interaction: discord.Interaction):
        config = get_config(interaction.guild_id) or {}
        config['panel_description'] = self.descricao.value
        save_config(interaction.guild_id, config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Descrição do painel atualizada com sucesso!"),
            ephemeral=True
        )


# =========================
# MODAL PARA TÍTULO DO PAINEL
# =========================

class PanelTitleModal(discord.ui.Modal):
    def __init__(self, current_title: str):
        super().__init__(title="🎨 Editar Título do Painel")
        
        self.titulo = discord.ui.TextInput(
            label="Título do Painel",
            placeholder="Digite o título que aparecerá no painel...",
            style=discord.TextStyle.short,
            required=True,
            max_length=100,
            default=current_title
        )
        self.add_item(self.titulo)
    
    async def on_submit(self, interaction: discord.Interaction):
        config = get_config(interaction.guild_id) or {}
        config['panel_title'] = self.titulo.value
        save_config(interaction.guild_id, config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Título do painel atualizado com sucesso!"),
            ephemeral=True
        )

# =========================
# MODAIS PARA O PAINEL STAFF
# =========================

class BanConfirmModal(discord.ui.Modal):
    """Modal para confirmar bloqueio de usuário"""
    def __init__(self, user_id: int, ticket_id: str):
        super().__init__(title="🔒 Bloquear Usuário")
        self.user_id = user_id
        self.ticket_id = ticket_id
        
        self.motivo = discord.ui.TextInput(
            label="Motivo do bloqueio",
            placeholder="Descreva o motivo do bloqueio...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.motivo)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        
        if member:
            try:
                await member.ban(reason=f"Ticket #{self.ticket_id} - {self.motivo.value}")
                
                # Registrar no histórico
                history_key = f"ticket_history:{self.ticket_id}"
                history = redis_pool.get(history_key)
                history_list = json.loads(history) if history else []
                history_list.append({
                    'timestamp': datetime.utcnow().isoformat(),
                    'action': 'Bloqueio',
                    'staff': str(interaction.user),
                    'details': self.motivo.value
                })
                redis_pool.set(history_key, json.dumps(history_list[-20:]), ex=TICKET_TIMEOUT)
                
                await interaction.followup.send(
                    view=create_text_only_view(f"✅ Usuário {member.mention} foi bloqueado com sucesso!\nMotivo: {self.motivo.value}"),
                    ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(
                    view=create_text_only_view(f"❌ Erro ao bloquear usuário: {str(e)[:100]}"),
                    ephemeral=True
                )
        else:
            await interaction.followup.send(view=create_text_only_view("❌ Usuário não encontrado no servidor."), ephemeral=True)


class WarnModal(discord.ui.Modal):
    """Modal para enviar advertência"""
    def __init__(self, user_id: int, ticket_id: str):
        super().__init__(title="⚠️ Advertência")
        self.user_id = user_id
        self.ticket_id = ticket_id
        
        self.motivo = discord.ui.TextInput(
            label="Motivo da advertência",
            placeholder="Descreva o motivo...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.motivo)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        
        if member:
            # Enviar DM para o usuário
            warn_container = discord.ui.Container()
            warn_container.accent = 0xED4245
            warn_container.add_item(discord.ui.TextDisplay(content="# ⚠️ ADVERTÊNCIA"))
            warn_container.add_item(discord.ui.Separator())
            warn_container.add_item(discord.ui.TextDisplay(content=f"**Ticket:** #{self.ticket_id}"))
            warn_container.add_item(discord.ui.TextDisplay(content=f"**Motivo:** {self.motivo.value}"))
            warn_container.add_item(discord.ui.Separator())
            warn_container.add_item(discord.ui.TextDisplay(content="Esta é uma advertência oficial. Por favor, siga as regras do servidor."))
            
            warn_view = discord.ui.LayoutView()
            warn_view.add_item(warn_container)
            
            await member.send(view=warn_view)
            
            # Registrar no histórico
            history_key = f"ticket_history:{self.ticket_id}"
            history = redis_pool.get(history_key)
            history_list = json.loads(history) if history else []
            history_list.append({
                'timestamp': datetime.utcnow().isoformat(),
                'action': 'Advertência',
                'staff': str(interaction.user),
                'details': self.motivo.value
            })
            redis_pool.set(history_key, json.dumps(history_list[-20:]), ex=TICKET_TIMEOUT)
            
            await interaction.followup.send(
                view=create_text_only_view(f"✅ Advertência enviada para {member.mention}!"),
                ephemeral=True
            )
        else:
            await interaction.followup.send(view=create_text_only_view("❌ Usuário não encontrado no servidor."), ephemeral=True)


class NoteModal(discord.ui.Modal):
    """Modal para adicionar nota interna"""
    def __init__(self, ticket_id: str):
        super().__init__(title="📝 Adicionar Nota Interna")
        self.ticket_id = ticket_id
        
        self.nota = discord.ui.TextInput(
            label="Nota interna",
            placeholder="Adicione uma nota sobre este ticket (visível apenas para staff)...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.nota)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Registrar no histórico
        history_key = f"ticket_history:{self.ticket_id}"
        history = redis_pool.get(history_key)
        history_list = json.loads(history) if history else []
        history_list.append({
            'timestamp': datetime.utcnow().isoformat(),
            'action': 'Nota Interna',
            'staff': str(interaction.user),
            'details': self.nota.value
        })
        redis_pool.set(history_key, json.dumps(history_list[-20:]), ex=TICKET_TIMEOUT)
        
        await interaction.followup.send(
            view=create_text_only_view(f"✅ Nota interna adicionada com sucesso!"),
            ephemeral=True
        )


# =========================
# TICKET CHANNEL VIEW - VERSÃO CORRIGIDA (COM EDIÇÃO DO BOTÃO)
# =========================

class TicketChannelView(discord.ui.LayoutView):
    def __init__(self, ticket_id: str, user_id: int, staff_role_id: int):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.user_id = user_id
        self.staff_role_id = staff_role_id
        
        # Armazenar referência ao botão claim
        self.claim_button = None
        
        # Construir o container com as informações
        container = discord.ui.Container()
        container.accent = 0x57F287

        container.add_item(discord.ui.TextDisplay(content="# 🎫 SISTEMA DE SUPORTE"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**Ticket ID:** #{self.ticket_id}"))
        container.add_item(discord.ui.TextDisplay(content=f"**Criado por:** <@{self.user_id}>"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="Utilize os botões abaixo para gerenciar este ticket."))
        
        # Adicionar o container à view
        self.add_item(container)
        
        # Adicionar LINHA 1 - Assumir Ticket e Notificar (2 botões)
        row1 = discord.ui.ActionRow()
        
        self.claim_button = discord.ui.Button(
            label="🧑‍💼 Assumir Ticket",
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_claim_{self.ticket_id[:8]}",
            emoji="🧑‍💼"
        )
        self.claim_button.callback = self.claim_ticket
        row1.add_item(self.claim_button)
        
        notify_btn = discord.ui.Button(
            label="🔔 Notificar",
            style=discord.ButtonStyle.secondary,
            custom_id=f"ticket_notify_{self.ticket_id[:8]}",
            emoji="🔔"
        )
        notify_btn.callback = self.notify_user
        row1.add_item(notify_btn)
        
        self.add_item(row1)
        
        # Adicionar LINHA 2 - Painel Staff e Encerrar (2 botões)
        row2 = discord.ui.ActionRow()
        
        staff_btn = discord.ui.Button(
            label="🛠️ Painel Staff",
            style=discord.ButtonStyle.secondary,
            custom_id=f"ticket_staff_{self.ticket_id[:8]}",
            emoji="🛠️"
        )
        staff_btn.callback = self.staff_panel
        row2.add_item(staff_btn)
        
        close_btn = discord.ui.Button(
            label="❌ Encerrar",
            style=discord.ButtonStyle.danger,
            custom_id=f"ticket_close_{self.ticket_id[:8]}",
            emoji="❌"
        )
        close_btn.callback = self.close_ticket
        row2.add_item(close_btn)
        
        self.add_item(row2)

    async def claim_ticket(self, interaction: discord.Interaction):
        """Assumir ticket - EDITA o botão original"""
        member = interaction.guild.get_member(interaction.user.id)
        staff_role = interaction.guild.get_role(self.staff_role_id)

        if not staff_role or (staff_role not in member.roles and not member.guild_permissions.administrator):
            await interaction.response.send_message(view=create_text_only_view("❌ Você não tem permissão para assumir tickets."), ephemeral=True)
            return

        ticket_data = get_ticket(self.ticket_id)
        if ticket_data.get('assigned_to'):
            await interaction.response.send_message(view=create_text_only_view(f"⚠️ Este ticket já foi assumido por <@{ticket_data['assigned_to']}>"), ephemeral=True)
            return

        ticket_data['assigned_to'] = interaction.user.id
        save_ticket(interaction.guild_id, ticket_data)

        # DESABILITAR O BOTÃO DE ASSUMIR e atualizar o texto
        self.claim_button.disabled = True
        self.claim_button.label = "✅ Assumido"
        self.claim_button.style = discord.ButtonStyle.success
        
        # Adicionar uma mensagem de confirmação no container do ticket (opcional)
        # Encontrar o container e adicionar uma mensagem
        for child in self.children:
            if isinstance(child, discord.ui.Container):
                # Adicionar uma mensagem de que o ticket foi assumido
                child.add_item(discord.ui.TextDisplay(content=f"\n✅ **Ticket assumido por {interaction.user.mention}**"))
                break
        
        # EDITAR a mensagem original
        await interaction.response.edit_message(view=self)
        
        log("TICKET", f"Ticket {self.ticket_id} assumido por {interaction.user}")

    async def notify_user(self, interaction: discord.Interaction):
        """Notificar usuário"""
        member = interaction.guild.get_member(self.user_id)
        if member:
            container = discord.ui.Container()
            container.accent = 0x5865F2
            container.add_item(discord.ui.TextDisplay(content="# 🔔 NOTIFICAÇÃO DO SUPORTE"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(content=f"Seu ticket **#{self.ticket_id}** foi atualizado!\n\nUm membro da equipe responderá em breve."))

            view = discord.ui.LayoutView()
            view.add_item(container)

            await member.send(view=view)
            await interaction.response.send_message(view=create_text_only_view("✅ Usuário notificado!"), ephemeral=True)
        else:
            await interaction.response.send_message(view=create_text_only_view("❌ Não foi possível notificar o usuário."), ephemeral=True)

    async def staff_panel(self, interaction: discord.Interaction):
        """Abrir painel staff"""
        member = interaction.guild.get_member(interaction.user.id)
        staff_role = interaction.guild.get_role(self.staff_role_id)

        if not staff_role or (staff_role not in member.roles and not member.guild_permissions.administrator):
            await interaction.response.send_message(view=create_text_only_view("❌ Você não tem permissão para acessar o painel staff."), ephemeral=True)
            return

        view = StaffPanelView(self.ticket_id, interaction.channel_id, self.user_id, self.staff_role_id)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def close_ticket(self, interaction: discord.Interaction):
        """Encerrar ticket"""
        member = interaction.guild.get_member(interaction.user.id)
        staff_role = interaction.guild.get_role(self.staff_role_id)

        has_permission = (staff_role and staff_role in member.roles) or member.guild_permissions.administrator or member.id == self.user_id

        if not has_permission:
            await interaction.response.send_message(view=create_text_only_view("❌ Você não tem permissão para encerrar este ticket."), ephemeral=True)
            return

        await interaction.response.defer()

        config = get_config(interaction.guild_id)
        log_channel_id = config.get('log_channel')
        review_channel_id = config.get('review_channel')

        ticket_data = get_ticket(self.ticket_id)
        staff_id = ticket_data.get('assigned_to')

        # Gerar transcript
        gist_url = None
        try:
            html_content = await TranscriptGenerator.generate_html(interaction.channel, ticket_data, interaction.user)
            gist_url = await TranscriptGenerator.upload_to_gist(html_content, self.ticket_id)
        except Exception as e:
            err("TRANSCRIPT", e)

        # Registrar logs
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                log_container = discord.ui.Container()
                log_container.accent = 0xED4245
                log_container.add_item(discord.ui.TextDisplay(content="# 📜 TICKET ENCERRADO"))
                log_container.add_item(discord.ui.Separator())
                log_container.add_item(discord.ui.TextDisplay(content=f"**Ticket:** #{self.ticket_id}"))
                log_container.add_item(discord.ui.TextDisplay(content=f"**Usuário:** <@{self.user_id}>"))
                log_container.add_item(discord.ui.TextDisplay(content=f"**Atendente:** <@{staff_id}>" if staff_id else "**Atendente:** Não assumido"))
                log_container.add_item(discord.ui.TextDisplay(content=f"**Encerrado por:** {interaction.user.mention}"))
                log_container.add_item(discord.ui.TextDisplay(content=f"**Transcript:** {gist_url if gist_url else 'Falha'}"))

                log_view = discord.ui.LayoutView()
                log_view.add_item(log_container)
                await log_channel.send(view=log_view)

# No TicketChannelView.close_ticket, substitua a parte da avaliação por:

        # Enviar avaliação para o USUÁRIO
        if staff_id:  # Se tem atendente, envia avaliação
            user_member = interaction.guild.get_member(self.user_id)
            if user_member:
                # Criar a view de avaliação
                view = AvaliacaoView(self.ticket_id, self.user_id, staff_id)
                
                # Enviar DM com a avaliação
                try:
                    await user_member.send(view=view)
                    logger.info(f"✅ Avaliação enviada para {user_member.name} (Ticket: {self.ticket_id})")
                except discord.Forbidden:
                    logger.warning(f"❌ Não foi possível enviar DM para {user_member.name} - DMs bloqueadas")
                except Exception as e:
                    logger.error(f"❌ Erro ao enviar avaliação: {e}")

        await interaction.followup.send(view=create_text_only_view("🔒 Ticket será encerrado em 5 segundos..."))
        await asyncio.sleep(5)

        delete_ticket(self.ticket_id, interaction.guild_id, self.user_id)
        await interaction.channel.delete()
        log("TICKET", f"Ticket {self.ticket_id} encerrado")


# =========================
# EDIT PAINEL TICKET (GERENCIAR CATEGORIAS)
# =========================

class GerenciarCategoriasView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, categories: list):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.categories = categories if isinstance(categories, list) else []
        self.build_container()
    
    def build_container(self):
        container = discord.ui.Container()
        container.accent = 0x5865F2
        
        container.add_item(discord.ui.TextDisplay(content="# 📂 GERENCIAR CATEGORIAS"))
        container.add_item(discord.ui.Separator())
        
        if not self.categories:
            container.add_item(discord.ui.TextDisplay(content="Nenhuma categoria cadastrada.\n\nClique em 'Nova Categoria' para criar."))
        else:
            for i, cat in enumerate(self.categories[:10], 1):
                if not isinstance(cat, dict):
                    continue
                    
                emoji = cat.get('emoji', '📁')
                title = cat.get('title', 'Sem título')
                description = cat.get('description', 'Sem descrição')[:50]
                
                container.add_item(discord.ui.TextDisplay(
                    content=f"**{i}.** {emoji} **{title}**\n┣ {description}..."
                ))
                container.add_item(discord.ui.Separator())
        
        self.add_item(container)
    
    @discord.ui.button(label="➕ Nova Categoria", style=discord.ButtonStyle.success, custom_id="new_category", emoji="➕", row=0)
    async def new_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = NovaCategoriaModal(self.guild_id, self.categories)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="✏️ Editar Categoria", style=discord.ButtonStyle.primary, custom_id="edit_category", emoji="✏️", row=0)
    async def edit_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.categories or len(self.categories) == 0:
            await interaction.response.send_message(view=create_text_only_view("❌ Nenhuma categoria cadastrada."), ephemeral=True)
            return
        
        options = []
        for i, cat in enumerate(self.categories):
            if not isinstance(cat, dict):
                continue
                
            title = cat.get('title', 'Sem título')[:25]
            emoji = cat.get('emoji', '📁')
            options.append(discord.SelectOption(
                label=title,
                value=str(i),
                emoji=emoji
            ))
        
        if not options:
            await interaction.response.send_message(view=create_text_only_view("❌ Nenhuma categoria cadastrada."), ephemeral=True)
            return
        
        select = discord.ui.Select(
            placeholder="Selecione a categoria para editar",
            options=options
        )
        
        async def select_callback(select_interaction: discord.Interaction):
            try:
                idx = int(select.values[0])
                if idx < 0 or idx >= len(self.categories):
                    await select_interaction.response.send_message(
                        view=create_text_only_view("❌ Categoria inválida."),
                        ephemeral=True
                    )
                    return
                
                cat = self.categories[idx]
                modal = EditarCategoriaModal(self.guild_id, self.categories, idx, cat)
                await select_interaction.response.send_modal(modal)
            except (ValueError, IndexError, TypeError) as e:
                err("EDIT_CATEGORY", e)
                await select_interaction.response.send_message(
                    view=create_text_only_view("❌ Erro ao selecionar categoria."),
                    ephemeral=True
                )
        
        select.callback = select_callback
        view = discord.ui.LayoutView()
        view.add_item(select)
        await interaction.response.send_message(view=view, ephemeral=True)
    
    @discord.ui.button(label="🗑️ Remover Categoria", style=discord.ButtonStyle.danger, custom_id="remove_category", emoji="🗑️", row=1)
    async def remove_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.categories or len(self.categories) == 0:
            await interaction.response.send_message(view=create_text_only_view("❌ Nenhuma categoria cadastrada."), ephemeral=True)
            return
        
        options = []
        for i, cat in enumerate(self.categories):
            if not isinstance(cat, dict):
                continue
                
            title = cat.get('title', 'Sem título')[:25]
            emoji = cat.get('emoji', '📁')
            options.append(discord.SelectOption(
                label=title,
                value=str(i),
                emoji=emoji
            ))
        
        if not options:
            await interaction.response.send_message(view=create_text_only_view("❌ Nenhuma categoria cadastrada."), ephemeral=True)
            return
        
        select = discord.ui.Select(
            placeholder="Selecione a categoria para remover",
            options=options
        )
        
        async def select_callback(select_interaction: discord.Interaction):
            try:
                idx = int(select.values[0])
                if idx < 0 or idx >= len(self.categories):
                    await select_interaction.response.send_message(
                        view=create_text_only_view("❌ Categoria inválida."),
                        ephemeral=True
                    )
                    return
                
                removed = self.categories.pop(idx)
                
                config = get_config(self.guild_id)
                config['categories'] = self.categories
                save_config(self.guild_id, config)
                
                await select_interaction.response.send_message(
                    view=create_text_only_view(f"🗑️ Categoria **{removed.get('title', 'Sem título')}** removida!"),
                    ephemeral=True
                )
            except (ValueError, IndexError, TypeError) as e:
                err("REMOVE_CATEGORY", e)
                await select_interaction.response.send_message(
                    view=create_text_only_view("❌ Erro ao remover categoria."),
                    ephemeral=True
                )
        
        select.callback = select_callback
        view = discord.ui.LayoutView()
        view.add_item(select)
        await interaction.response.send_message(view=view, ephemeral=True)
    
    @discord.ui.button(label="🔙 Voltar", style=discord.ButtonStyle.secondary, custom_id="back_main", emoji="🔙", row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = EditTicketPanelView(self.guild_id)
        await interaction.response.send_message(view=view, ephemeral=True)


class NovaCategoriaModal(discord.ui.Modal):
    def __init__(self, guild_id: int, categories: list):
        super().__init__(title="📂 Nova Categoria")
        self.guild_id = guild_id
        self.categories = categories if isinstance(categories, list) else []
        
        self.emoji = discord.ui.TextInput(
            label="Emoji da categoria",
            placeholder="📁, 🎮, 💰, etc...",
            required=False,
            max_length=5,
            default="📁"
        )
        self.add_item(self.emoji)
        
        self.titulo = discord.ui.TextInput(
            label="Título da categoria",
            placeholder="Ex: Suporte Técnico",
            required=True,
            max_length=50
        )
        self.add_item(self.titulo)
        
        self.descricao = discord.ui.TextInput(
            label="Descrição da categoria",
            placeholder="Descreva o propósito desta categoria...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=200
        )
        self.add_item(self.descricao)
    
    async def on_submit(self, interaction: discord.Interaction):
        new_category = {
            'emoji': self.emoji.value or "📁",
            'title': self.titulo.value,
            'description': self.descricao.value
        }
        
        self.categories.append(new_category)
        
        config = get_config(self.guild_id)
        if not isinstance(config, dict):
            config = {}
            
        config['categories'] = self.categories
        save_config(self.guild_id, config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Categoria **{self.titulo.value}** adicionada com sucesso!"),
            ephemeral=True
        )


class EditarCategoriaModal(discord.ui.Modal):
    def __init__(self, guild_id: int, categories: list, idx: int, category: dict):
        super().__init__(title="✏️ Editar Categoria")
        self.guild_id = guild_id
        self.categories = categories if isinstance(categories, list) else []
        self.idx = idx
        
        self.emoji = discord.ui.TextInput(
            label="Emoji da categoria",
            placeholder="📁, 🎮, 💰, etc...",
            required=False,
            max_length=5,
            default=category.get('emoji', '📁')
        )
        self.add_item(self.emoji)
        
        self.titulo = discord.ui.TextInput(
            label="Título da categoria",
            placeholder="Ex: Suporte Técnico",
            required=True,
            max_length=50,
            default=category.get('title', '')
        )
        self.add_item(self.titulo)
        
        self.descricao = discord.ui.TextInput(
            label="Descrição da categoria",
            placeholder="Descreva o propósito desta categoria...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=200,
            default=category.get('description', '')
        )
        self.add_item(self.descricao)
    
    async def on_submit(self, interaction: discord.Interaction):
        updated_category = {
            'emoji': self.emoji.value or "📁",
            'title': self.titulo.value,
            'description': self.descricao.value
        }
        
        if self.idx < 0 or self.idx >= len(self.categories):
            await interaction.response.send_message(
                view=create_text_only_view("❌ Índice de categoria inválido."),
                ephemeral=True
            )
            return
            
        self.categories[self.idx] = updated_category
        
        config = get_config(self.guild_id)
        if not isinstance(config, dict):
            config = {}
            
        config['categories'] = self.categories
        save_config(self.guild_id, config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Categoria **{self.titulo.value}** atualizada com sucesso!"),
            ephemeral=True
        )


# =========================
# EDIT PAINEL TICKET (CONFIGURAÇÃO)
# =========================

class EditTicketPanelView(discord.ui.LayoutView):
    def __init__(self, guild_id: int):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.config = get_config(guild_id) or {}
        self.build_container()
    
    def build_container(self):
        container = discord.ui.Container()
        container.accent = 0x5865F2
        
        container.add_item(discord.ui.TextDisplay(content="# ⚙️ CONFIGURAÇÃO DO SISTEMA DE TICKETS"))
        container.add_item(discord.ui.Separator())
        
        # Processar cada configuração com segurança
        categoria_id = self.config.get('category_id', 'Não definido')
        staff_role_id = self.config.get('staff_role_id', 'Não definido')
        log_channel_id = self.config.get('log_channel', 'Não definido')
        review_channel_id = self.config.get('review_channel', 'Não definido')
        
        # Formatar exibição com segurança
        categoria_display = f"<#{categoria_id}>" if categoria_id != 'Não definido' and str(categoria_id).isdigit() else categoria_id
        staff_role_display = f"<@&{staff_role_id}>" if staff_role_id != 'Não definido' and str(staff_role_id).isdigit() else staff_role_id
        log_channel_display = f"<#{log_channel_id}>" if log_channel_id != 'Não definido' and str(log_channel_id).isdigit() else log_channel_id
        review_channel_display = f"<#{review_channel_id}>" if review_channel_id != 'Não definido' and str(review_channel_id).isdigit() else review_channel_id
        
        container.add_item(discord.ui.TextDisplay(
            content=f"**📁 Categoria de Tickets:** {categoria_display}"
        ))
        container.add_item(discord.ui.TextDisplay(content=f"**👮 Cargo de Staff:** {staff_role_display}"))
        container.add_item(discord.ui.TextDisplay(content=f"**📜 Canal de Logs:** {log_channel_display}"))
        container.add_item(discord.ui.TextDisplay(content=f"**⭐ Canal de Avaliações:** {review_channel_display}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="**Categorias Disponíveis:**"))
        
        categories = self.config.get('categories', [])
        if not isinstance(categories, list):
            categories = []
            
        if not categories:
            container.add_item(discord.ui.TextDisplay(content="Nenhuma categoria cadastrada."))
        else:
            for i, cat in enumerate(categories[:5], 1):
                if not isinstance(cat, dict):
                    continue
                    
                emoji = cat.get('emoji', '📁')
                title = cat.get('title', 'Sem título')
                description = cat.get('description', 'Sem descrição')
                
                container.add_item(discord.ui.TextDisplay(
                    content=f"{i}. {emoji} **{title}** - {description[:40]}..."
                ))
        
        self.add_item(container)
    
    @discord.ui.button(label="📁 Definir Categoria", style=discord.ButtonStyle.primary, custom_id="set_category", emoji="📁", row=0)
    async def set_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SetCategoryModal(self.guild_id, self.config)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="👮 Definir Staff Role", style=discord.ButtonStyle.primary, custom_id="set_staff", emoji="👮", row=0)
    async def set_staff_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SetStaffRoleModal(self.guild_id, self.config)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📜 Definir Log Channel", style=discord.ButtonStyle.primary, custom_id="set_log", emoji="📜", row=0)
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SetLogChannelModal(self.guild_id, self.config)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⭐ Definir Review Channel", style=discord.ButtonStyle.primary, custom_id="set_review", emoji="⭐", row=1)
    async def set_review_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SetReviewChannelModal(self.guild_id, self.config)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📂 Gerenciar Categorias", style=discord.ButtonStyle.success, custom_id="manage_categories", emoji="📂", row=1)
    async def manage_categories(self, interaction: discord.Interaction, button: discord.ui.Button):
        categories = self.config.get('categories', [])
        view = GerenciarCategoriasView(self.guild_id, categories)
        await interaction.response.send_message(view=view, ephemeral=True)
    
    @discord.ui.button(label="🎨 Editar Painel Visual", style=discord.ButtonStyle.secondary, custom_id="edit_visual", emoji="🎨", row=1)
    async def edit_visual(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditPanelVisualModal(self.guild_id, self.config)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔐 Configurar GitHub", style=discord.ButtonStyle.secondary, custom_id="config_github", emoji="🔐", row=2)
    async def config_github(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ConfigGitHubModal(self.guild_id)
        await interaction.response.send_modal(modal)


class ConfigGitHubModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="🔐 Configurar Token do GitHub")
        self.guild_id = guild_id
        
        self.github_token = discord.ui.TextInput(
            label="Token do GitHub",
            placeholder="Cole seu token de acesso pessoal aqui",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=100
        )
        self.add_item(self.github_token)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            token = self.github_token.value.strip()
            
            # Armazenar no Redis
            redis_pool.set("github:token", token, ex=None)
            
            # Testar o token
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json"
                }
                
                async with session.get("https://api.github.com/user", headers=headers) as response:
                    if response.status == 200:
                        user_data = await response.json()
                        await interaction.response.send_message(
                            view=create_text_only_view(f"✅ Token configurado com sucesso!\n\nUsuário: {user_data['login']}"),
                            ephemeral=True
                        )
                        log("GITHUB", "Token do GitHub configurado")
                    else:
                        error_data = await response.text()
                        await interaction.response.send_message(
                            view=create_text_only_view(f"❌ Token inválido ou com permissões insuficientes.\nStatus: {response.status}"),
                            ephemeral=True
                        )
        except Exception as e:
            err("GITHUB", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro ao configurar token: {str(e)[:100]}"),
                ephemeral=True
            )


class SetCategoryModal(discord.ui.Modal):
    def __init__(self, guild_id: int, config: dict):
        super().__init__(title="📁 Definir Categoria de Tickets")
        self.guild_id = guild_id
        self.config = config
        
        self.category_id = discord.ui.TextInput(
            label="ID da Categoria",
            placeholder="Cole o ID da categoria aqui",
            required=True,
            max_length=20,
            default=str(config.get('category_id', '')) if config.get('category_id') else ""
        )
        self.add_item(self.category_id)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            category_id = int(self.category_id.value)
            category = interaction.guild.get_channel(category_id)
            
            if not category or not isinstance(category, discord.CategoryChannel):
                await interaction.response.send_message(view=create_text_only_view("❌ ID de categoria inválido!"), ephemeral=True)
                return
            
            self.config['category_id'] = category_id
            save_config(self.guild_id, self.config)
            
            await interaction.response.send_message(
                view=create_text_only_view(f"✅ Categoria definida: {category.mention}"),
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(view=create_text_only_view("❌ ID inválido!"), ephemeral=True)


class SetStaffRoleModal(discord.ui.Modal):
    def __init__(self, guild_id: int, config: dict):
        super().__init__(title="👮 Definir Cargo de Staff")
        self.guild_id = guild_id
        self.config = config
        
        self.role_id = discord.ui.TextInput(
            label="ID do Cargo",
            placeholder="Cole o ID do cargo aqui",
            required=True,
            max_length=20,
            default=str(config.get('staff_role_id', '')) if config.get('staff_role_id') else ""
        )
        self.add_item(self.role_id)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_id.value)
            role = interaction.guild.get_role(role_id)
            
            if not role:
                await interaction.response.send_message(view=create_text_only_view("❌ ID de cargo inválido!"), ephemeral=True)
                return
            
            self.config['staff_role_id'] = role_id
            save_config(self.guild_id, self.config)
            
            await interaction.response.send_message(
                view=create_text_only_view(f"✅ Cargo de staff definido: {role.mention}"),
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(view=create_text_only_view("❌ ID inválido!"), ephemeral=True)


class SetLogChannelModal(discord.ui.Modal):
    def __init__(self, guild_id: int, config: dict):
        super().__init__(title="📜 Definir Canal de Logs")
        self.guild_id = guild_id
        self.config = config
        
        self.channel_id = discord.ui.TextInput(
            label="ID do Canal",
            placeholder="Cole o ID do canal aqui",
            required=True,
            max_length=20,
            default=str(config.get('log_channel', '')) if config.get('log_channel') else ""
        )
        self.add_item(self.channel_id)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_id.value)
            channel = interaction.guild.get_channel(channel_id)
            
            if not channel or not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message(view=create_text_only_view("❌ ID de canal inválido!"), ephemeral=True)
                return
            
            self.config['log_channel'] = channel_id
            save_config(self.guild_id, self.config)
            
            await interaction.response.send_message(
                view=create_text_only_view(f"✅ Canal de logs definido: {channel.mention}"),
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(view=create_text_only_view("❌ ID inválido!"), ephemeral=True)


class SetReviewChannelModal(discord.ui.Modal):
    def __init__(self, guild_id: int, config: dict):
        super().__init__(title="⭐ Definir Canal de Avaliações")
        self.guild_id = guild_id
        self.config = config
        
        self.channel_id = discord.ui.TextInput(
            label="ID do Canal",
            placeholder="Cole o ID do canal aqui",
            required=True,
            max_length=20,
            default=str(config.get('review_channel', '')) if config.get('review_channel') else ""
        )
        self.add_item(self.channel_id)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_id.value)
            channel = interaction.guild.get_channel(channel_id)
            
            if not channel or not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message(view=create_text_only_view("❌ ID de canal inválido!"), ephemeral=True)
                return
            
            self.config['review_channel'] = channel_id
            save_config(self.guild_id, self.config)
            
            await interaction.response.send_message(
                view=create_text_only_view(f"✅ Canal de avaliações definido: {channel.mention}"),
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(view=create_text_only_view("❌ ID inválido!"), ephemeral=True)


class EditPanelVisualModal(discord.ui.Modal):
    def __init__(self, guild_id: int, config: dict):
        super().__init__(title="🎨 Editar Painel Visual")
        self.guild_id = guild_id
        self.config = config
        
        self.titulo = discord.ui.TextInput(
            label="Título do Painel",
            placeholder="Ex: 🎫 SISTEMA DE SUPORTE",
            required=True,
            max_length=100,
            default=config.get('panel_title', '🎫 SISTEMA DE SUPORTE')
        )
        self.add_item(self.titulo)
        
        self.descricao = discord.ui.TextInput(
            label="Descrição do Painel",
            placeholder="Descreva como abrir um ticket...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500,
            default=config.get('panel_description', 'Selecione uma categoria abaixo para abrir um ticket de suporte.')
        )
        self.add_item(self.descricao)
    
    async def on_submit(self, interaction: discord.Interaction):
        self.config['panel_title'] = self.titulo.value
        self.config['panel_description'] = self.descricao.value
        save_config(self.guild_id, self.config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Painel visual atualizado!"),
            ephemeral=True
        )


# =========================
# PAINEL PÚBLICO DE TICKETS - NOVA ABORDAGEM
# =========================

class TicketCategorySelect(discord.ui.Select):
    """Select para escolher a categoria de ticket"""
    def __init__(self, guild_id: int, config: dict):
        self.guild_id = guild_id
        self.config = config
        
        # Obter categorias da configuração
        categories = config.get('categories', [])
        if not isinstance(categories, list):
            categories = []
        
        # Criar opções do select
        options = []
        for cat in categories:
            if not isinstance(cat, dict):
                continue
                
            title = cat.get('title', 'Sem título')[:25]
            description = cat.get('description', '')[:50]
            emoji = cat.get('emoji', '📁')
            
            options.append(
                discord.SelectOption(
                    label=title,
                    description=description,
                    value=title,
                    emoji=emoji
                )
            )
        
        # Se não houver opções válidas, adicionar uma opção de aviso
        if not options:
            options = [
                discord.SelectOption(
                    label="Nenhuma categoria disponível",
                    description="Configure categorias no painel de administração",
                    value="no_categories",
                    emoji="⚠️"
                )
            ]
        
        super().__init__(
            placeholder="📂 Selecione uma categoria",
            options=options,
            custom_id=f"ticket_category_select_{guild_id}"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Callback quando uma categoria é selecionada"""
        if self.values[0] == "no_categories":
            await interaction.response.send_message(
                view=create_text_only_view("❌ Nenhuma categoria disponível. Configure categorias usando `/ticket_setup` e depois `/edit_painel_ticket`."),
                ephemeral=True
            )
            return
        
        # Obter configuração atualizada
        config = get_config(self.guild_id)
        categories = config.get('categories', [])
        
        # Encontrar categoria selecionada
        selected_cat = None
        for cat in categories:
            if not isinstance(cat, dict):
                continue
                
            if cat.get('title') == self.values[0]:
                selected_cat = cat
                break
        
        if not selected_cat:
            await interaction.response.send_message(
                view=create_text_only_view("❌ Categoria inválida."),
                ephemeral=True
            )
            return
        
        # Verificar limite de tickets
        active_tickets = get_user_active_tickets(interaction.guild_id, interaction.user.id)
        if active_tickets >= MAX_TICKETS_PER_USER:
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Você já possui {active_tickets} ticket(s) ativo(s).\nAguarde o encerramento para abrir um novo."),
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Criar canal do ticket
        category_id = config.get('category_id')
        if not category_id:
            await interaction.followup.send(
                view=create_text_only_view("❌ Sistema não configurado corretamente. Contate um administrador."),
                ephemeral=True
            )
            return
        
        category = interaction.guild.get_channel(category_id)
        if not category:
            await interaction.followup.send(
                view=create_text_only_view("❌ Categoria de tickets não encontrada."),
                ephemeral=True
            )
            return
        
        # Criar overwrites
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        
        staff_role_id = config.get('staff_role_id')
        if staff_role_id:
            staff_role = interaction.guild.get_role(staff_role_id)
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        
        # Gerar ID do ticket
        ticket_id = f"{interaction.user.id}_{int(datetime.utcnow().timestamp())}"
        channel_name = f"ticket-{interaction.user.name.lower()[:20]}"
        
        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket #{ticket_id} - Categoria: {selected_cat.get('title', 'Geral')}"
            )
            
            # Salvar dados do ticket
            ticket_data = {
                'ticket_id': ticket_id,
                'channel_id': channel.id,
                'user_id': interaction.user.id,
                'category': selected_cat.get('title', 'Geral'),
                'created_at': datetime.utcnow().isoformat(),
                'assigned_to': None
            }
            save_ticket(interaction.guild_id, ticket_data)
            
            # Enviar mensagem no canal
            view = TicketChannelView(ticket_id, interaction.user.id, staff_role_id)
            
            # Dentro do TicketCategorySelect, na criação do ticket, remova a linha duplicada:

            # Remova esta linha (está duplicada):
            # view = TicketChannelView(ticket_id, interaction.user.id, staff_role_id)

            # Mantenha apenas:
            welcome_container = discord.ui.Container()
            welcome_container.accent = 0x57F287
            welcome_container.add_item(discord.ui.TextDisplay(content=f"# 🎫 {selected_cat.get('emoji', '📁')} {selected_cat.get('title', 'Geral')}"))
            welcome_container.add_item(discord.ui.Separator())
            welcome_container.add_item(discord.ui.TextDisplay(content=selected_cat.get('description', '')))
            welcome_container.add_item(discord.ui.Separator())
            welcome_container.add_item(discord.ui.TextDisplay(content="Bem-vindo ao seu ticket de suporte! Um membro da equipe atenderá em breve."))

            welcome_view = discord.ui.LayoutView()
            welcome_view.add_item(welcome_container)

            await channel.send(view=welcome_view)

            # Enviar o painel de controle do ticket (COM OS BOTÕES) - apenas uma vez
            ticket_view = TicketChannelView(ticket_id, interaction.user.id, staff_role_id)
            await channel.send(view=ticket_view)
            
            await interaction.followup.send(
                view=create_text_only_view(f"✅ Ticket criado com sucesso!\n\n📁 Canal: {channel.mention}"),
                ephemeral=True
            )
            
            # Log de criação
            log_channel_id = config.get('log_channel')
            if log_channel_id:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    log_container = discord.ui.Container()
                    log_container.accent = 0x57F287
                    log_container.add_item(discord.ui.TextDisplay(content="# 🎫 NOVO TICKET"))
                    log_container.add_item(discord.ui.Separator())
                    log_container.add_item(discord.ui.TextDisplay(content=f"**Ticket:** #{ticket_id}"))
                    log_container.add_item(discord.ui.TextDisplay(content=f"**Usuário:** {interaction.user.mention}"))
                    log_container.add_item(discord.ui.TextDisplay(content=f"**Categoria:** {selected_cat.get('title', 'Geral')}"))
                    log_container.add_item(discord.ui.TextDisplay(content=f"**Canal:** {channel.mention}"))
                    
                    log_view = discord.ui.LayoutView()
                    log_view.add_item(log_container)
                    await log_channel.send(view=log_view)
            
            log("TICKET", f"Ticket {ticket_id} criado por {interaction.user}")
            
        except Exception as e:
            err("CREATE_TICKET", e)
            await interaction.followup.send(
                view=create_text_only_view(f"❌ Erro ao criar ticket: {str(e)[:100]}"),
                ephemeral=True
            )


class PainelTicketView(discord.ui.LayoutView):
    """View principal do painel de tickets"""
    def __init__(self, guild_id: int, config: dict):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.config = config or {}
        
        # Container com o conteúdo
        container = discord.ui.Container()
        container.accent = 0x5865F2
        
        title = config.get('panel_title', '🎫 SISTEMA DE SUPORTE')
        container.add_item(discord.ui.TextDisplay(content=f"# {title}"))
        container.add_item(discord.ui.Separator())
        
        description = config.get('panel_description', 'Selecione uma categoria abaixo para abrir um ticket de suporte.')
        container.add_item(discord.ui.TextDisplay(content=description))
        container.add_item(discord.ui.Separator())
        
        self.add_item(container)
        
        # Criar Action Row explicitamente para o select
        action_row = discord.ui.ActionRow()
        action_row.add_item(TicketCategorySelect(guild_id, config))
        self.add_item(action_row)
    
    def build_container(self):
        """Constrói o container principal da view"""
        container = discord.ui.Container()
        container.accent = 0x5865F2
        
        title = self.config.get('panel_title', '🎫 SISTEMA DE SUPORTE')
        container.add_item(discord.ui.TextDisplay(content=f"# {title}"))
        container.add_item(discord.ui.Separator())
        
        description = self.config.get('panel_description', 'Selecione uma categoria abaixo para abrir um ticket de suporte.')
        container.add_item(discord.ui.TextDisplay(content=description))
        container.add_item(discord.ui.Separator())
        
        # Adicionar informações sobre as categorias
        categories = self.config.get('categories', [])
        if isinstance(categories, list) and categories:
            container.add_item(discord.ui.TextDisplay(content="**Categorias disponíveis:**"))
            
            for i, cat in enumerate(categories[:5], 1):
                if not isinstance(cat, dict):
                    continue
                    
                emoji = cat.get('emoji', '📁')
                title = cat.get('title', 'Sem título')
                description = cat.get('description', 'Sem descrição')[:40]
                
                container.add_item(discord.ui.TextDisplay(
                    content=f"{i}. {emoji} **{title}** - {description}..."
                ))
        
        self.add_item(container)


# =========================
# COG PRINCIPAL
# =========================

class TicketSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log("INIT", "TicketSystem carregado")

    async def cog_load(self):
        log("INIT", "TicketSystem pronto para uso")


    @discord.app_commands.command(name="ticket_stats", description="📊 Mostra estatísticas do sistema de tickets")
    @discord.app_commands.default_permissions(administrator=True)
    async def ticket_stats(self, interaction: discord.Interaction):
        """Mostra estatísticas do sistema"""
        try:
            stats = metrics.get_stats()
            
            container = discord.ui.Container()
            container.accent = 0x5865F2
            container.add_item(discord.ui.TextDisplay(content="# 📊 ESTATÍSTICAS DO SISTEMA"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(content=f"**✅ Total de tickets criados:** {stats['total_created']}"))
            container.add_item(discord.ui.TextDisplay(content=f"**❌ Total de tickets fechados:** {stats['total_closed']}"))
            container.add_item(discord.ui.TextDisplay(content=f"**🟢 Tickets abertos:** {stats['open_tickets']}"))
            container.add_item(discord.ui.TextDisplay(content=f"**⏱️ Tempo médio de fechamento:** {stats['avg_close_time_minutes']} minutos"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(content="**📂 Tickets por categoria:**"))
            
            for cat, count in stats['tickets_by_category'].items():
                container.add_item(discord.ui.TextDisplay(content=f"┣ {cat}: {count}"))
            
            view = discord.ui.LayoutView()
            view.add_item(container)
            await interaction.response.send_message(view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Erro ao mostrar estatísticas: {e}")
            await interaction.response.send_message(view=create_text_only_view("❌ Erro ao carregar estatísticas"), ephemeral=True)

    # =========================
    # COMANDOS DE CONFIGURAÇÃO (COM ARGUMENTOS)
    # =========================

    @discord.app_commands.command(name="ticket_set_category", description="📁 Define a categoria onde os tickets serão criados")
    @discord.app_commands.default_permissions(administrator=True)
    async def set_category(self, interaction: discord.Interaction, categoria: discord.CategoryChannel):
        """Define a categoria para criação de tickets"""
        config = get_config(interaction.guild_id) or {}
        config['category_id'] = categoria.id
        save_config(interaction.guild_id, config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Categoria definida: {categoria.mention}"),
            ephemeral=True
        )

    @discord.app_commands.command(name="ticket_set_staff_role", description="👮 Define o cargo de staff que pode atender tickets")
    @discord.app_commands.default_permissions(administrator=True)
    async def set_staff_role(self, interaction: discord.Interaction, cargo: discord.Role):
        """Define o cargo de staff"""
        config = get_config(interaction.guild_id) or {}
        config['staff_role_id'] = cargo.id
        save_config(interaction.guild_id, config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Cargo de staff definido: {cargo.mention}"),
            ephemeral=True
        )

    @discord.app_commands.command(name="ticket_set_log_channel", description="📜 Define o canal para logs de tickets")
    @discord.app_commands.default_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        """Define o canal de logs"""
        config = get_config(interaction.guild_id) or {}
        config['log_channel'] = canal.id
        save_config(interaction.guild_id, config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Canal de logs definido: {canal.mention}"),
            ephemeral=True
        )

    @discord.app_commands.command(name="ticket_set_review_channel", description="⭐ Define o canal para avaliações")
    @discord.app_commands.default_permissions(administrator=True)
    async def set_review_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        """Define o canal de avaliações"""
        config = get_config(interaction.guild_id) or {}
        config['review_channel'] = canal.id
        save_config(interaction.guild_id, config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Canal de avaliações definido: {canal.mention}"),
            ephemeral=True
        )

    @discord.app_commands.command(name="ticket_add_category", description="📂 Adiciona uma categoria de ticket")
    @discord.app_commands.default_permissions(administrator=True)
    async def add_category(self, interaction: discord.Interaction, emoji: str, titulo: str, descricao: str):
        """Adiciona uma categoria de ticket"""
        config = get_config(interaction.guild_id) or {}
        categories = config.get('categories', [])
        
        categories.append({
            'emoji': emoji or "📁",
            'title': titulo,
            'description': descricao
        })
        
        config['categories'] = categories
        save_config(interaction.guild_id, config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Categoria **{titulo}** adicionada com sucesso!"),
            ephemeral=True
        )

    @discord.app_commands.command(name="ticket_remove_category", description="🗑️ Remove uma categoria de ticket")
    @discord.app_commands.default_permissions(administrator=True)
    async def remove_category(self, interaction: discord.Interaction, titulo: str):
        """Remove uma categoria de ticket pelo título"""
        config = get_config(interaction.guild_id) or {}
        categories = config.get('categories', [])
        
        removed = None
        for i, cat in enumerate(categories):
            if cat.get('title') == titulo:
                removed = categories.pop(i)
                break
        
        if removed:
            config['categories'] = categories
            save_config(interaction.guild_id, config)
            await interaction.response.send_message(
                view=create_text_only_view(f"🗑️ Categoria **{titulo}** removida!"),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Categoria **{titulo}** não encontrada."),
                ephemeral=True
            )

    @discord.app_commands.command(name="ticket_list_categories", description="📋 Lista todas as categorias de ticket")
    @discord.app_commands.default_permissions(administrator=True)
    async def list_categories(self, interaction: discord.Interaction):
        """Lista as categorias cadastradas"""
        config = get_config(interaction.guild_id) or {}
        categories = config.get('categories', [])
        
        if not categories:
            await interaction.response.send_message(
                view=create_text_only_view("📂 Nenhuma categoria cadastrada.\nUse `/ticket_add_category` para adicionar."),
                ephemeral=True
            )
            return
        
        container = discord.ui.Container()
        container.accent = 0x5865F2
        container.add_item(discord.ui.TextDisplay(content="# 📂 CATEGORIAS DE TICKETS"))
        container.add_item(discord.ui.Separator())
        
        for i, cat in enumerate(categories, 1):
            container.add_item(discord.ui.TextDisplay(
                content=f"**{i}.** {cat.get('emoji', '📁')} **{cat.get('title')}**\n┣ {cat.get('description', 'Sem descrição')}"
            ))
            container.add_item(discord.ui.Separator())
        
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)

    @discord.app_commands.command(name="ticket_set_panel_title", description="🎨 Define o título do painel de tickets")
    @discord.app_commands.default_permissions(administrator=True)
    async def set_panel_title(self, interaction: discord.Interaction):
        """Define o título do painel (abre modal)"""
        config = get_config(interaction.guild_id) or {}
        current_title = config.get('panel_title', '🎫 SISTEMA DE SUPORTE')
        
        modal = PanelTitleModal(current_title)
        await interaction.response.send_modal(modal)

    @discord.app_commands.command(name="ticket_set_panel_description", description="📝 Define a descrição do painel de tickets")
    @discord.app_commands.default_permissions(administrator=True)
    async def set_panel_description(self, interaction: discord.Interaction):
        """Define a descrição do painel (abre modal)"""
        config = get_config(interaction.guild_id) or {}
        current_description = config.get('panel_description', 'Selecione uma categoria abaixo para abrir um ticket de suporte.\n\nNossa equipe estará disponível para atendê-lo.')
        
        modal = PanelDescriptionModal(current_description)
        await interaction.response.send_modal(modal)

    @discord.app_commands.command(name="ticket_show_config", description="📊 Mostra a configuração atual do sistema")
    @discord.app_commands.default_permissions(administrator=True)
    async def show_config(self, interaction: discord.Interaction):
        """Mostra a configuração atual"""
        config = get_config(interaction.guild_id) or {}
        
        container = discord.ui.Container()
        container.accent = 0x5865F2
        container.add_item(discord.ui.TextDisplay(content="# ⚙️ CONFIGURAÇÃO DO SISTEMA"))
        container.add_item(discord.ui.Separator())
        
        categoria_id = config.get('category_id', '❌ Não definido')
        staff_role_id = config.get('staff_role_id', '❌ Não definido')
        log_channel_id = config.get('log_channel', '❌ Não definido')
        review_channel_id = config.get('review_channel', '❌ Não definido')
        
        container.add_item(discord.ui.TextDisplay(content=f"**📁 Categoria:** {f'<#{categoria_id}>' if categoria_id != '❌ Não definido' else categoria_id}"))
        container.add_item(discord.ui.TextDisplay(content=f"**👮 Staff Role:** {f'<@&{staff_role_id}>' if staff_role_id != '❌ Não definido' else staff_role_id}"))
        container.add_item(discord.ui.TextDisplay(content=f"**📜 Log Channel:** {f'<#{log_channel_id}>' if log_channel_id != '❌ Não definido' else log_channel_id}"))
        container.add_item(discord.ui.TextDisplay(content=f"**⭐ Review Channel:** {f'<#{review_channel_id}>' if review_channel_id != '❌ Não definido' else review_channel_id}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**🎨 Título:** {config.get('panel_title', '🎫 SISTEMA DE SUPORTE')}"))
        container.add_item(discord.ui.TextDisplay(content=f"**📝 Descrição:** {config.get('panel_description', 'Selecione uma categoria abaixo')[:100]}..."))
        
        if config.get('categories'):
            container.add_item(discord.ui.TextDisplay(content=f"**📂 Categorias:** {len(config.get('categories'))} cadastradas"))
        
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)

    @discord.app_commands.command(name="ticket_setup", description="⚙️ Configuração inicial do sistema de tickets")
    @discord.app_commands.default_permissions(administrator=True)
    async def ticket_setup(self, interaction: discord.Interaction):
        try:
            log("SETUP", f"Iniciando setup para {interaction.guild}")
            
            config = get_config(interaction.guild_id) or {}
            
            if not config:
                config = {
                    'guild_id': interaction.guild_id,
                    'categories': [],
                    'panel_title': '🎫 SISTEMA DE SUPORTE',
                    'panel_description': 'Selecione uma categoria abaixo para abrir um ticket de suporte.\n\nNossa equipe estará disponível para atendê-lo.'
                }
                save_config(interaction.guild_id, config)
            
            view = EditTicketPanelView(interaction.guild_id)
            await interaction.response.send_message(view=view, ephemeral=True)
            log("SETUP", f"Setup concluído para {interaction.guild}")
            
        except Exception as e:
            err("SETUP", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro na configuração: {str(e)[:100]}"),
                ephemeral=True
            )

    @discord.app_commands.command(name="edit_painel_ticket", description="✏️ Edita o painel público de tickets")
    @discord.app_commands.default_permissions(administrator=True)
    async def edit_ticket_panel(self, interaction: discord.Interaction):
        try:
            log("EDIT", f"Editando painel para {interaction.guild}")
            
            config = get_config(interaction.guild_id) or {}
            
            if not config:
                await interaction.response.send_message(
                    view=create_text_only_view("❌ Sistema não configurado. Use `/ticket_setup` primeiro."),
                    ephemeral=True
                )
                return
            
            view = EditTicketPanelView(interaction.guild_id)
            await interaction.response.send_message(view=view, ephemeral=True)
            
        except Exception as e:
            err("EDIT", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"),
                ephemeral=True
            )

    @commands.command(name="sync_tickets", hidden=True)
    @commands.is_owner()
    async def sync_tickets(self, ctx):
        """Força a sincronização dos comandos de tickets"""
        try:
            # Sincronizar globalmente
            synced = await self.bot.tree.sync()
            
            # Mostrar comandos registrados
            cmd_list = [cmd.name for cmd in synced]
            await ctx.send(f"✅ {len(synced)} comandos sincronizados!\nComandos: {', '.join(cmd_list[:20])}")
            
            log("SYNC", f"Sincronizados {len(synced)} comandos")
        except Exception as e:
            await ctx.send(f"❌ Erro: {e}")
            err("SYNC", e)

    @discord.app_commands.command(name="enviar_painel_ticket", description="📢 Envia o painel público de tickets")
    @discord.app_commands.default_permissions(administrator=True)
    async def send_ticket_panel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        try:
            log("PANEL", f"Enviando painel para {canal.mention}")
            
            config = get_config(interaction.guild_id) or {}
            
            if not config or not config.get('category_id') or not config.get('categories'):
                await interaction.response.send_message(
                    view=create_text_only_view("❌ Sistema não configurado corretamente.\nUse `/ticket_setup` e depois `/edit_painel_ticket` para configurar as categorias."),
                    ephemeral=True
                )
                return
            
            # Enviar o painel com o select funcional
            view = PainelTicketView(interaction.guild_id, config)
            await canal.send(view=view)
            
            await interaction.response.send_message(
                view=create_text_only_view(f"✅ Painel de tickets enviado em {canal.mention}!"),
                ephemeral=True
            )
            
        except Exception as e:
            err("SEND_PANEL", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"),
                ephemeral=True
            )


# =========================
# SETUP
# =========================

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketSystem(bot))
    log("SETUP", "✅ TicketSystem carregado com sucesso!")