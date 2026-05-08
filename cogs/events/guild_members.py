import discord
from discord import app_commands
from discord.ext import commands
import json

from pool.redis import redis_pool
from pool.connection import mongo_pool
from pool.event_bus import event_bus


# =========================
# LOG
# =========================

def log(prefix: str, msg: str):
    print(f"[GuildMembers:{prefix}] {msg}")


# =========================
# DATABASE
# =========================

def get_collection():
    return mongo_pool.get_collection("guild_config")


def cache_key(guild_id: int):
    return f"guild:{guild_id}:config"


def get_config(guild_id: int):
    try:
        cached = redis_pool.get(cache_key(guild_id))
        if cached:
            return json.loads(cached) if isinstance(cached, str) else cached
    except:
        pass

    try:
        col = get_collection()
        data = col.find_one({"guild_id": guild_id}) or {}
        if data:
            data["_id"] = str(data.get("_id"))
            redis_pool.set(cache_key(guild_id), json.dumps(data), ex=300)
        return data
    except Exception as e:
        log("DB", f"Erro: {e}")
        return {}


def save_config(guild_id: int, config: dict):
    try:
        col = get_collection()
        col.update_one({"guild_id": guild_id}, {"$set": config}, upsert=True)
        redis_pool.set(cache_key(guild_id), json.dumps(config), ex=300)
    except Exception as e:
        log("SAVE", f"Erro: {e}")


# =========================
# ANTI DUPLICATE
# =========================

_processed = set()

def _dedupe(guild_id: int, user_id: int, event: str):
    key = f"{guild_id}:{user_id}:{event}"
    if key in _processed:
        return False
    _processed.add(key)
    if len(_processed) > 5000:
        _processed.clear()
    return True


# =========================
# UI BUILDER (Container V2 - Sem Embed)
# =========================

def build_join_ui(member: discord.Member):
    container = discord.ui.Container()

    # Título
    container.add_item(discord.ui.TextDisplay(
        content=f"# 👋 **BEM-VINDO(A) AO {member.guild.name.upper()}!**"
    ))

    # Avatar como link (melhor compatibilidade)
    avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
    container.add_item(discord.ui.TextDisplay(
        content=f"![Avatar]({avatar_url})"
    ))

    # Informações
    container.add_item(discord.ui.TextDisplay(
        content=f"### {member.mention}\n**{member}**"
    ))

    container.add_item(discord.ui.Separator())

    container.add_item(discord.ui.TextDisplay(
        content=f"**🆔 ID:** {member.id}"
    ))
    container.add_item(discord.ui.TextDisplay(
        content=f"**📅 Conta Criada:** {discord.utils.format_dt(member.created_at, 'R')}"
    ))
    if member.joined_at:
        container.add_item(discord.ui.TextDisplay(
            content=f"**📥 Entrou em:** {discord.utils.format_dt(member.joined_at, 'R')}"
        ))

    container.add_item(discord.ui.TextDisplay(
        content=f"**📊 Membros agora:** {member.guild.member_count}"
    ))

    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(
        content="💡 **Explore os canais, leia as regras e divirta-se na comunidade!**"
    ))

    container.add_item(discord.ui.TextDisplay(
        content=f"🕒 {discord.utils.utcnow().strftime('%d/%m/%Y %H:%M:%S')}"
    ))

    view = discord.ui.LayoutView()
    view.add_item(container)
    return view


def build_leave_ui(member: discord.Member):
    container = discord.ui.Container()

    container.add_item(discord.ui.TextDisplay(
        content="# 🔴 **MEMBRO SAIU DO SERVIDOR**"
    ))

    container.add_item(discord.ui.TextDisplay(
        content=f"**👤 Usuário:** {member.mention}\n**🆔 ID:** {member.id}"
    ))

    if member.joined_at:
        container.add_item(discord.ui.TextDisplay(
            content=f"**⏳ Ficou no servidor:** {discord.utils.format_dt(member.joined_at, 'R')}"
        ))

    container.add_item(discord.ui.TextDisplay(
        content=f"**📊 Membros restantes:** {member.guild.member_count}"
    ))

    container.add_item(discord.ui.TextDisplay(
        content=f"🕒 {discord.utils.utcnow().strftime('%d/%m/%Y %H:%M:%S')}"
    ))

    view = discord.ui.LayoutView()
    view.add_item(container)
    return view


# =========================
# COG PRINCIPAL
# =========================

class GuildMembers(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_group = app_commands.Group(name="config", description="Configurar boas-vindas e logs")
        self._register_slash_commands()

    def _register_slash_commands(self):
        @self.config_group.command(name="welcome_role", description="Definir cargo de boas-vindas")
        @app_commands.default_permissions(administrator=True)
        async def welcome_role(interaction: discord.Interaction, role: discord.Role):
            config = get_config(interaction.guild.id)
            config["welcome_role"] = role.id
            save_config(interaction.guild.id, config)
            await interaction.response.send_message(f"✅ Cargo definido: {role.mention}", ephemeral=True)

        @self.config_group.command(name="join_log", description="Definir canal de log de entrada")
        @app_commands.default_permissions(administrator=True)
        async def join_log(interaction: discord.Interaction, channel: discord.TextChannel):
            config = get_config(interaction.guild.id)
            config["join_log_channel"] = channel.id
            save_config(interaction.guild.id, config)
            await interaction.response.send_message(f"✅ Log de entrada: {channel.mention}", ephemeral=True)

        @self.config_group.command(name="leave_log", description="Definir canal de log de saída")
        @app_commands.default_permissions(administrator=True)
        async def leave_log(interaction: discord.Interaction, channel: discord.TextChannel):
            config = get_config(interaction.guild.id)
            config["leave_log_channel"] = channel.id
            save_config(interaction.guild.id, config)
            await interaction.response.send_message(f"✅ Log de saída: {channel.mention}", ephemeral=True)

    # ========================
    # EVENTS
    # ========================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or not _dedupe(member.guild.id, member.id, "join"):
            return

        config = get_config(member.guild.id)
        if not config:
            return

        # Auto Role
        if role_id := config.get("welcome_role"):
            if role := member.guild.get_role(role_id):
                try:
                    await member.add_roles(role, reason="Auto Welcome Role")
                except:
                    pass

        # Log no servidor
        if join_channel_id := config.get("join_log_channel"):
            if channel := member.guild.get_channel(join_channel_id):
                try:
                    await channel.send(view=build_join_ui(member))
                except Exception as e:
                    log("JOIN_LOG", str(e))

        # DM
        try:
            await member.send(view=build_join_ui(member))
        except:
            pass

        await event_bus.emit("member_join", member.guild.id, member.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not _dedupe(member.guild.id, member.id, "leave"):
            return

        config = get_config(member.guild.id)
        if not config:
            return

        if leave_channel_id := config.get("leave_log_channel"):
            if channel := member.guild.get_channel(leave_channel_id):
                try:
                    await channel.send(view=build_leave_ui(member))
                except Exception as e:
                    log("LEAVE_LOG", str(e))

        await event_bus.emit("member_leave", member.guild.id, member.id)


# =========================
# SETUP
# =========================

async def setup(bot: commands.Bot):
    cog = GuildMembers(bot)
    bot.tree.add_command(cog.config_group)
    await bot.add_cog(cog)
    log("SETUP", "Cog carregada com sucesso")