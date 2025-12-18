import logging
import os
from typing import Any, Dict, List, Optional
from mem0 import AsyncMemory
from mem0.configs.base import MemoryConfig

from app.domain.ports import MemoryPort

logger = logging.getLogger(__name__)

class Mem0Adapter(MemoryPort):
    def __init__(self):
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = os.getenv("QDRANT_PORT", "6333")
        
        neo4j_url = os.getenv("NEO4J_URL", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USERNAME", "neo4j")
        neo4j_pass = os.getenv("NEO4J_PASSWORD", "neo4j-password")
        
        custom_config = MemoryConfig(
            vector_store={
                "provider": "qdrant",
                "config": {
                    "host": qdrant_host,
                    "port": qdrant_port,
                    "collection_name": "eve_memories_fixed",
                    "embedding_model_dims": 384,  # must match your embedder output dims
                },
            },
            graph_store={
                "provider": "neo4j",
                "config": {
                    "url": neo4j_url,
                    "username": neo4j_user,
                    "password": neo4j_pass,
                    "database": "neo4j",
                    # Optional: reduce noisy edges by raising extraction confidence threshold
                    "threshold": 0.75,
                },
            },
            llm={
                # Option A (recommended): use Mem0's vLLM provider
                # See vLLM provider params in Mem0 docs. :contentReference[oaicite:5]{index=5}
                "provider": "vllm",
                "config": {
                    "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                    "vllm_base_url": os.getenv("VLLM_SPEED_BASE_URL", "http://localhost:8001/v1"),
                    "api_key": os.getenv("VLLM_API_KEY", "vllm-api-key"),
                    "temperature": 0.0,
                    "max_tokens": 500,
                },
            },
            embedder={
                "provider": "huggingface",
                "config": {
                    "model": "multi-qa-MiniLM-L6-cos-v1",
                    "model_kwargs": {"device": "cuda"},
                },
            },
            custom_prompt=(
                "You are a memory management system. Your job is to extract and store "
                "important information from conversations.\n\n"
                "ALWAYS save these types of information:\n"
                "- User's name, preferences, and personal details\n"
                "- Important facts about the user\n"
                "- User's goals, tasks, or requests\n"
                "- Technical details, configurations, or decisions made\n"
                "- Relationships between entities\n\n"
                "Extract factual information and save it in a clear, concise format."
            )
        )
        

        try:
            self.client = AsyncMemory(config=custom_config)
            logger.info("Mem0 initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Mem0 client: {e}")
            self.client = None

    async def add(self, text: str, user_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Stores interaction in both Vector and Graph stores"""
        if not self.client:
            return
        try:
            result = await self.client.add(text, user_id=user_id, metadata=metadata or {})
            logger.info(f"Mem0 add result: {result}")
            
            # Check if memory was actually saved
            if isinstance(result, dict):
                event = result.get('event', 'UNKNOWN')
                if event == 'NOOP':
                    logger.warning(f"Mem0 decided NOOP (not saved): {text[:100]}...")
                elif event in ['ADD', 'UPDATE']:
                    logger.info(f"✓ Memory {event}: {result.get('id', 'no-id')}")
        except Exception as e:
            logger.error(f"Error adding to Mem0: {e}")

    async def search(self, query: str, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        res = await self.client.search(query=query, user_id=user_id, limit=limit)
        results = res.get("results", []) if isinstance(res, dict) else []
        return results

    async def get_context(self, query: str, user_id: str) -> Dict[str, Any]:
        history = await self.search(query, user_id=user_id, limit=5)
        if self.client:
            all_memories = await self.client.get_all(user_id=user_id)
            recent = (all_memories.get("results", []) if isinstance(all_memories, dict) else all_memories) or []
            recent = sorted(recent, key=lambda x: x.get("created_at", ""), reverse=True)[:10][::-1]
        else:
            recent = []

        return {
            "relevant_history": [h.get("memory", h.get("text", "")) for h in history],
            "recent_history": [r.get("memory", r.get("text", "")) for r in recent],
            "user_directives": self._get_hardcoded_directives(),
            "metadata": {
                "context_count": len(history),
                "recent_count": len(recent),
                "graph_enabled": True,
            },
        }

    def _get_hardcoded_directives(self) -> List[str]:
        return [
            "Always output Python code for complex tasks.",
            "Do not delete files outside /workspace.",
            "User prefers concise answers.",
            "When executing code, ensure proper error handling.",
            "Prioritize security and data privacy.",
            "Use the sandbox environment for all code execution.",
            "Provide explanations for complex operations."
        ]