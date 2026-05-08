"""
Event Bus System for inter-module communication
"""

import asyncio
import json
from typing import Callable, Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict

from pool.redis import redis_pool


class EventBus:
    """Sistema de eventos assíncrono com suporte a Redis"""
    
    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = defaultdict(list)
        self.middlewares: List[Callable] = []
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    def on(self, event_name: str):
        """Decorator para registrar listeners de eventos"""
        def decorator(func: Callable):
            self.listeners[event_name].append(func)
            return func
        return decorator

    def use(self, middleware: Callable):
        """Adiciona middleware para processar eventos"""
        self.middlewares.append(middleware)

    async def _run_middlewares(self, event: dict) -> dict:
        """Executa todos os middlewares no evento"""
        for mw in self.middlewares:
            try:
                if asyncio.iscoroutinefunction(mw):
                    event = await mw(event)
                else:
                    event = mw(event)
            except Exception as e:
                print(f"[EventBus Middleware] Error: {e}")
        return event

    async def emit(self, event_name: str, guild_id: int, 
                   user_id: int = None, payload: dict = None):
        """Emite um evento para todos os listeners e Redis"""
        event = {
            "name": event_name,
            "guild_id": guild_id,
            "user_id": user_id,
            "payload": payload or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        # Aplicar middlewares
        event = await self._run_middlewares(event)

        # Publicar no Redis (distribuído)
        try:
            redis_pool.publish("nexus:events", json.dumps(event, default=str))
        except Exception as e:
            print(f"[EventBus] Redis publish error: {e}")

        # Processar localmente
        await self._dispatch(event)

    async def _dispatch(self, event: dict):
        """Despacha evento para listeners locais"""
        name = event["name"]
        if name not in self.listeners:
            return
        
        # Executar todos os handlers em paralelo
        tasks = []
        for handler in self.listeners[name]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(asyncio.create_task(handler(event)))
                else:
                    # Executar função síncrona em thread pool
                    tasks.append(asyncio.to_thread(handler, event))
            except Exception as e:
                print(f"[EventBus] Handler error for {name}: {e}")
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def start_worker(self):
        """Inicia worker para processar fila de eventos"""
        self._worker_task = asyncio.create_task(self._process_queue())

    async def _process_queue(self):
        """Processa eventos da fila"""
        while True:
            try:
                event = await self._event_queue.get()
                await self._dispatch(event)
                self._event_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[EventBus] Queue worker error: {e}")

    async def stop(self):
        """Para o worker de eventos"""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass


# Singleton instance
event_bus = EventBus()