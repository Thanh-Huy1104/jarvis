from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import time

class PipelineStage(str, Enum):
    PLANNING = "PLANNING"
    GENERATING = "GENERATING"
    LINTING = "LINTING"
    TESTING = "TESTING"
    REFINING = "REFINING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class EventType(str, Enum):
    STEP_START = "STEP_START"
    STEP_COMPLETE = "STEP_COMPLETE"
    LOG = "LOG"
    ERROR = "ERROR"

class PipelineEvent(BaseModel):
    job_id: str
    timestamp: float = Field(default_factory=time.time)
    stage: PipelineStage
    type: EventType
    content: str
    metadata: Optional[Dict[str, Any]] = None
