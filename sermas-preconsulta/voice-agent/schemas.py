from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ConversationState(str, Enum):
    GREETING = "greeting"
    IDENTIFY_PATIENT = "identify_patient"
    COLLECT_CHIEF_COMPLAINT = "collect_chief_complaint"
    COLLECT_SYMPTOMS = "collect_symptoms"
    CONFIRM = "confirm"
    DONE = "done"


class Turn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class SymptomSummary(BaseModel):
    cip: Optional[str] = None
    chief_complaint: Optional[str] = None
    symptoms: list[str] = Field(default_factory=list)
    duration: Optional[str] = None
    severity: Optional[str] = None  # mild | moderate | severe
    associated_symptoms: list[str] = Field(default_factory=list)
    relevant_history_flags: list[str] = Field(default_factory=list)
    raw_transcript: list[Turn] = Field(default_factory=list)


class AgentResponse(BaseModel):
    response: str
    done: bool
    symptoms: Optional[SymptomSummary] = None
    next_state: ConversationState


class FHIRPostPayload(BaseModel):
    session_id: str
    cip: Optional[str]
    symptoms: SymptomSummary
