"""
Skill Library
-------------
Stores and retrieves reusable Python code snippets using semantic search.
This allows the agent to learn from past successful executions.
Loads skills from ~/.jarvis/skills/*.md files on initialization.
"""

import logging
import chromadb
from chromadb.utils import embedding_functions
from typing import Optional, List, Dict
from pathlib import Path
import re
import json
import uuid
import time
import os

logger = logging.getLogger(__name__)


class PendingSkillManager:
    """
    Manages a queue of skills awaiting approval.
    Stores pending skills as JSON files in a dedicated directory.
    """
    
    def __init__(self, pending_dir="jarvis_data/pending_skills"):
        self.pending_dir = Path(pending_dir)
        if not self.pending_dir.is_absolute():
             project_root = Path(__file__).resolve().parent.parent.parent
             self.pending_dir = project_root / pending_dir
        
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"PendingSkillManager initialized at {self.pending_dir}")

    def add_pending_skill(self, code: str, description: str, name: str = None) -> str:
        """
        Adds a new skill to the pending queue.
        Returns the ID of the pending skill.
        """
        skill_id = str(uuid.uuid4())
        timestamp = time.time()
        
        if not name:
            name = f"skill_{int(timestamp)}"
            
        data = {
            "id": skill_id,
            "name": name,
            "code": code,
            "description": description,
            "status": "pending",
            "created_at": timestamp,
            "notes": "Auto-generated suggestion"
        }
        
        file_path = self.pending_dir / f"{skill_id}.json"
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Added pending skill: {name} ({skill_id})")
            return skill_id
        except Exception as e:
            logger.error(f"Failed to save pending skill: {e}")
            return None

    def list_pending_skills(self) -> List[Dict]:
        """Lists all pending skills."""
        skills = []
        if not self.pending_dir.exists():
            return []
            
        for file_path in self.pending_dir.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    skills.append(json.load(f))
            except Exception as e:
                logger.error(f"Error reading pending skill {file_path}: {e}")
        
        # Sort by newest first
        return sorted(skills, key=lambda x: x.get('created_at', 0), reverse=True)

    def get_pending_skill(self, skill_id: str) -> Optional[Dict]:
        """Retrieves a specific pending skill."""
        file_path = self.pending_dir / f"{skill_id}.json"
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading pending skill {skill_id}: {e}")
            return None

    def update_pending_skill(self, skill_id: str, code: str = None, name: str = None, description: str = None, notes: str = None) -> bool:
        """Updates a pending skill."""
        skill = self.get_pending_skill(skill_id)
        if not skill:
            return False
        
        if code is not None: skill['code'] = code
        if name is not None: skill['name'] = name
        if description is not None: skill['description'] = description
        if notes is not None: skill['notes'] = notes
        
        file_path = self.pending_dir / f"{skill_id}.json"
        try:
            with open(file_path, 'w') as f:
                json.dump(skill, f, indent=2)
            logger.info(f"Updated pending skill: {skill['name']} ({skill_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to update pending skill: {e}")
            return False

    def delete_pending_skill(self, skill_id: str) -> bool:
        """Deletes a pending skill (rejection)."""
        file_path = self.pending_dir / f"{skill_id}.json"
        if not file_path.exists():
            return False
            
        try:
            os.remove(file_path)
            logger.info(f"Deleted pending skill: {skill_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete pending skill: {e}")
            return False


