import pytest
import json
import os
from app.core.skills import PendingSkillManager
from pathlib import Path

class TestPendingSkillManager:
    
    @pytest.fixture
    def pending_manager(self, tmp_path):
        # Use a temporary directory for testing
        return PendingSkillManager(pending_dir=str(tmp_path / "pending_skills"))

    def test_add_pending_skill(self, pending_manager):
        skill_id = pending_manager.add_pending_skill(
            code="print('hello')",
            description="Say hello",
            name="hello-skill"
        )
        
        assert skill_id is not None
        
        # Verify file exists
        skill = pending_manager.get_pending_skill(skill_id)
        assert skill['name'] == "hello-skill"
        assert skill['code'] == "print('hello')"
        assert skill['status'] == "pending"

    def test_list_pending_skills(self, pending_manager):
        pending_manager.add_pending_skill("code1", "desc1", "skill1")
        pending_manager.add_pending_skill("code2", "desc2", "skill2")
        
        skills = pending_manager.list_pending_skills()
        assert len(skills) == 2
        # Check sorting (newest first) - implicitly tested if execution is fast, 
        # but let's just check presence
        names = [s['name'] for s in skills]
        assert "skill1" in names
        assert "skill2" in names

    def test_update_pending_skill(self, pending_manager):
        skill_id = pending_manager.add_pending_skill("old_code", "desc", "old_name")
        
        success = pending_manager.update_pending_skill(
            skill_id, 
            code="new_code", 
            notes="updated"
        )
        
        assert success is True
        skill = pending_manager.get_pending_skill(skill_id)
        assert skill['code'] == "new_code"
        assert skill['notes'] == "updated"
        assert skill['name'] == "old_name" # Should remain unchanged

    def test_delete_pending_skill(self, pending_manager):
        skill_id = pending_manager.add_pending_skill("code", "desc", "skill")
        
        success = pending_manager.delete_pending_skill(skill_id)
        assert success is True
        
        skill = pending_manager.get_pending_skill(skill_id)
        assert skill is None
