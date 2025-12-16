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

logger = logging.getLogger(__name__)


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