class SkillLibrary:
    """
    A semantic code snippet library using ChromaDB.
    Stores Python code with descriptions for retrieval.
    Automatically loads skills from .jarvis/skills/*.md on init.
    """
    
    def __init__(self, db_path="./db/chroma", skills_dir=".jarvis/skills"):
        """
        Initialize the skill library.
        
        Args:
            db_path: Path to ChromaDB persistent storage
            skills_dir: Directory containing markdown skill files (relative to project root)
        """
        self.pending = PendingSkillManager()
        
        try:
            self.client = chromadb.PersistentClient(path=db_path)
            
            # Use same embedding model as router for consistency
            self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            
            self.collection = self.client.get_or_create_collection(
                name="jarvis_skills", 
                embedding_function=self.emb_fn
            )
            
            logger.info(f"SkillLibrary initialized with {self.collection.count()} skills")
            
            # Load skills from markdown files
            self._load_skills_from_markdown(skills_dir)
            
        except Exception as e:
            logger.error(f"Failed to initialize SkillLibrary: {e}")
            self.collection = None
    
    def _load_skills_from_markdown(self, skills_dir: str):
        """
        Load skills from markdown files in the skills directory.
        
        Markdown format:
        # Skill Title
        
        Description of the skill.
        
        ## Code
        
        ```python
        code here
        ```
        """
        # Support both absolute and relative paths
        skills_path = Path(skills_dir)
        if not skills_path.is_absolute():
            # Relative to project root (where app/ folder is)
            project_root = Path(__file__).resolve().parent.parent.parent
            skills_path = project_root / skills_dir
        
        skills_path = skills_path.expanduser()
        
        if not skills_path.exists():
            logger.warning(f"Skills directory not found: {skills_path}")
            return
        
        md_files = list(skills_path.glob("*.md"))
        logger.info(f"Found {len(md_files)} markdown skill files in {skills_path}")
        
        for md_file in md_files:
            try:
                content = md_file.read_text()
                
                # Extract title (first # heading)
                title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                title = title_match.group(1) if title_match else md_file.stem
                
                # Extract description (text before ## Code)
                desc_match = re.search(r'^#\s+.+?\n\n(.+?)(?=\n##|\Z)', content, re.DOTALL | re.MULTILINE)
                description = desc_match.group(1).strip() if desc_match else title
                
                # Extract code from ```python code blocks
                code_match = re.search(r'```python\n(.+?)\n```', content, re.DOTALL)
                if not code_match:
                    logger.warning(f"No Python code block found in {md_file.name}")
                    continue
                
                code = code_match.group(1)
                
                # Use filename (without .md) as skill ID
                skill_id = md_file.stem
                
                # Save to ChromaDB
                self.save_skill(skill_id, code, description)
                logger.info(f"Loaded skill '{skill_id}' from {md_file.name}")
                
            except Exception as e:
                logger.error(f"Error loading skill from {md_file.name}: {e}")

    def find_skill(self, query: str, threshold: float = 1.2) -> Optional[str]:
        """
        Finds the most relevant Python code snippet based on the task description.
        
        Args:
            query: Task description (e.g., "read a CSV file and calculate statistics")
            threshold: Distance threshold (lower = stricter, < 1.0 = very similar)
            
        Returns:
            Python code string if found, None otherwise
        """
        if not self.collection:
            return None
        
        try:
            results = self.collection.query(
                query_texts=[query], 
                n_results=1
            )
            
            # Check if we have results and distance is below threshold
            if (results['ids'] and 
                results['distances'] and 
                results['distances'][0] and 
                results['distances'][0][0] < threshold):
                
                code = results['metadatas'][0][0].get('code', '')
                skill_name = results['ids'][0][0]
                distance = results['distances'][0][0]
                
                logger.info(f"Found skill '{skill_name}' with distance {distance:.3f}")
                return code
            
            logger.debug(f"No relevant skill found for: {query[:50]}...")
            return None
            
        except Exception as e:
            logger.error(f"Error searching skills: {e}")
            return None

    def find_top_skills(self, query: str, n: int = 3, threshold: float = 1.5) -> List[Dict[str, str]]:
        """
        Finds multiple relevant skills.
        
        Args:
            query: Task description
            n: Number of results to return
            threshold: Maximum distance threshold
            
        Returns:
            List of dicts with 'name', 'code', 'description', 'distance'
        """
        if not self.collection:
            return []
        
        try:
            results = self.collection.query(
                query_texts=[query], 
                n_results=n
            )
            
            skills = []
            for i in range(len(results['ids'][0])):
                distance = results['distances'][0][i]
                
                if distance < threshold:
                    skills.append({
                        'name': results['ids'][0][i],
                        'code': results['metadatas'][0][i].get('code', ''),
                        'description': results['documents'][0][i],
                        'distance': distance
                    })
            
            return skills
            
        except Exception as e:
            logger.error(f"Error searching skills: {e}")
            return []

    def save_skill(self, name: str, code: str, description: str) -> bool:
        """
        Saves or updates a code snippet in the library.
        
        Args:
            name: Unique identifier for the skill
            code: Python code to store
            description: Natural language description (used for semantic search)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.collection:
            logger.error("Cannot save skill: collection not initialized")
            return False
        
        try:
            self.collection.upsert(
                ids=[name],
                documents=[description],  # This is what we search against
                metadatas=[{
                    "code": code,
                    "name": name
                }]
            )
            logger.info(f"Saved skill: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving skill: {e}")
            return False

    def delete_skill(self, name: str) -> bool:
        """
        Removes a skill from the library.
        
        Args:
            name: Skill identifier
            
        Returns:
            True if deleted, False otherwise
        """
        if not self.collection:
            return False
        
        try:
            self.collection.delete(ids=[name])
            logger.info(f"Deleted skill: {name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting skill: {e}")
            return False

    def list_all_skills(self) -> List[Dict[str, str]]:
        """
        Returns all skills in the library.
        
        Returns:
            List of dicts with 'name', 'code', 'description'
        """
        if not self.collection:
            return []
        
        try:
            results = self.collection.get()
            
            skills = []
            for i in range(len(results['ids'])):
                skills.append({
                    'name': results['ids'][i],
                    'code': results['metadatas'][i].get('code', ''),
                    'description': results['documents'][i]
                })
            
            return skills
            
        except Exception as e:
            logger.error(f"Error listing skills: {e}")
            return []

    def get_stats(self) -> Dict[str, int]:
        """
        Returns statistics about the skill library.
        
        Returns:
            Dict with 'total_skills' count
        """
        if not self.collection:
            return {"total_skills": 0}
        
        try:
            return {
                "total_skills": self.collection.count()
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"total_skills": 0}
