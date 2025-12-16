import logging
import os
from typing import Any, Dict, List, Optional
from mem0 import Memory

from app.domain.ports import MemoryPort

logger = logging.getLogger(__name__)

class Mem0Adapter(MemoryPort):
    def __init__(self):
        # Configuration for Local Execution (Free)
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "embedding_model_dims": 384,
                    "collection_name": "eve_memories_fixed",
                    "path": "./eve_memory_local", 
                }
            },
            "graph_store": {
                "provider": "kuzu",  # Local embedded graph DB
                "config": {
                    "db_path": "./db/kuzu_graph"
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "Qwen/Qwen3-14B-AWQ",
                    "temperature": 0.1,
                    "max_tokens": 1000,
                    "openai_base_url": "http://localhost:8000/v1",
                    "api_key": "EMPTY"
                }
            },
            "embedder": {
                "provider": "huggingface",
                "config": {
                    "model": "multi-qa-MiniLM-L6-cos-v1",
                    "model_kwargs": {"device": "cpu"}
                }
            }
        }

        try:
            logger.info("Initializing Mem0 with local configuration (Qdrant + vLLM + HF)...")
            self.client = Memory.from_config(config)
            logger.info("Mem0 initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Mem0 client: {e}")
            self.client = None

    def add(self, text: str, user_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Stores interaction in both Vector and Graph stores"""
        if not self.client:
            return
        try:
            self.client.add(text, user_id=user_id, metadata=metadata or {})
        except Exception as e:
            logger.error(f"Error adding to Mem0: {e}")

    def search(self, query: str, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        try:
            results = self.client.search(query, user_id=user_id, limit=limit)

            # If we don't do this, iterating over 'results' just gives us the key strings ("results")
            if isinstance(results, dict):
                results = results.get("results", [])
            
            normalized = []
            for r in results:
                if isinstance(r, dict):
                    normalized.append(r)
                elif isinstance(r, str):
                    normalized.append({"memory": r, "text": r, "score": 1.0})
                else:
                    # Handle objects (like Pydantic models)
                    try:
                        if hasattr(r, "model_dump"):
                            normalized.append(r.model_dump())
                        elif hasattr(r, "to_dict"):
                             normalized.append(r.to_dict())
                        else:
                             val = str(r)
                             normalized.append({"memory": val, "text": val, "score": 1.0})
                    except Exception:
                        val = str(r)
                        normalized.append({"memory": val, "text": val, "score": 1.0})
                    
            return normalized
        except Exception as e:
            logger.error(f"Error searching Mem0: {e}")
            return []

    def get_context(self, query: str, user_id: str) -> Dict[str, Any]:
        """
        Retrieves the 'Context Sandwich' for the Planner.
        Combines vector similarity search with graph relationships.
        
        Args:
            query: The current user query
            user_id: User identifier
            
        Returns:
            Dictionary with relevant_history and user_directives
        """
        if not self.client:
            return {
                "relevant_history": [],
                "user_directives": self._get_hardcoded_directives()
            }
        
        try:
            # 1. Search Vector (Similar past conversations)
            history = self.search(query, user_id=user_id, limit=5)
            
            # 2. Search Graph (Entities & Relationships)
            # Mem0 v1.1+ automatically includes relations in search results if graph is enabled
            # The graph store enriches the context with entity relationships
            
            return {
                "relevant_history": [h.get('memory', h.get('text', '')) for h in history],
                "user_directives": self._get_hardcoded_directives(),
                "metadata": {
                    "context_count": len(history),
                    "graph_enabled": True
                }
            }
        except Exception as e:
            logger.error(f"Error getting context from memory: {e}")
            return {
                "relevant_history": [],
                "user_directives": self._get_hardcoded_directives()
            }

    def _get_hardcoded_directives(self) -> List[str]:
        """
        These act as the 'Constitution' - core behavioral rules.
        These directives are always included in the context.
        """
        return [
            "Always output Python code for complex tasks.",
            "Do not delete files outside /workspace.",
            "User prefers concise answers.",
            "When executing code, ensure proper error handling.",
            "Prioritize security and data privacy.",
            "Use the sandbox environment for all code execution.",
            "Provide explanations for complex operations."
        ]