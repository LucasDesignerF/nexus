"""
PIX Payment System - Discord Components V2
Sistema completo de cobranças via PIX com QR Code e EMV
"""

import discord
from discord import app_commands
from discord.ext import commands
import qrcode
from io import BytesIO
import traceback
import logging
import json
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import uuid

from pool.redis import redis_pool
from pool.connection import mongo_pool


# =========================
# CONFIGURAÇÃO DE LOGGING
# =========================

logger = logging.getLogger('PIXPayments')
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(handler)


# =========================
# LOG
# =========================

def log(tag: str, msg: str):
    logger.info(f"[{tag}] {msg}")

def err(tag: str, e: Exception):
    logger.error(f"[{tag}] {repr(e)}")
    traceback.print_exc()


# =========================
# CONFIGURAÇÃO
# =========================

SESSION_DURATION = 3600  # 1 hora para cobranças pendentes
MAX_COBRANCAS_HISTORY = 50


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
# 🔧 FORMATADOR EMV (PIX)
# =========================

def _format_field(id: str, value: str) -> str:
    """Formata campo EMV com ID + tamanho + valor"""
    size = f"{len(value):02d}"
    return f"{id}{size}{value}"


def _crc16(payload: str) -> str:
    """Calcula CRC16 para validação do payload PIX"""
    polinomio = 0x1021
    resultado = 0xFFFF

    for char in payload:
        resultado ^= ord(char) << 8
        for _ in range(8):
            if resultado & 0x8000:
                resultado = (resultado << 1) ^ polinomio
            else:
                resultado <<= 1
            resultado &= 0xFFFF

    return f"{resultado:04X}"


def gerar_payload_pix(valor: float, chave: str, txid: str) -> str:
    """Gera payload EMV completo para PIX"""
    valor_str = f"{valor:.2f}"
    
    if not txid:
        txid = str(uuid.uuid4())[:25]
    
    payload = ""
    
    # 00 - Payload Format Indicator
    payload += _format_field("00", "01")
    
    # 26 - Merchant Account Information (PIX)
    merchant_data = (
        _format_field("00", "BR.GOV.BCB.PIX") +
        _format_field("01", chave)
    )
    payload += _format_field("26", merchant_data)
    
    # 52 - Merchant Category Code (MCC)
    payload += _format_field("52", "0000")
    
    # 53 - Transaction Currency (BRL)
    payload += _format_field("53", "986")
    
    # 54 - Transaction Amount
    payload += _format_field("54", valor_str)
    
    # 58 - Country Code
    payload += _format_field("58", "BR")
    
    # 59 - Merchant Name (FIXO)
    payload += _format_field("59", "NEXUS PIX")
    
    # 60 - Merchant City (FIXA)
    payload += _format_field("60", "BRASIL")
    
    # 62 - Additional Data Field Template (TXID)
    additional_data = _format_field("05", txid[:25])
    payload += _format_field("62", additional_data)
    
    # 63 - CRC (placeholder, calculado depois)
    payload += "6304"
    crc = _crc16(payload)
    
    return payload + crc


