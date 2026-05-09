"""
Nexus Bot - Main Entry Point
Sistema SaaS com MongoDB + Redis Cloud + EventBus V2.2
"""

import os
import asyncio
import signal
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Adicionar root ao path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from pool.connection import mongo_pool
from pool.redis import redis_pool
from pool.event_bus import event_bus

# =========================
# 🔧 ENV & CONFIG
# =========================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ DISCORD_TOKEN não definido no .env")

# Configurações
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
STATUS_CHANNEL = os.getenv("STATUS_CHANNEL")  # Opcional


# =========================
# 🎨 LOG SYSTEM MELHORADO (MAIS LIMPO)
# =========================

class Logger:
    """Sistema de logging melhorado e limpo"""
    
    COLORS = {
        'INFO': '\033[92m',    # Verde
        'WARN': '\033[93m',    # Amarelo
        'ERROR': '\033[91m',   # Vermelho
        'SUCCESS': '\033[96m', # Ciano
        'RESET': '\033[0m'
    }
    
    @staticmethod
    def _log(level: str, msg: str, color: str, emoji: str):
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"{color}[{timestamp}] {emoji} {level:7} | {msg}{Logger.COLORS['RESET']}", flush=True)
    
    @classmethod
    def info(cls, msg: str):
        cls._log("INFO", msg, cls.COLORS['INFO'], "🟢")
    
    @classmethod
    def warn(cls, msg: str):
        cls._log("WARN", msg, cls.COLORS['WARN'], "🟡")
    
    @classmethod
    def error(cls, msg: str):
        cls._log("ERROR", msg, cls.COLORS['ERROR'], "🔴")
    
    @classmethod
    def success(cls, msg: str):
        cls._log("SUCCESS", msg, cls.COLORS['SUCCESS'], "🟣")

# Aliases para compatibilidade
log_info = Logger.info
log_warn = Logger.warn
log_error = Logger.error
log_success = Logger.success


# =========================
# 🤖 INTENTS
# =========================

intents = discord.Intents.all()


# =========================
# 🧠 BOT CORE MELHORADO
# =========================

