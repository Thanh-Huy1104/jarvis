import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

logger = logging.getLogger("uvicorn")

router = APIRouter()

# --- Data Models ---
class RefineSkillRequest(BaseModel):
    instruction: str

class UpdateSkillRequest(BaseModel):
    code: str = None
    name: str = None
    description: str = None
    notes: str = None

class TestCodeRequest(BaseModel):
    code: str

# --- HTTP Endpoints for Skill Management ---

@router.get("/skills/pending")
async def list_pending_skills(request: Request):
    """List all pending skills."""
    # We can access skills via the main engine or skills engine. 
    # Using main engine is fine as it owns the components.
    return request.app.state.engine.skills.pending.list_pending_skills()

@router.get("/skills/pending/{skill_id}")
async def get_pending_skill(skill_id: str, request: Request):
    """Get details of a specific pending skill."""
    skill = request.app.state.engine.skills.pending.get_pending_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill

@router.post("/skills/pending/{skill_id}/approve")
async def approve_skill(skill_id: str, request: Request):
    """
    Approve a pending skill.
    Triggers an autonomous refinement loop (Code -> Sandbox -> Fix) to ensure quality.
    If successful, moves the refined skill to the final library.
    """
    # Access the dedicated SkillsEngine
    skills_engine = request.app.state.skills_engine
    pending = skills_engine.skills.pending
    library = skills_engine.skills
    
    skill = pending.get_pending_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    logger.info(f"Initiating approval/refinement loop for skill: {skill['name']}")
    
    # Run the autonomous verification/refinement loop
    try:
        final_state = await skills_engine.run_verification(
            code=skill['code'],
            user_input=skill['description'],
            thread_id=f"approve_{skill_id}"
        )
    except Exception as e:
        logger.error(f"Verification loop failed: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")
    
    # Extract results
    final_values = final_state
    if hasattr(final_state, "values"):
        final_values = final_state.values
        
    generated_code = final_values.get("generated_code")
    execution_result = final_values.get("execution_result")
    execution_error = final_values.get("execution_error")
    
    if execution_error:
        # Loop failed after retries
        logger.warning(f"Skill approval failed. Verification error: {execution_error}")
        
        # Update pending skill with the failed attempt details
        pending.update_pending_skill(
            skill_id, 
            code=generated_code, 
            notes=f"Verification Failed: {execution_error[:200]}..."
        )
        
        return {
            "status": "failed", 
            "error": execution_error,
            "code": generated_code,
            "output": execution_result
        }
    
    # Success! Save to Final Library
    logger.info(f"Skill verified successfully. Saving '{skill['name']}' to library.")
    
    success = library.save_skill(
        name=skill['name'],
        code=generated_code, # Use the refined code
        description=skill['description']
    )
    
    if success:
        # Remove from pending
        pending.delete_pending_skill(skill_id)
        return {
            "status": "approved", 
            "skill_name": skill['name'],
            "code": generated_code,
            "output": execution_result
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save skill to library")

@router.delete("/skills/pending/{skill_id}")
async def reject_skill(skill_id: str, request: Request):
    """Reject and delete a pending skill."""
    pending = request.app.state.engine.skills.pending
    if pending.delete_pending_skill(skill_id):
        return {"status": "rejected"}
    else:
        raise HTTPException(status_code=404, detail="Skill not found")

@router.post("/skills/pending/{skill_id}/refine")
async def refine_skill(skill_id: str, body: RefineSkillRequest, request: Request):
    """Refine a pending skill using AI based on instructions."""
    engine = request.app.state.engine
    pending = engine.skills.pending
    
    skill = pending.get_pending_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    # Use LLM to refine code
    prompt = f"""You are a Python expert. Refine the following code based on the user's instruction.
    
    CURRENT CODE:
    ```python
    {skill['code']}
    ```
    
    INSTRUCTION: {body.instruction}
    
    Return ONLY the refined Python code. No markdown formatting, just the code.
    """
    
    try:
        response = await engine.llm.run_agent_step(
            messages=[HumanMessage(content=prompt)],
            system_persona="You are a code refactoring expert. Output only clean Python code.",
            tools=None,
            mode="speed"
        )
        
        refined_code = engine.llm.sanitize_thought_process(str(response.content)).strip()
        
        # Remove markdown code blocks if present
        if refined_code.startswith("```python"):
            refined_code = refined_code.replace("```python", "", 1)
        if refined_code.startswith("```"):
            refined_code = refined_code.replace("```", "", 1)
        if refined_code.endswith("```"):
            refined_code = refined_code[:-3]
            
        refined_code = refined_code.strip()
        
        # Update the pending skill
        pending.update_pending_skill(skill_id, code=refined_code, notes=f"Refined: {body.instruction}")
        
        return {"status": "refined", "code": refined_code}
        
    except Exception as e:
        logger.error(f"Refinement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/skills/pending/{skill_id}")
async def manual_update_skill(skill_id: str, body: UpdateSkillRequest, request: Request):
    """Manually update a pending skill's attributes."""
    pending = request.app.state.engine.skills.pending
    
    success = pending.update_pending_skill(
        skill_id,
        code=body.code,
        name=body.name,
        description=body.description,
        notes=body.notes
    )
    
    if success:
        return {"status": "updated"}
    else:
        raise HTTPException(status_code=404, detail="Skill not found")

@router.post("/sandbox/test")
async def test_code(body: TestCodeRequest, request: Request):
    """Test run arbitrary code in the sandbox."""
    engine = request.app.state.engine
    # execute_with_packages handles import detection and installation
    output = engine.sandbox.execute_with_packages(body.code)
    return {"output": output}

@router.post("/skills/pending/{skill_id}/test")
async def test_skill(skill_id: str, request: Request):
    """Test run a pending skill in the sandbox."""
    engine = request.app.state.engine
    pending = engine.skills.pending
    
    skill = pending.get_pending_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    # Execute the code in the sandbox
    output = engine.sandbox.execute_with_packages(skill['code'])
    
    return {"status": "tested", "output": output}