def gerar_qrcode(payload: str) -> BytesIO:
    """Gera imagem QR Code a partir do payload EMV"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    
    return buffer


# =========================
# DATABASE OPERATIONS
# =========================

def get_config_key(guild_id: int) -> str:
    return f"pix_config:{guild_id}"

def get_cobranca_key(cobranca_id: str) -> str:
    return f"pix_cobranca:{cobranca_id}"

def get_history_key(guild_id: int, user_id: int) -> str:
    return f"pix_history:{guild_id}:{user_id}"

def save_config(guild_id: int, config: dict):
    try:
        key = get_config_key(guild_id)
        redis_pool.set(key, json.dumps(config), ex=None)
        
        col = mongo_pool.get_collection("pix_config")
        col.update_one({"guild_id": guild_id}, {"$set": config}, upsert=True)
        
        log("CONFIG", f"Config PIX salva para guild {guild_id}")
    except Exception as e:
        err("SAVE_CONFIG", e)

def get_config(guild_id: int) -> dict:
    try:
        key = get_config_key(guild_id)
        data = redis_pool.get(key)
        if data:
            return json.loads(data) if isinstance(data, str) else data
        
        col = mongo_pool.get_collection("pix_config")
        config = col.find_one({"guild_id": guild_id}) or {}
        if config:
            config.pop("_id", None)
            redis_pool.set(key, json.dumps(config), ex=None)
        return config
    except Exception as e:
        err("GET_CONFIG", e)
        return {}

def save_cobranca(cobranca_data: dict):
    try:
        cobranca_id = cobranca_data.get('cobranca_id')
        key = get_cobranca_key(cobranca_id)
        redis_pool.set(key, json.dumps(cobranca_data), ex=SESSION_DURATION)
        log("COBRANCA", f"Cobrança {cobranca_id} salva")
    except Exception as e:
        err("SAVE_COBRANCA", e)

def get_cobranca(cobranca_id: str) -> dict:
    try:
        key = get_cobranca_key(cobranca_id)
        data = redis_pool.get(key)
        if data:
            return json.loads(data) if isinstance(data, str) else data
        return {}
    except Exception as e:
        err("GET_COBRANCA", e)
        return {}

def delete_cobranca(cobranca_id: str):
    try:
        redis_pool.delete(get_cobranca_key(cobranca_id))
        log("COBRANCA", f"Cobrança {cobranca_id} removida")
    except Exception as e:
        err("DELETE_COBRANCA", e)

def add_to_history(guild_id: int, user_id: int, cobranca_data: dict):
    try:
        key = get_history_key(guild_id, user_id)
        existing = redis_pool.get(key)
        history = []
        
        if existing:
            try:
                history = json.loads(existing) if isinstance(existing, str) else existing
            except:
                history = []
        
        if not isinstance(history, list):
            history = []
        
        history.insert(0, cobranca_data)
        history = history[:MAX_COBRANCAS_HISTORY]
        
        redis_pool.set(key, json.dumps(history, ensure_ascii=False), ex=86400)
        log("HISTORY", f"Adicionado ao histórico de {user_id}")
    except Exception as e:
        err("ADD_HISTORY", e)

def get_history(guild_id: int, user_id: int) -> List[Dict]:
    try:
        key = get_history_key(guild_id, user_id)
        data = redis_pool.get(key)
        if data:
            return json.loads(data) if isinstance(data, str) else data
        return []
    except Exception as e:
        err("GET_HISTORY", e)
        return []


# =========================
# MODAL PARA CRIAR COBRANÇA
# =========================

class CriarCobrancaModal(discord.ui.Modal):
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(title="💰 Criar Cobrança PIX")
        self.user_id = user_id
        self.guild_id = guild_id
        
        self.valor = discord.ui.TextInput(
            label="💰 Valor (R$)",
            placeholder="Ex: 25.90, 100, 49.99",
            required=True,
            max_length=20,
            style=discord.TextStyle.short
        )
        self.add_item(self.valor)
        
        self.descricao = discord.ui.TextInput(
            label="📝 Descrição / TXID",
            placeholder="Ex: Assinatura Mensal, Compra #123...",
            required=False,
            max_length=100,
            style=discord.TextStyle.short
        )
        self.add_item(self.descricao)
        
        self.mensagem_adicional = discord.ui.TextInput(
            label="💬 Mensagem Adicional",
            placeholder="Mensagem que aparecerá para o cliente...",
            required=False,
            max_length=200,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.mensagem_adicional)
    
    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                view=create_text_only_view("❌ Este modal não pertence a você."),
                ephemeral=True
            )
            return
        
        try:
            valor = float(self.valor.value.replace(',', '.'))
            if valor <= 0:
                raise ValueError("Valor deve ser positivo")
        except ValueError:
            await interaction.response.send_message(
                view=create_text_only_view("❌ Valor inválido! Use formato como 25.90 ou 100"),
                ephemeral=True
            )
            return
        
        config = get_config(self.guild_id)
        chave_pix = config.get('chave_pix')
        
        if not chave_pix:
            await interaction.response.send_message(
                view=create_text_only_view("❌ Chave PIX não configurada neste servidor!\n\nUse `/pix_config` para configurar."),
                ephemeral=True
            )
            return
        
        txid = self.descricao.value if self.descricao.value else f"cobranca_{uuid.uuid4().hex[:8]}"
        payload = gerar_payload_pix(valor, chave_pix, txid)
        qr_buffer = gerar_qrcode(payload)
        
        cobranca_id = uuid.uuid4().hex[:12]
        cobranca_data = {
            'cobranca_id': cobranca_id,
            'criador_id': self.user_id,
            'guild_id': self.guild_id,
            'valor': valor,
            'descricao': self.descricao.value,
            'txid': txid,
            'payload': payload,
            'mensagem': self.mensagem_adicional.value,
            'created_at': datetime.utcnow().isoformat(),
            'status': 'aguardando'
        }
        save_cobranca(cobranca_data)
        
        qr_file = discord.File(qr_buffer, filename="qrcode.png")
        
        container = discord.ui.Container()
        container.accent = 0x00D4AA
        
        container.add_item(discord.ui.TextDisplay(content="# 💰 COBRANÇA PIX"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**Valor:** R$ {valor:.2f}"))
        container.add_item(discord.ui.TextDisplay(content=f"**Descrição:** {self.descricao.value or 'Sem descrição'}"))
        container.add_item(discord.ui.TextDisplay(content=f"**TXID:** `{txid[:20]}`"))
        container.add_item(discord.ui.Separator())
        
        if self.mensagem_adicional.value:
            container.add_item(discord.ui.TextDisplay(content=f"💬 {self.mensagem_adicional.value}"))
            container.add_item(discord.ui.Separator())
        
        container.add_item(discord.ui.TextDisplay(content="### 📱 Como pagar:"))
        container.add_item(discord.ui.TextDisplay(content="1. Abra o app do seu banco\n2. Escolha **Pagar com PIX**\n3. **Leia o QR Code** ao lado\n4. Confirme o pagamento"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"⏰ **Validade:** 1 hora\n🔒 **Pagamento seguro via PIX**"))
        
        view = discord.ui.LayoutView()
        view.add_item(container)
        
        btn_copiar = discord.ui.Button(
            label="📋 Copiar Código PIX",
            style=discord.ButtonStyle.primary,
            custom_id=f"pix_copy_{cobranca_id}",
            emoji="📋"
        )
        
        async def copy_callback(copy_interaction: discord.Interaction):
            if copy_interaction.user.id != self.user_id:
                await copy_interaction.response.send_message(
                    view=create_text_only_view("❌ Você não tem permissão para copiar esta cobrança."),
                    ephemeral=True
                )
                return
            
            copy_container = discord.ui.Container()
            copy_container.accent = 0x5865F2
            copy_container.add_item(discord.ui.TextDisplay(content=f"📋 **Código PIX (copia e cola):**\n```\n{payload}\n```"))
            copy_view = discord.ui.LayoutView()
            copy_view.add_item(copy_container)
            await copy_interaction.response.send_message(view=copy_view, ephemeral=True)
        
        btn_copiar.callback = copy_callback
        
        btn_confirmar = discord.ui.Button(
            label="✅ Marcar como Pago",
            style=discord.ButtonStyle.success,
            custom_id=f"pix_confirm_{cobranca_id}",
            emoji="✅"
        )
        
        async def confirm_callback(confirm_interaction: discord.Interaction):
            if confirm_interaction.user.id != self.user_id:
                await confirm_interaction.response.send_message(
                    view=create_text_only_view("❌ Apenas o criador da cobrança pode confirmar o pagamento."),
                    ephemeral=True
                )
                return
            
            cobranca = get_cobranca(cobranca_id)
            if not cobranca:
                await confirm_interaction.response.send_message(
                    view=create_text_only_view("❌ Cobrança não encontrada ou expirada."),
                    ephemeral=True
                )
                return
            
            cobranca['status'] = 'pago'
            save_cobranca(cobranca)
            add_to_history(confirm_interaction.guild_id, self.user_id, cobranca)
            
            confirm_container = discord.ui.Container()
            confirm_container.accent = 0x57F287
            confirm_container.add_item(discord.ui.TextDisplay(content="# ✅ PAGAMENTO CONFIRMADO!"))
            confirm_container.add_item(discord.ui.Separator())
            confirm_container.add_item(discord.ui.TextDisplay(content=f"**Valor:** R$ {cobranca['valor']:.2f}\n**Descrição:** {cobranca.get('descricao', 'Sem descrição')}"))
            confirm_container.add_item(discord.ui.Separator())
            confirm_container.add_item(discord.ui.TextDisplay(content="O pagamento foi registrado com sucesso!"))
            
            confirm_view = discord.ui.LayoutView()
            confirm_view.add_item(confirm_container)
            await confirm_interaction.response.send_message(view=confirm_view, ephemeral=True)
        
        btn_confirmar.callback = confirm_callback
        
        view.add_item(btn_copiar)
        view.add_item(btn_confirmar)
        
        await interaction.response.send_message(file=qr_file, view=view)
        log("COBRANCA", f"Cobrança criada: R$ {valor:.2f} por {interaction.user}")


# =========================
# VIEW DE CONFIGURAÇÃO
# =========================

class ConfigPIXView(discord.ui.LayoutView):
    def __init__(self, guild_id: int):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.config = get_config(guild_id) or {}
        self.build_container()
    
    def build_container(self):
        container = discord.ui.Container()
        container.accent = 0x00D4AA
        
        container.add_item(discord.ui.TextDisplay(content="# 💰 CONFIGURAÇÃO PIX"))
        container.add_item(discord.ui.Separator())
        
        chave_pix = self.config.get('chave_pix', '❌ Não configurada')
        container.add_item(discord.ui.TextDisplay(content=f"**🔑 Chave PIX:** `{chave_pix if chave_pix != '❌ Não configurada' else chave_pix}`"))
        container.add_item(discord.ui.Separator())
        
        container.add_item(discord.ui.TextDisplay(content="**⚙️ Opções disponíveis:**"))
        
        self.add_item(container)
    
    @discord.ui.button(label="🔑 Definir Chave PIX", style=discord.ButtonStyle.primary, custom_id="pix_set_key", emoji="🔑", row=0)
    async def set_key(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SetChavePixModal(self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📊 Ver Configuração", style=discord.ButtonStyle.secondary, custom_id="pix_view_config", emoji="📊", row=0)
    async def view_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_config(self.guild_id)
        chave = config.get('chave_pix', 'Não configurada')
        
        container = discord.ui.Container()
        container.accent = 0x5865F2
        container.add_item(discord.ui.TextDisplay(content="# 📊 Configuração Atual"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content=f"**🔑 Chave PIX:** `{chave}`"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(content="Use `/pix` para criar cobranças!"))
        
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)
    
    @discord.ui.button(label="🔙 Voltar", style=discord.ButtonStyle.secondary, custom_id="pix_back", emoji="🔙", row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()


class SetChavePixModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="🔑 Definir Chave PIX")
        self.guild_id = guild_id
        
        self.chave = discord.ui.TextInput(
            label="Chave PIX",
            placeholder="CPF, CNPJ, Email, Telefone ou Chave Aleatória",
            required=True,
            max_length=100,
            style=discord.TextStyle.short
        )
        self.add_item(self.chave)
        
        self.confirmar = discord.ui.TextInput(
            label="Digite 'CONFIRMAR' para prosseguir",
            placeholder="CONFIRMAR",
            required=True,
            max_length=10,
            style=discord.TextStyle.short
        )
        self.add_item(self.confirmar)
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmar.value.upper() != "CONFIRMAR":
            await interaction.response.send_message(
                view=create_text_only_view("❌ Você precisa digitar 'CONFIRMAR' para prosseguir."),
                ephemeral=True
            )
            return
        
        config = get_config(self.guild_id) or {}
        config['chave_pix'] = self.chave.value.strip()
        save_config(self.guild_id, config)
        
        await interaction.response.send_message(
            view=create_text_only_view(f"✅ Chave PIX definida com sucesso!\n\n**Chave:** `{self.chave.value}`"),
            ephemeral=True
        )
        
        log("CONFIG", f"Chave PIX configurada no servidor {self.guild_id}")


# =========================
# VIEW DE HISTÓRICO
# =========================

class HistoricoPIXView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.user_id = user_id
        self.build_container()
    
    def build_container(self):
        container = discord.ui.Container()
        container.accent = 0x5865F2
        
        container.add_item(discord.ui.TextDisplay(content="# 📜 HISTÓRICO DE COBRANÇAS"))
        container.add_item(discord.ui.Separator())
        
        history = get_history(self.guild_id, self.user_id)
        
        if not history:
            container.add_item(discord.ui.TextDisplay(content="📭 Nenhuma cobrança realizada ainda.\n\nUse `/pix` para criar sua primeira cobrança!"))
        else:
            for i, entry in enumerate(history[:10], 1):
                valor = entry.get('valor', 0)
                descricao = entry.get('descricao', 'Sem descrição')
                status = entry.get('status', 'aguardando')
                created_at = entry.get('created_at', datetime.utcnow().isoformat())
                
                try:
                    date = datetime.fromisoformat(created_at).strftime('%d/%m/%Y %H:%M')
                except:
                    date = created_at[:19] if len(created_at) > 19 else "agora"
                
                status_emoji = "✅" if status == 'pago' else "⏳"
                status_text = "Pago" if status == 'pago' else "Aguardando"
                
                container.add_item(discord.ui.TextDisplay(
                    content=f"**{i}.** {status_emoji} **R$ {valor:.2f}** - {status_text}\n┣ **Descrição:** {descricao[:50]}\n┗ **Data:** {date}"
                ))
                container.add_item(discord.ui.Separator())
            
            total_pago = sum(e.get('valor', 0) for e in history if e.get('status') == 'pago')
            container.add_item(discord.ui.TextDisplay(content=f"📊 **Total arrecadado:** R$ {total_pago:.2f}\n**Total de cobranças:** {len(history)}"))
        
        self.add_item(container)
    
    @discord.ui.button(label="🔙 Fechar", style=discord.ButtonStyle.secondary, custom_id="pix_hist_close", emoji="🔙", row=0)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()


# =========================
# BOTÃO PRINCIPAL DO PAINEL
# =========================

class BtnCriarCobranca(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="💰 Criar Cobrança",
            style=discord.ButtonStyle.success,
            custom_id="pix_btn_create",
            emoji="💰",
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        config = get_config(interaction.guild_id)
        if not config.get('chave_pix'):
            await interaction.response.send_message(
                view=create_text_only_view("❌ Chave PIX não configurada neste servidor!\n\nUse `/pix_config` por um administrador."),
                ephemeral=True
            )
            return
        
        modal = CriarCobrancaModal(interaction.user.id, interaction.guild_id)
        await interaction.response.send_modal(modal)


class BtnHistoricoPIX(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="📜 Histórico",
            style=discord.ButtonStyle.secondary,
            custom_id="pix_btn_history",
            emoji="📜",
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        view = HistoricoPIXView(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(view=view, ephemeral=True)


class BtnAjudaPIX(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="❓ Como Funciona",
            style=discord.ButtonStyle.secondary,
            custom_id="pix_btn_help",
            emoji="❓",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        container = discord.ui.Container()
        container.accent = 0x5865F2
        container.add_item(discord.ui.TextDisplay(content="# 💰 PIX - Guia Rápido"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            content="**1. Configurar Chave PIX**\nUse `/pix_config` para definir a chave do servidor\n\n"
                    "**2. Criar Cobrança**\nClique em 'Criar Cobrança' e preencha:\n"
                    "• Valor (R$)\n"
                    "• Descrição (opcional)\n"
                    "• Mensagem adicional (opcional)\n\n"
                    "**3. Pagamento**\n"
                    "• Leia o QR Code com o app do banco\n"
                    "• Ou copie o código PIX para pagar\n\n"
                    "**4. Confirmar**\n"
                    "Após o pagamento, clique em 'Marcar como Pago'\n\n"
                    "**✅ Histórico**\nVeja todas as suas cobranças em /pix_config"
        ))
        view = discord.ui.LayoutView()
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)


# =========================
# PAINEL PRINCIPAL
# =========================

class PainelPIX(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        
        container = discord.ui.Container()
        container.accent = 0x00D4AA
        
        container.add_item(discord.ui.TextDisplay(content="# 💰 SISTEMA DE PAGAMENTOS PIX"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            content="Cobre seus clientes de forma rápida e segura!\n\n"
                    "**✨ Vantagens:**\n"
                    "• QR Code instantâneo\n"
                    "• Código copia e cola\n"
                    "• Histórico de cobranças\n"
                    "• Pagamento confirmado em tempo real"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            content="### 🔒 Segurança PIX\n"
                    "• Payload EMV oficial\n"
                    "• Validade de 1 hora\n"
                    "• Chave configurável por servidor"
        ))
        
        self.add_item(container)
        
        row0 = discord.ui.ActionRow()
        row0.add_item(BtnCriarCobranca())
        row0.add_item(BtnHistoricoPIX())
        self.add_item(row0)
        
        row1 = discord.ui.ActionRow()
        row1.add_item(BtnAjudaPIX())
        self.add_item(row1)


# =========================
# COG PRINCIPAL
# =========================

class PIXPaymentSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log("INIT", "PIXPaymentSystem carregado")
    
    async def cog_load(self):
        self.bot.add_view(PainelPIX())
        log("INIT", "Views persistentes registradas")

    @app_commands.command(name="pix_ver_config", description="📊 Visualiza a configuração PIX atual")
    @app_commands.default_permissions(administrator=True)
    async def pix_ver_config(self, interaction: discord.Interaction):
        try:
            view = ConfigPIXView(interaction.guild_id)
            await interaction.response.send_message(view=view, ephemeral=True)
        except Exception as e:
            err("VER_CONFIG", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"),
                ephemeral=True
            )
    
    @app_commands.command(name="pix", description="💰 Abre o painel de cobranças PIX")
    async def pix_panel(self, interaction: discord.Interaction):
        try:
            log("PANEL", f"Painel PIX aberto por {interaction.user}")
            view = PainelPIX()
            await interaction.response.send_message(view=view)
        except Exception as e:
            err("PANEL", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"),
                ephemeral=True
            )
    
    @app_commands.command(name="pix_config", description="⚙️ Configura a chave PIX do servidor")
    @app_commands.default_permissions(administrator=True)
    async def pix_config(self, interaction: discord.Interaction):
        try:
            log("CONFIG", f"Configuração PIX acessada por {interaction.user}")
            modal = SetChavePixModal(interaction.guild_id)
            await interaction.response.send_modal(modal)
        except Exception as e:
            err("CONFIG", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"),
                ephemeral=True
            )
    
    @app_commands.command(name="pix_quick", description="💰 Cria uma cobrança PIX rapidamente")
    async def pix_quick(self, interaction: discord.Interaction, valor: str, membro: Optional[discord.Member] = None, descricao: str = None):
        try:
            try:
                valor_float = float(valor.replace(',', '.'))
                if valor_float <= 0:
                    raise ValueError
            except:
                await interaction.response.send_message(
                    view=create_text_only_view("❌ Valor inválido! Use formato como 25.90 ou 100"),
                    ephemeral=True
                )
                return
            
            config = get_config(interaction.guild_id)
            chave_pix = config.get('chave_pix')
            
            if not chave_pix:
                await interaction.response.send_message(
                    view=create_text_only_view("❌ Chave PIX não configurada!\nUse `/pix_config` por um administrador."),
                    ephemeral=True
                )
                return
            
            txid = descricao if descricao else f"quick_{uuid.uuid4().hex[:8]}"
            payload = gerar_payload_pix(valor_float, chave_pix, txid)
            qr_buffer = gerar_qrcode(payload)
            
            cobranca_id = uuid.uuid4().hex[:12]
            target_member = membro if membro else interaction.user
            
            cobranca_data = {
                'cobranca_id': cobranca_id,
                'criador_id': interaction.user.id,
                'criador_name': interaction.user.display_name,
                'target_id': target_member.id,
                'target_name': target_member.display_name,
                'guild_id': interaction.guild_id,
                'valor': valor_float,
                'descricao': descricao,
                'txid': txid,
                'payload': payload,
                'created_at': datetime.utcnow().isoformat(),
                'status': 'aguardando',
                'pago_em': None
            }
            save_cobranca(cobranca_data)
            
            add_to_history(interaction.guild_id, target_member.id, cobranca_data)
            if target_member.id != interaction.user.id:
                add_to_history(interaction.guild_id, interaction.user.id, cobranca_data)
            
            stats_key = f"pix_stats:{interaction.guild_id}:{target_member.id}"
            redis_pool.incr(stats_key)
            redis_pool.incr(f"{stats_key}:valor", int(valor_float * 100))
            
            qr_file = discord.File(qr_buffer, filename="qrcode.png")
            
            container = discord.ui.Container()
            container.accent = 0x00D4AA
            
            container.add_item(discord.ui.TextDisplay(content="# 💰 COBRANÇA PIX"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(content=f"**💰 Valor:** R$ {valor_float:.2f}"))
            container.add_item(discord.ui.TextDisplay(content=f"**📝 Descrição:** {descricao or 'Sem descrição'}"))
            container.add_item(discord.ui.TextDisplay(content=f"**👤 Cobrado:** {target_member.mention}"))
            container.add_item(discord.ui.TextDisplay(content=f"**👤 Criado por:** {interaction.user.mention}"))
            container.add_item(discord.ui.TextDisplay(content=f"**🆔 ID:** `{cobranca_id}`"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(content="📱 **QR Code em anexo!**"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(content="### 📋 Código PIX (Copia e Cola)"))
            container.add_item(discord.ui.TextDisplay(content=f"```\n{payload}\n```"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(content="### 📱 Como pagar:"))
            container.add_item(discord.ui.TextDisplay(
                content="1️⃣ Abra o app do seu banco\n"
                        "2️⃣ Escolha **Pagar com PIX**\n"
                        "3️⃣ **Leia o QR Code** anexado\n"
                        "4️⃣ Confirme o pagamento"
            ))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(content=f"⏰ **Validade:** 1 hora\n🔒 **Pagamento seguro via PIX**"))
            
            view = discord.ui.LayoutView()
            view.add_item(container)
            
            btn_copiar = discord.ui.Button(
                label="📋 Copiar Código PIX",
                style=discord.ButtonStyle.primary,
                custom_id=f"pix_copy_{cobranca_id}",
                emoji="📋"
            )
            
            async def copy_callback(copy_interaction: discord.Interaction):
                if copy_interaction.user.id != interaction.user.id and copy_interaction.user.id != target_member.id:
                    await copy_interaction.response.send_message(
                        view=create_text_only_view("❌ Apenas o criador ou o cobrado podem copiar o código."),
                        ephemeral=True
                    )
                    return
                
                copy_container = discord.ui.Container()
                copy_container.accent = 0x5865F2
                copy_container.add_item(discord.ui.TextDisplay(content="# 📋 Código PIX Completo"))
                copy_container.add_item(discord.ui.Separator())
                copy_container.add_item(discord.ui.TextDisplay(content="**Copie o código abaixo e cole no seu banco:**"))
                copy_container.add_item(discord.ui.TextDisplay(content=f"```\n{payload}\n```"))
                copy_container.add_item(discord.ui.TextDisplay(content="⚠️ **Não compartilhe este código com ninguém!**"))
                
                copy_view = discord.ui.LayoutView()
                copy_view.add_item(copy_container)
                await copy_interaction.response.send_message(view=copy_view, ephemeral=True)
            
            btn_copiar.callback = copy_callback
            
            btn_confirmar = discord.ui.Button(
                label="✅ Marcar como Pago",
                style=discord.ButtonStyle.success,
                custom_id=f"pix_confirm_{cobranca_id}",
                emoji="✅"
            )
            
            async def confirm_callback(confirm_interaction: discord.Interaction):
                if confirm_interaction.user.id != interaction.user.id and confirm_interaction.user.id != target_member.id:
                    await confirm_interaction.response.send_message(
                        view=create_text_only_view("❌ Apenas o criador ou o cobrado podem confirmar o pagamento."),
                        ephemeral=True
                    )
                    return
                
                cobranca = get_cobranca(cobranca_id)
                if not cobranca:
                    await confirm_interaction.response.send_message(
                        view=create_text_only_view("❌ Cobrança não encontrada ou expirada."),
                        ephemeral=True
                    )
                    return
                
                if cobranca['status'] == 'pago':
                    await confirm_interaction.response.send_message(
                        view=create_text_only_view("⚠️ Esta cobrança já foi marcada como paga!"),
                        ephemeral=True
                    )
                    return
                
                cobranca['status'] = 'pago'
                cobranca['pago_em'] = datetime.utcnow().isoformat()
                cobranca['pago_por'] = confirm_interaction.user.id
                save_cobranca(cobranca)
                
                add_to_history(confirm_interaction.guild_id, target_member.id, cobranca)
                if target_member.id != interaction.user.id:
                    add_to_history(confirm_interaction.guild_id, interaction.user.id, cobranca)
                
                redis_pool.incr(f"pix_stats:{interaction.guild_id}:{target_member.id}:pagos")
                valor_cents = int(cobranca['valor'] * 100)
                redis_pool.incr(f"pix_stats:{interaction.guild_id}:{target_member.id}:valor_pago", valor_cents)
                
                confirm_container = discord.ui.Container()
                confirm_container.accent = 0x57F287
                confirm_container.add_item(discord.ui.TextDisplay(content="# ✅ PAGAMENTO CONFIRMADO!"))
                confirm_container.add_item(discord.ui.Separator())
                confirm_container.add_item(discord.ui.TextDisplay(
                    content=f"**💰 Valor:** R$ {cobranca['valor']:.2f}\n"
                            f"**📝 Descrição:** {cobranca.get('descricao', 'Sem descrição')}\n"
                            f"**👤 Cobrado:** <@{cobranca['target_id']}>"
                ))
                confirm_container.add_item(discord.ui.Separator())
                confirm_container.add_item(discord.ui.TextDisplay(content="✅ O pagamento foi registrado com sucesso!\nObrigado pela preferência!"))
                
                confirm_view = discord.ui.LayoutView()
                confirm_view.add_item(confirm_container)
                await confirm_interaction.response.send_message(view=confirm_view, ephemeral=True)
                
                if confirm_interaction.user.id != interaction.user.id:
                    try:
                        notif_container = discord.ui.Container()
                        notif_container.accent = 0x57F287
                        notif_container.add_item(discord.ui.TextDisplay(content="# 💰 Pagamento Confirmado!"))
                        notif_container.add_item(discord.ui.Separator())
                        notif_container.add_item(discord.ui.TextDisplay(
                            content=f"**{confirm_interaction.user.display_name}** confirmou o pagamento da cobrança:\n"
                                    f"**Valor:** R$ {cobranca['valor']:.2f}\n"
                                    f"**Descrição:** {cobranca.get('descricao', 'Sem descrição')}"
                        ))
                        notif_view = discord.ui.LayoutView()
                        notif_view.add_item(notif_container)
                        await interaction.user.send(view=notif_view)
                    except:
                        pass
            
            btn_confirmar.callback = confirm_callback
            
            row_buttons = discord.ui.ActionRow()
            row_buttons.add_item(btn_copiar)
            row_buttons.add_item(btn_confirmar)
            view.add_item(row_buttons)
            
            await interaction.response.send_message(file=qr_file, view=view)
            log("QUICK", f"Cobrança rápida: R$ {valor_float:.2f} para {target_member.display_name} por {interaction.user}")
            
        except Exception as e:
            err("QUICK", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro: {str(e)[:200]}"),
                ephemeral=True
            )

    @app_commands.command(name="pix_ranking", description="📊 Mostra ranking de quem mais pagou/recebeu PIX")
    async def pix_ranking(self, interaction: discord.Interaction, tipo: str = "pagos"):
        try:
            guild_id = interaction.guild_id
            prefix = f"pix_stats:{guild_id}"
            
            all_keys = redis_pool.keys(f"{prefix}:*")
            
            rankings = []
            for key in all_keys:
                if "valor_pago" in key or "pagos" in key:
                    continue
                
                parts = key.split(":")
                if len(parts) >= 3:
                    user_id = int(parts[-1])
                    member = interaction.guild.get_member(user_id)
                    if member and not member.bot:
                        total_cobrancas = int(redis_pool.get(f"{prefix}:{user_id}") or 0)
                        total_pagos = int(redis_pool.get(f"{prefix}:{user_id}:pagos") or 0)
                        valor_total_cents = int(redis_pool.get(f"{prefix}:{user_id}:valor_pago") or 0)
                        valor_total = valor_total_cents / 100
                        valor_pago = valor_total_cents / 100
                        
                        if tipo == "pagos":
                            rankings.append((member, total_pagos, valor_pago))
                        else:
                            rankings.append((member, total_cobrancas, valor_total))
            
            rankings.sort(key=lambda x: x[1], reverse=True)
            rankings = rankings[:10]
            
            if not rankings:
                await interaction.response.send_message(
                    view=create_text_only_view("📊 Nenhuma estatística encontrada ainda.\n\nUse `/pix_quick` para começar a coletar dados!"),
                    ephemeral=True
                )
                return
            
            container = discord.ui.Container()
            container.accent = 0x5865F2
            
            titulo = "🏆 PAGAMENTOS REALIZADOS" if tipo == "pagos" else "💰 VALORES RECEBIDOS"
            container.add_item(discord.ui.TextDisplay(content=f"# {titulo}"))
            container.add_item(discord.ui.Separator())
            
            for i, (member, count, valor) in enumerate(rankings, 1):
                medalha = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}º")
                if tipo == "pagos":
                    container.add_item(discord.ui.TextDisplay(
                        content=f"{medalha} **{member.display_name}**\n┣ **Pagamentos:** {count}\n┗ **Total Pago:** R$ {valor:.2f}"
                    ))
                else:
                    container.add_item(discord.ui.TextDisplay(
                        content=f"{medalha} **{member.display_name}**\n┣ **Cobranças:** {count}\n┗ **Total Recebido:** R$ {valor:.2f}"
                    ))
                container.add_item(discord.ui.Separator())
            
            view = discord.ui.LayoutView()
            view.add_item(container)
            
            await interaction.response.send_message(view=view, ephemeral=False)
            
        except Exception as e:
            err("RANKING", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro ao gerar ranking: {str(e)[:100]}"),
                ephemeral=True
            )

    @app_commands.command(name="pix_stats_user", description="📊 Mostra estatísticas PIX de um usuário")
    async def pix_stats_user(self, interaction: discord.Interaction, membro: Optional[discord.Member] = None):
        try:
            target = membro if membro else interaction.user
            guild_id = interaction.guild_id
            
            total_cobrancas = int(redis_pool.get(f"pix_stats:{guild_id}:{target.id}") or 0)
            total_pagos = int(redis_pool.get(f"pix_stats:{guild_id}:{target.id}:pagos") or 0)
            valor_recebido_cents = int(redis_pool.get(f"pix_stats:{guild_id}:{target.id}:valor_pago") or 0)
            valor_recebido = valor_recebido_cents / 100
            
            taxa_conversao = (total_pagos / total_cobrancas * 100) if total_cobrancas > 0 else 0
            
            container = discord.ui.Container()
            container.accent = 0x00D4AA
            
            container.add_item(discord.ui.TextDisplay(content=f"# 📊 Estatísticas PIX - {target.display_name}"))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.TextDisplay(
                content=f"**💰 Cobranças Recebidas:** {total_cobrancas}\n"
                        f"**✅ Pagamentos Confirmados:** {total_pagos}\n"
                        f"**💵 Total Recebido:** R$ {valor_recebido:.2f}\n"
                        f"**📈 Taxa de Conversão:** {taxa_conversao:.1f}%"
            ))
            
            view = discord.ui.LayoutView()
            view.add_item(container)
            
            await interaction.response.send_message(view=view, ephemeral=True)
            
        except Exception as e:
            err("STATS_USER", e)
            await interaction.response.send_message(
                view=create_text_only_view(f"❌ Erro: {str(e)[:100]}"),
                ephemeral=True
            )


# =========================
# SETUP
# =========================

async def setup(bot: commands.Bot):
    await bot.add_cog(PIXPaymentSystem(bot))
    log("SETUP", "✅ PIXPaymentSystem carregado com sucesso!")