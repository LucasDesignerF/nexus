"""
Redis Connection Pool Manager with full method support
"""

import os
import json
import redis
from typing import Optional, Any, Set, List
from dotenv import load_dotenv

load_dotenv()


class RedisPool:
    """Gerenciador de conexão Redis com suporte a todos métodos necessários"""
    
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self._is_connected = False

    def connect(self) -> bool:
        """Estabelece conexão com Redis Cloud"""
        try:
            host = os.getenv('REDIS_HOST')
            port = int(os.getenv('REDIS_PORT', 6379))
            password = os.getenv('REDIS_PASSWORD')
            ssl = os.getenv('REDIS_SSL', 'false').lower() == 'true'
            
            if not host or not password:
                raise ValueError("REDIS_HOST e REDIS_PASSWORD são obrigatórios")
            
            # Configurar conexão
            self.client = redis.Redis(
                host=host,
                port=port,
                password=password,
                ssl=ssl,
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=10,
                retry_on_timeout=True,
                health_check_interval=30,
                max_connections=20
            )
            
            # Testar conexão
            self.client.ping()
            self._is_connected = True
            print("✅ Redis Cloud conectado com sucesso!")
            return True

        except Exception as e:
            print(f"❌ Erro ao conectar no Redis: {e}")
            self._is_connected = False
            return False

    def is_connected(self) -> bool:
        """Verifica se está conectado"""
        return self._is_connected and self.client is not None

    # --- Operações Básicas ---
    
    def get(self, key: str) -> Optional[Any]:
        """Obtém valor por chave"""
        if not self.is_connected():
            return None
        try:
            val = self.client.get(key)
            if val and isinstance(val, str):
                # Tentar fazer parse de JSON
                try:
                    return json.loads(val)
                except:
                    return val
            return val
        except Exception as e:
            print(f"[Redis] GET error: {e}")
            return None

    def set(self, key: str, value: Any, ex: int = None) -> bool:
        """Define valor para chave"""
        if not self.is_connected():
            return False
        try:
            # Serializar se for dict ou list
            if isinstance(value, (dict, list)):
                value = json.dumps(value, default=str)
            self.client.set(key, value, ex=ex)
            return True
        except Exception as e:
            print(f"[Redis] SET error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Deleta uma chave"""
        if not self.is_connected():
            return False
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            print(f"[Redis] DELETE error: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Verifica se chave existe"""
        if not self.is_connected():
            return False
        try:
            return self.client.exists(key) > 0
        except:
            return False

    def expire(self, key: str, seconds: int) -> bool:
        """Define expiração para chave"""
        if not self.is_connected():
            return False
        try:
            return self.client.expire(key, seconds)
        except Exception as e:
            print(f"[Redis] EXPIRE error: {e}")
            return False

    # --- Operações Numéricas ---
    
    def incr(self, key: str, amount: int = 1) -> int:
        """Incrementa valor numérico"""
        if not self.is_connected():
            return 0
        try:
            return self.client.incr(key, amount)
        except Exception as e:
            print(f"[Redis] INCR error: {e}")
            return 0

    def decr(self, key: str, amount: int = 1) -> int:
        """Decrementa valor numérico"""
        if not self.is_connected():
            return 0
        try:
            return self.client.decr(key, amount)
        except Exception as e:
            print(f"[Redis] DECR error: {e}")
            return 0

    # --- Operações com Sets ---
    
    def sadd(self, key: str, *values: str) -> int:
        """Adiciona valores a um set"""
        if not self.is_connected():
            return 0
        try:
            return self.client.sadd(key, *values)
        except Exception as e:
            print(f"[Redis] SADD error: {e}")
            return 0

    def srem(self, key: str, *values: str) -> int:
        """Remove valores de um set"""
        if not self.is_connected():
            return 0
        try:
            return self.client.srem(key, *values)
        except Exception as e:
            print(f"[Redis] SREM error: {e}")
            return 0

    def smembers(self, key: str) -> Set[str]:
        """Obtém todos membros de um set"""
        if not self.is_connected():
            return set()
        try:
            return self.client.smembers(key)
        except Exception as e:
            print(f"[Redis] SMEMBERS error: {e}")
            return set()

    def scard(self, key: str) -> int:
        """Conta membros de um set"""
        if not self.is_connected():
            return 0
        try:
            return self.client.scard(key)
        except Exception as e:
            print(f"[Redis] SCARD error: {e}")
            return 0

    def sismember(self, key: str, value: str) -> bool:
        """Verifica se valor está no set"""
        if not self.is_connected():
            return False
        try:
            return self.client.sismember(key, value)
        except Exception as e:
            print(f"[Redis] SISMEMBER error: {e}")
            return False

    # --- Pub/Sub ---
    
    def publish(self, channel: str, message: str) -> int:
        """Publica mensagem em canal"""
        if not self.is_connected():
            return 0
        try:
            return self.client.publish(channel, message)
        except Exception as e:
            print(f"[Redis] PUBLISH error: {e}")
            return 0

    def get_pubsub(self):
        """Retorna objeto PubSub"""
        if not self.is_connected():
            return None
        try:
            return self.client.pubsub()
        except Exception as e:
            print(f"[Redis] PUBSUB error: {e}")
            return None

    # --- Utilitários ---
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Lista chaves que correspondem ao padrão"""
        if not self.is_connected():
            return []
        try:
            return self.client.keys(pattern)
        except Exception as e:
            print(f"[Redis] KEYS error: {e}")
            return []

    def flush_all(self) -> bool:
        """Limpa todos os dados (cuidado!)"""
        if not self.is_connected():
            return False
        try:
            self.client.flushall()
            return True
        except Exception as e:
            print(f"[Redis] FLUSHALL error: {e}")
            return False

    def close(self):
        """Fecha conexão Redis"""
        if self.client:
            self.client.close()
            self.client = None
            self._is_connected = False
            print("🔌 Redis conexão fechada")


# Singleton instance
redis_pool = RedisPool()