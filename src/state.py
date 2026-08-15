"""
Veritas-Graph: Central System State & Telemetry Schemas
Enforces strict immutability and provenance tracking.
"""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    RETRYING = "RETRYING"
    ESCALATED_HUMAN_REVIEW = "ESCALATED_HUMAN_REVIEW"
    FAILED = "FAILED"


class BoundingBox(BaseModel):
    """Physical coordinate provenance from Phase 1."""
    model_config = ConfigDict(frozen=True)
    
    page_number: int
    x0: float
    top: float
    x1: float
    bottom: float


class ExtractedClause(BaseModel):
    """Semantic clause with physical grounding and retry state."""
    model_config = ConfigDict(frozen=True)
    
    clause_id: str
    text: str
    context_before: str = ""  # FIX: Plumb context for the aligner
    redline_suggestion: Optional[str] = None
    section_header: Optional[str] = None
    bounding_boxes: List[BoundingBox] = Field(default_factory=list)
    confidence_score: float = 1.0
    retry_count: int = 0
    status: ExecutionStatus = ExecutionStatus.PENDING
    requires_human_review: bool = False
    escalation_reason: Optional[str] = None
    


class RedlineAction(BaseModel):
    """Native Word AST redline instruction."""
    model_config = ConfigDict(frozen=True)
    
    clause_id: str
    target_paragraph_index: Optional[int] = None
    original_text: str
    replacement_text: str
    author: str = "Veritas-AI"
    timestamp: str = ""
    is_fallback_comment: bool = False
    warning_comment: Optional[str] = None


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class SystemState(BaseModel):
    """
    Immutable State Graph payload.
    All transitions must execute via state.model_copy(update={...}).
    """
    model_config = ConfigDict(frozen=True)
    
    document_id: str
    raw_pdf_path: Optional[str] = None
    raw_docx_path: Optional[str] = None
    is_pdf_only: bool = False
    
    # Processing state
    chunks: List[str] = Field(default_factory=list)
    unstructured_document_flag: bool = False
    extracted_clauses: List[ExtractedClause] = Field(default_factory=list)
    redlines: List[RedlineAction] = Field(default_factory=list)
    
    # Telemetry & Observability
    node_latency_ms: Dict[str, float] = Field(default_factory=dict)
    token_telemetry: TokenUsage = Field(default_factory=TokenUsage)
    failed_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    requires_global_human_review: bool = False