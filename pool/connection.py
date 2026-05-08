"""
MongoDB Connection Pool Manager
"""

import os
from typing import Optional, Dict, Any
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from dotenv import load_dotenv

load_dotenv()


class MongoPool:
    """Gerenciador de conexão MongoDB com singleton pattern"""
    
    def __init__(self):
        self.client: Optional[MongoClient] = None
        self.db = None
        self._is_connected = False

    def connect(self) -> bool:
        """Estabelece conexão com MongoDB"""
        try:
            uri = os.getenv("MONGO_URI")
            db_name = os.getenv("MONGO_DB", "nexus")
            
            if not uri:
                raise ValueError("MONGO_URI não configurado")
            
            # Configurar cliente com opções otimizadas
            self.client = MongoClient(
                uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=30000,
                maxPoolSize=10,
                minPoolSize=2,
                retryWrites=True
            )
            
            # Testar conexão
            self.client.admin.command('ping')
            
            self.db = self.client[db_name]
            self._is_connected = True
            print("✅ MongoDB conectado com sucesso!")
            return True

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            print(f"❌ MongoDB erro de conexão: {e}")
            self._is_connected = False
            return False
        except Exception as e:
            print(f"❌ MongoDB erro: {e}")
            self._is_connected = False
            return False

    def get_collection(self, collection_name: str):
        """Obtém uma coleção do MongoDB"""
        if not self._is_connected or self.db is None:
            if not self.connect():
                raise ConnectionError("Não foi possível conectar ao MongoDB")
        
        return self.db[collection_name]

    def is_connected(self) -> bool:
        """Verifica se está conectado"""
        return self._is_connected and self.client is not None

    def close(self):
        """Fecha a conexão com MongoDB"""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            self._is_connected = False
            print("🔌 MongoDB conexão fechada")


# Singleton instance
mongo_pool = MongoPool()