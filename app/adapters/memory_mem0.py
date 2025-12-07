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
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
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
            
            # DEBUG: Print to help diagnose return types
            print(f"[Mem0 DEBUG] Search returned type: {type(results)}")

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