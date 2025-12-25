import logging
import asyncio
from app.core.events import PipelineEvent, PipelineStage, EventType
from app.core.bus import EventBus
from app.core.skills_engine import SkillsEngine
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

class JobRunner:
    def __init__(self, skills_engine: SkillsEngine, event_bus: EventBus):
        self.engine = skills_engine
        self.bus = event_bus

    async def run_verification_job(self, job_id: str, code: str, instruction: str, skill_id: str):
        """
        Executes the skill verification loop for an existing pending skill.
        If successful, saves the skill to the library and removes from pending.
        """
        try:
            skill_name = "Unknown"
            # Get skill name for logging/saving (optional, can be fetched from pending if needed, 
            # but we'll assume the instruction/code is enough context or fetch it inside)
            
            # Fetch skill details to get the name for saving
            pending_skill = self.engine.skills.pending.get_pending_skill(skill_id)
            if pending_skill:
                skill_name = pending_skill.get("name", "Unknown")
            
            await self.bus.publish(PipelineEvent(
                job_id=job_id,
                stage=PipelineStage.PLANNING,
                type=EventType.STEP_START,
                content=f"Starting verification job for skill: {skill_name}"
            ))
            
            final_code = code
            execution_error = None
            lint_error = None
            
            # 1. RUNNING THE PIPELINE (Lint/Test/Refine Loop)
            async for event in self.engine.run_verification_stream(
                code=code,
                user_input=instruction,
                thread_id=job_id
            ):
                event_type = event.get("event")
                data = event.get("data", {})
                name = event.get("name", "")
                
                # Capture the latest code from the state if available
                if event_type == "on_chain_end" and name == "think_agent":
                    # think_agent outputs the refined code
                    if "generated_code" in data.get("output", {}):
                         final_code = data["output"]["generated_code"]

                # Map LangGraph events to PipelineEvents
                if event_type == "on_chain_start":
                    if name == "linter":
                        await self.bus.publish(PipelineEvent(
                            job_id=job_id,
                            stage=PipelineStage.LINTING,
                            type=EventType.STEP_START,
                            content="Linting generated code..."
                        ))
                    elif name == "executor":
                        await self.bus.publish(PipelineEvent(
                            job_id=job_id,
                            stage=PipelineStage.TESTING,
                            type=EventType.STEP_START,
                            content="Running in sandbox..."
                        ))
                    elif name == "think_agent":
                        await self.bus.publish(PipelineEvent(
                            job_id=job_id,
                            stage=PipelineStage.REFINING,
                            type=EventType.STEP_START,
                            content="Analyzing errors and fixing code..."
                        ))
                        
                elif event_type == "on_chain_end":
                    if name == "linter":
                        lint_error = data.get("output", {}).get("lint_error")
                        if lint_error:
                             await self.bus.publish(PipelineEvent(
                                job_id=job_id,
                                stage=PipelineStage.LINTING,
                                type=EventType.ERROR,
                                content=f"Linting Failed:\n{lint_error[:500]}..."
                            ))
                        else:
                             await self.bus.publish(PipelineEvent(
                                job_id=job_id,
                                stage=PipelineStage.LINTING,
                                type=EventType.STEP_COMPLETE,
                                content="Linting passed."
                            ))
                            
                    elif name == "executor":
                        # data['output'] should contain the execution result
                        output = data.get("output", {}).get("execution_result", "")
                        execution_error = data.get("output", {}).get("execution_error", "")
                        
                        if execution_error:
                            await self.bus.publish(PipelineEvent(
                                job_id=job_id,
                                stage=PipelineStage.TESTING,
                                type=EventType.ERROR,
                                content=f"Tests Failed:\n{execution_error[:500]}..."
                            ))
                        else:
                             await self.bus.publish(PipelineEvent(
                                job_id=job_id,
                                stage=PipelineStage.TESTING,
                                type=EventType.STEP_COMPLETE,
                                content=f"Execution Successful:\n{output[:200]}..."
                            ))
                            
                elif event_type == "on_tool_start":
                     await self.bus.publish(PipelineEvent(
                        job_id=job_id,
                        stage=PipelineStage.TESTING,
                        type=EventType.LOG,
                        content=f"Executing tool: {name}"
                    ))

            # 2. FINALIZATION
            if execution_error or lint_error:
                # Failed after retries
                 error_details = execution_error if execution_error else lint_error
                 await self.bus.publish(PipelineEvent(
                    job_id=job_id,
                    stage=PipelineStage.FAILED,
                    type=EventType.ERROR,
                    content=f"Verification failed. Skill returned to pending with notes."
                ))
                 # Update pending with error
                 self.engine.skills.pending.update_pending_skill(
                     skill_id, 
                     code=final_code, 
                     notes=f"Verification Failed: {error_details[:500]}..."
                 )
            else:
                # Success
                await self.bus.publish(PipelineEvent(
                    job_id=job_id,
                    stage=PipelineStage.COMPLETED,
                    type=EventType.STEP_START,
                    content="Verification passed. Saving to library..."
                ))
                
                success = self.engine.skills.save_skill(
                    name=skill_name,
                    code=final_code,
                    description=instruction
                )
                
                if success:
                    self.engine.skills.pending.delete_pending_skill(skill_id)
                    await self.bus.publish(PipelineEvent(
                        job_id=job_id,
                        stage=PipelineStage.COMPLETED,
                        type=EventType.STEP_COMPLETE,
                        content=f"Skill '{skill_name}' saved to library successfully."
                    ))
                else:
                    await self.bus.publish(PipelineEvent(
                        job_id=job_id,
                        stage=PipelineStage.FAILED,
                        type=EventType.ERROR,
                        content="Failed to save skill to file system."
                    ))

        except Exception as e:
            logger.error(f"Verification Job failed: {e}")
            await self.bus.publish(PipelineEvent(
                job_id=job_id,
                stage=PipelineStage.FAILED,
                type=EventType.ERROR,
                content=str(e)
            ))