class NexusBot(commands.Bot):
    """Bot principal com sistema de shutdown seguro"""

    def __init__(self):
        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            help_command=None,
            activity=discord.Activity(
                type=discord.ActivityType.custom,
                name="Nexus Bot",
                state="Inicializando..."
            )
        )
        self.start_time = datetime.now(timezone.utc)
        self._shutdown_requested = False

    async def setup_hook(self):
        """Hook executado antes do bot iniciar"""
        log_info("Inicializando Nexus Bot (SaaS Core V2.2)...")
        
        # Inicializar conexões
        await self.init_databases()
        
        # Configurar EventBus
        await self.setup_event_bus()
        
        # Carregar Cogs (logs silenciosos)
        await self.load_all_cogs()
        
        # Registrar views persistentes
        await self.register_persistent_views()
        
        log_success("Setup hook concluído")

    async def init_databases(self):
        """Inicializa conexões com bancos de dados"""
        
        # MongoDB
        try:
            if mongo_pool.connect():
                log_success("MongoDB conectado")
            else:
                log_error("Falha ao conectar MongoDB")
        except Exception as e:
            log_error(f"MongoDB erro: {e}")

        # Redis
        try:
            if redis_pool.connect():
                # Testar Redis com operações básicas
                redis_pool.set("nexus:status", "booting", ex=60)
                redis_pool.set("nexus:boot_time", str(datetime.now(timezone.utc)))
                log_success("Redis inicializado")
            else:
                log_error("Falha ao conectar ao Redis")
        except Exception as e:
            log_error(f"Redis erro: {e}")

    async def setup_event_bus(self):
        """Configura middleware do EventBus"""
        try:
            async def audit_middleware(event: dict) -> dict:
                """Middleware para auditoria de eventos"""
                event["processed_by"] = "nexus-core-v2"
                event["bot_start_time"] = self.start_time.isoformat()
                return event

            event_bus.use(audit_middleware)
            log_success("EventBus middleware registrado")
        except Exception as e:
            log_error(f"EventBus middleware erro: {e}")

    async def load_all_cogs(self):
        """Carrega todos os cogs da pasta cogs/ (modo silencioso)"""
        cogs_loaded = 0
        cogs_failed = 0
        
        base = Path("cogs")
        if not base.exists():
            log_warn("cogs/ não encontrado - criando diretório")
            base.mkdir(parents=True)
            return

        for file in base.rglob("*.py"):
            if file.name.startswith("_"):
                continue
            
            module = str(file).replace("\\", ".").replace("/", ".")[:-3]
            
            try:
                await self.load_extension(module)
                cogs_loaded += 1
            except Exception as e:
                log_error(f"Erro cog {module}: {e}")
                cogs_failed += 1
        
        # Resumo compacto (apenas total, sem listar cada cog)
        log_info(f"Cogs: {cogs_loaded} carregadas | {cogs_failed} falhas")

    async def register_persistent_views(self):
        """Registra views persistentes para o bot"""
        try:
            from cogs.utils.temp_mail import PainelEmailTemp
            from cogs.utils.temp_number import PainelNumeroTemp
            from cogs.system.register import RegisterPanelView
            
            # Registrar views
            self.add_view(PainelEmailTemp())
            self.add_view(PainelNumeroTemp())
            
            log_success("Views persistentes registradas")
        except ImportError as e:
            log_warn(f"Views: {e}")
        except Exception as e:
            log_error(f"Erro ao registrar views: {e}")

    async def on_ready(self):
        """Evento disparado quando o bot está pronto"""
        if hasattr(self, '_ready_done'):
            return
        
        self._ready_done = True
        log_success(f"Logado como {self.user} 🚀")
        
        # Sincronizar comandos slash
        await self.sync_slash_commands()
        
        # Atualizar status
        await self.update_bot_status()
        
        # Atualizar Redis com status
        await self.update_redis_status()
        
        # Resumo dos servidores (mais compacto)
        log_info(f"Conectado em {len(self.guilds)} servidor(es)")
        for guild in self.guilds:
            log_info(f"  └ {guild.name} | {guild.member_count} membros")
        
        log_success("Bot operacional!")

    async def sync_slash_commands(self):
        """Sincroniza comandos slash com o Discord"""
        try:
            synced = await self.tree.sync()
            log_success(f"{len(synced)} comandos slash sincronizados")
        except Exception as e:
            log_error(f"Erro ao sincronizar: {e}")

    async def update_bot_status(self):
        """Atualiza o status personalizado do bot"""
        try:
            activities = [
                discord.Activity(
                    type=discord.ActivityType.custom,
                    name="Nexus Bot",
                    state=f"✨ Em {len(self.guilds)} servidores"
                ),
                discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{len(self.users)} usuários"
                ),
                discord.Activity(
                    type=discord.ActivityType.listening,
                    name="/help"
                )
            ]
            
            async def rotate_status():
                index = 0
                while not self.is_closed():
                    await self.change_presence(
                        status=discord.Status.online,
                        activity=activities[index % len(activities)]
                    )
                    index += 1
                    await asyncio.sleep(30)
            
            self.loop.create_task(rotate_status())
            log_success("Status configurado")
            
        except Exception as e:
            log_error(f"Erro status: {e}")

    async def update_redis_status(self):
        """Atualiza status no Redis"""
        try:
            redis_pool.set("nexus:status", "online")
            redis_pool.set("nexus:guilds", str(len(self.guilds)))
            redis_pool.set("nexus:users", str(len(self.users)))
        except Exception as e:
            log_warn(f"Redis status: {e}")

    async def on_guild_join(self, guild: discord.Guild):
        """Evento ao entrar em um novo servidor"""
        log_info(f"+ Servidor: {guild.name} | {guild.member_count} membros")
        
        try:
            redis_pool.set(f"guild:{guild.id}:status", "active", ex=3600)
            redis_pool.set("nexus:guilds", str(len(self.guilds)))
        except:
            pass

    async def on_guild_remove(self, guild: discord.Guild):
        """Evento ao sair de um servidor"""
        log_info(f"- Servidor: {guild.name}")
        
        try:
            redis_pool.delete(f"guild:{guild.id}:status")
            redis_pool.set("nexus:guilds", str(len(self.guilds)))
        except:
            pass

    async def close(self):
        """Shutdown seguro do bot"""
        if self._shutdown_requested:
            return
        
        self._shutdown_requested = True
        log_info("Shutdown em andamento...")
        
        try:
            redis_pool.set("nexus:status", "offline")
        except:
            pass
        
        mongo_pool.close()
        redis_pool.close()
        
        await super().close()
        log_success("Bot finalizado")


# =========================
# 🚀 START
# =========================

async def main():
    """Função principal do bot"""
    bot = NexusBot()
    
    # Configurar handlers de sinal
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        log_warn("Sinal de shutdown recebido")
        asyncio.create_task(bot.close())
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass
    
    try:
        await bot.start(TOKEN)
    except KeyboardInterrupt:
        log_warn("Interrupção manual")
    except Exception as e:
        log_error(f"Erro: {e}")
        raise
    finally:
        if not bot._shutdown_requested:
            await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[⚠️] Bot finalizado.")
    except Exception as e:
        print(f"\n[❌] Erro fatal: {e}")