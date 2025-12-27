import logging
import uuid
import glob
import os
import ast
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from sse_starlette.sse import EventSourceResponse
from app.core.utils.executor import execute_with_packages

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
async def approve_skill(skill_id: str, request: Request, background_tasks: BackgroundTasks):
    """
    Approve a pending skill.
    Triggers an autonomous refinement loop (Code -> Fix) as a background job.
    Returns a job_id to track progress via SSE.
    """
    # Access the dedicated SkillsEngine
    skills_engine = request.app.state.skills_engine
    pending = skills_engine.skills.pending
    
    skill = pending.get_pending_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
        
    if not hasattr(request.app.state, "job_runner"):
        raise HTTPException(status_code=500, detail="JobRunner not initialized")
    
    job_runner = request.app.state.job_runner
    job_id = str(uuid.uuid4())
    
    logger.info(f"Initiating approval/refinement job {job_id} for skill: {skill['name']}")
    
    # Start the verification job in the background
    background_tasks.add_task(
        job_runner.run_verification_job,
        job_id=job_id,
        code=skill['code'],
        instruction=skill['description'],
        skill_id=skill_id
    )
    
    return {"status": "started", "job_id": job_id, "skill_name": skill['name']}

@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request):
    """
    Stream events for a specific job using SSE.
    """
    if not hasattr(request.app.state, "event_bus"):
        raise HTTPException(status_code=500, detail="EventBus not initialized")
        
    event_bus = request.app.state.event_bus
    
    # sse_starlette handles the async generator
    return EventSourceResponse(
        event_bus.stream(job_id)
    )

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
    """Test run arbitrary code locally."""
    # execute_with_packages handles import detection and installation
    output = execute_with_packages(body.code)
    return {"output": output}

@router.post("/skills/pending/{skill_id}/test")
async def test_skill(skill_id: str, request: Request):
    """Test run a pending skill locally."""
    pending = request.app.state.engine.skills.pending
    
    skill = pending.get_pending_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    # Execute the code locally
    output = execute_with_packages(skill['code'])
    
    return {"status": "tested", "output": output}


@router.get("/skills/library")
async def list_library_skills(request: Request):
    """
    List all active skills in the library.
    Reads directly from the .jarvis/skills/library directory.
    """
    skills_dir = ".jarvis/skills/library"
    skills = []
    
    if not os.path.exists(skills_dir):
        return []
        
    for py_file in glob.glob(f"{skills_dir}/*.py"):
        if "__init__" in py_file:
            continue
            
        try:
            with open(py_file, 'r') as f:
                content = f.read()
                
            # Basic parsing to get docstring (description)
            tree = ast.parse(content)
            description = ast.get_docstring(tree) or "No description."
            name = os.path.splitext(os.path.basename(py_file))[0]
            
            skills.append({
                "name": name,
                "description": description.strip(),
                "code": content, # Frontend might want to see the code
                "file_path": py_file
            })
        except Exception as e:
            logger.error(f"Error reading skill {py_file}: {e}")
            
    return skills

@router.delete("/skills/library/{skill_name}")
async def delete_library_skill(skill_name: str, request: Request):
    """Delete an active skill from the library."""
    file_path = f".jarvis/skills/library/{skill_name}.py"
    
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            # Re-sync registry if possible, or wait for next restart
            # request.app.state.engine.skills.sync_library() 
            return {"status": "deleted", "name": skill_name}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")
    else:
        raise HTTPException(status_code=404, detail="Skill not found")


@router.get("/skills/library")
async def list_library_skills(request: Request):
    """
    List all active skills in the library.
    Reads directly from the .jarvis/skills/library directory.
    """
    skills_dir = ".jarvis/skills/library"
    skills = []
    
    if not os.path.exists(skills_dir):
        return []
        
    for py_file in glob.glob(f"{skills_dir}/*.py"):
        if "__init__" in py_file:
            continue
            
        try:
            with open(py_file, 'r') as f:
                content = f.read()
                
            # Basic parsing to get docstring (description)
            tree = ast.parse(content)
            description = ast.get_docstring(tree) or "No description."
            name = os.path.splitext(os.path.basename(py_file))[0]
            
            skills.append({
                "name": name,
                "description": description.strip(),
                "code": content, # Frontend might want to see the code
                "file_path": py_file
            })
        except Exception as e:
            logger.error(f"Error reading skill {py_file}: {e}")
            
    return skills

@router.delete("/skills/library/{skill_name}")
async def delete_library_skill(skill_name: str, request: Request):
    """Delete an active skill from the library."""
    file_path = f".jarvis/skills/library/{skill_name}.py"
    
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            # Re-sync registry if possible, or wait for next restart
            # request.app.state.engine.skills.sync_library() 
            return {"status": "deleted", "name": skill_name}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")
    else:
        raise HTTPException(status_code=404, detail="Skill not found")
