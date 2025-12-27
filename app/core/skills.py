"""
Skill Management
----------------
Manages pending skills awaiting approval.
"""

import logging
from typing import Optional, List, Dict
from pathlib import Path
import os
import json
import uuid
import time

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
