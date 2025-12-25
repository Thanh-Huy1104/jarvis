import asyncio
import json
from typing import Dict, AsyncGenerator
from app.core.events import PipelineEvent

class EventBus:
    def __init__(self):
        # job_id -> Queue
        self.channels: Dict[str, asyncio.Queue] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        if job_id not in self.channels:
            self.channels[job_id] = asyncio.Queue()
        return self.channels[job_id]

    async def publish(self, event: PipelineEvent):
        if event.job_id in self.channels:
            await self.channels[event.job_id].put(event)

    async def stream(self, job_id: str) -> AsyncGenerator[dict, None]:
        """
        Yields data in the strict format required by Server-Sent Events.
        Format: {"data": "<json_string>"}
        """
        queue = self.subscribe(job_id)
        try:
            while True:
                # Wait for the next event
                event: PipelineEvent = await queue.get()
                
                # SERIALIZATION FIX: Convert Pydantic -> JSON String
                yield {"data": event.model_dump_json()}
                
                queue.task_done()
                
                # Stop streaming logic
                if event.stage in ["COMPLETED", "FAILED"] and event.type in ["STEP_COMPLETE", "ERROR"]:
                     break
                     
        except asyncio.CancelledError:
            # Handle client disconnect
            pass
        finally:
            if job_id in self.channels:
                del self.channels[job_id]