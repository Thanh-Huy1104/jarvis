import ast
import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Optional, Any
import chromadb
from chromadb.utils import embedding_functions
from app.core.skills import PendingSkillManager

logger = logging.getLogger(__name__)

@dataclass
class ToolDefinition:
    name: str
    description: str
    signature: str
    parameters: Dict[str, Any]
    file_path: str

class SkillRegistry:
    """
    Manages the library of Python skills.
    Extracts metadata via AST and stores it in ChromaDB for semantic search.
    """
    
    def __init__(self, db_path="./db/chroma", library_dir=".jarvis/skills/library"):
        self.library_dir = Path(library_dir).resolve()
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.pending = PendingSkillManager() # Re-added for skill proposal
        
        try:
            self.client = chromadb.PersistentClient(path=db_path)
            self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self.collection = self.client.get_or_create_collection(
                name="jarvis_tools",
                embedding_function=self.emb_fn
            )
            logger.info(f"SkillRegistry initialized with {self.collection.count()} tools")
            
            # Initial sync
            self.sync_library()
            
        except Exception as e:
            logger.error(f"Failed to initialize SkillRegistry: {e}")
            self.collection = None

    def _parse_skill_file(self, file_path: Path) -> Optional[ToolDefinition]:
        """Parses a Python file to extract the main skill function metadata."""
        try:
            with open(file_path, "r") as f:
                tree = ast.parse(f.read())
            
            # Heuristic: Find the function that matches the filename or the first function
            target_func_name = file_path.stem
            func_node = None
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name == target_func_name:
                        func_node = node
                        break
                    if func_node is None: # Fallback to first function found
                        func_node = node
            
            if not func_node:
                return None
            
            # Extract docstring
            description = ast.get_docstring(func_node) or "No description provided."
            
            # Extract parameters and build signature
            params = []
            param_meta = {}
            
            for arg in func_node.args.args:
                arg_name = arg.arg
                # Try to get type hint
                type_hint = "Any"
                if arg.annotation:
                    if isinstance(arg.annotation, ast.Name):
                        type_hint = arg.annotation.id
                    elif isinstance(arg.annotation, ast.Constant):
                        type_hint = str(arg.annotation.value)
                
                params.append(f"{arg_name}: {type_hint}")
                param_meta[arg_name] = type_hint
            
            signature = f"{func_node.name}({', '.join(params)})"
            
            return ToolDefinition(
                name=func_node.name,
                description=description.strip(),
                signature=signature,
                parameters=param_meta,
                file_path=str(file_path)
            )
            
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return None

    def sync_library(self):
        """Syncs the filesystem library with ChromaDB."""
        if not self.collection: return
        
        logger.info("Syncing Skill Library...")
        py_files = list(self.library_dir.glob("*.py"))
        
        # Remove __init__.py from sync
        py_files = [f for f in py_files if f.name != "__init__.py"]
        
        ids = []
        documents = []
        metadatas = []
        
        for py_file in py_files:
            tool = self._parse_skill_file(py_file)
            if tool:
                ids.append(tool.name)
                # We store the description as the document for semantic search
                documents.append(tool.description)
                metadatas.append({
                    "signature": tool.signature,
                    "parameters": json.dumps(tool.parameters),
                    "file_path": tool.file_path
                })
        
        if ids:
            self.collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"Synced {len(ids)} tools to registry")

    def save_skill(self, name: str, code: str, description: str = None, full_content: str = None) -> bool:
        """
        Saves a verified skill to the library filesystem and updates the registry.
        
        Args:
            name: The name of the skill (filename without extension)
            code: The pure Python code of the skill
            description: (Optional) Description of the skill
            full_content: (Optional) Ignored in pure-python mode, kept for compatibility
        """
        try:
            # Ensure filename is safe
            safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-')).strip()
            file_path = self.library_dir / f"{safe_name}.py"
            
            # Write code to file
            with open(file_path, "w") as f:
                f.write(code)
                
            logger.info(f"Saved skill file: {file_path}")
            
            # Update registry
            self.sync_library()
            return True
            
        except Exception as e:
            logger.error(f"Failed to save skill '{name}': {e}")
            return False

    def find_tools(self, query: str, n: int = 3, threshold: float = 1.5) -> List[ToolDefinition]:
        """Finds relevant tools based on a query."""
        if not self.collection: return []
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n
            )
            
            tools = []
            for i in range(len(results['ids'][0])):
                if results['distances'][0][i] < threshold:
                    meta = results['metadatas'][0][i]
                    tools.append(ToolDefinition(
                        name=results['ids'][0][i],
                        description=results['documents'][0][i],
                        signature=meta['signature'],
                        parameters=json.loads(meta['parameters']),
                        file_path=meta['file_path']
                    ))
            return tools
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Retrieves a specific tool definition by name."""
        if not self.collection: return None
        try:
            res = self.collection.get(ids=[name])
            if res['ids']:
                meta = res['metadatas'][0]
                return ToolDefinition(
                    name=res['ids'][0],
                    description=res['documents'][0],
                    signature=meta['signature'],
                    parameters=json.loads(meta['parameters']),
                    file_path=meta['file_path']
                )
            return None
        except Exception as e:
            logger.error(f"Error getting tool {name}: {e}")
            return None

    def get_tool_definitions_prompt(self, tools: List[ToolDefinition]) -> str:
        """Formats tools for inclusion in an LLM prompt."""
        if not tools:
            return "No specialized tools found for this task."
        
        prompt = "Available Tools (Pre-loaded in your environment):\n"
        for tool in tools:
            prompt += f"- {tool.signature}: {tool.description}\n"
        return prompt
