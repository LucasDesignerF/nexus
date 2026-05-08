"""
Pool module - Gerencia conexões com bancos de dados
"""

from .connection import mongo_pool
from .redis import redis_pool
from .event_bus import event_bus

__all__ = ['mongo_pool', 'redis_pool', 'event_bus']