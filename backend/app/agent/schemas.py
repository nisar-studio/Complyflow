"""
ComplyFlow — Pydantic Schemas
Structured data contracts used across agent tools, API, and Firestore.
Gemini structured output is enforced against these schemas.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class Priority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceStatus(str, Enum):
    SATISFIED = "SATISFIED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    CONFLICT = "CONFLICT"


class OverallStatus(str, Enum):
    READY = "READY"
    ACTION_REQUIRED = "ACTION_REQUIRED"


class TaskStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class AgentEventType(str, Enum):
    AGENT_STARTED = "AGENT_STARTED"
    TOOL_STARTED = "TOOL_STARTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    GAP_DETECTED = "GAP_DETECTED"
    PLAN_CREATED = "PLAN_CREATED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    AGENT_ERROR = "AGENT_ERROR"


# ─────────────────────────────────────────────
# Requirements
# ─────────────────────────────────────────────

class Requirement(BaseModel):
    requirement_id: str = Field(..., description="e.g. REQ-001")
    title: str
    description: str
    required_evidence: str = Field(..., description="Description of what evidence satisfies this requirement")
    priority: Priority
    source_reference: str = Field(..., description="Page/section reference in the requirements document")


class RequirementsResult(BaseModel):
    requirements: List[Requirement]
    total_count: int
    extraction_notes: str = ""


# ─────────────────────────────────────────────
# Document Analysis
# ─────────────────────────────────────────────

class DocumentAnalysis(BaseModel):
    doc_name: str
    doc_type: str = Field(..., description="e.g. certificate, policy, financial_statement")
    key_facts: List[str]
    dates: List[str] = Field(default_factory=list)
    organizations: List[str] = Field(default_factory=list)
    identifiers: List[str] = Field(default_factory=list, description="IDs, policy numbers, reg numbers, etc.")
    evidence_statements: List[str] = Field(..., description="Specific facts that could satisfy requirements")
    possible_inconsistencies: List[str] = Field(default_factory=list)


class DocumentsAnalysisResult(BaseModel):
    analyses: List[DocumentAnalysis]


# ─────────────────────────────────────────────
# Evidence Matching & Grounded Citations
# ─────────────────────────────────────────────

class EvidenceCitation(BaseModel):
    """An exact verifiable excerpt from a source document proving compliance."""
    document_id: str = ""
    document_name: str
    chunk_id: Optional[str] = None
    page_number: Optional[int] = None
    section: Optional[str] = None
    quote: str = Field(..., description="Exact verified excerpt from the source document")
    relevance: str = Field(default="", description="Why this excerpt proves satisfaction of the requirement")
    verified: bool = Field(default=True, description="Whether this quote was grounded and verified in source text")


class ConflictingSource(BaseModel):
    """Source provenance and extracted conflicting value from a single document."""
    citation: EvidenceCitation
    value: str = Field(..., description="The specific extracted fact/value, e.g. 'Suite 800, Innovation Park'")


class ConflictDetail(BaseModel):
    """Fact-level, auditable conflict representation between two competing sources."""
    conflict_id: str = Field(default_factory=lambda: f"CONF-{uuid.uuid4().hex[:6]}")
    related_requirement_id: str
    fact: str = Field(..., description="Machine-readable fact identifier, e.g. 'company_address'")
    fact_label: str = Field(..., description="Human-readable fact name, e.g. 'Registered Company Address'")
    source_a: ConflictingSource
    source_b: ConflictingSource
    explanation: str = Field(..., description="Why these two extracted values are contradictory")
    severity: Priority = Priority.HIGH
    recommended_action: str = Field(..., description="Specific corrective action to resolve the conflict")


class EvidenceMatch(BaseModel):
    requirement_id: str
    requirement_title: str
    status: EvidenceStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[EvidenceCitation] = Field(default_factory=list, description="Grounded citations from source documents")
    evidence_references: List[str] = Field(default_factory=list, description="Document names that provide evidence")
    reasoning: str = Field(..., description="Concise user-facing explanation, no internal chain-of-thought")
    missing_reason: Optional[str] = Field(default=None, description="Detailed explanation of what was searched for and why missing")
    partial_details: Optional[str] = Field(default=None, description="Explanation of what is satisfied vs what remains missing")
    conflict_details: Optional[ConflictDetail] = Field(default=None, description="Fact-level conflicting source claims")


class MatchingResult(BaseModel):
    matches: List[EvidenceMatch]
    satisfied_count: int
    partial_count: int
    missing_count: int
    conflict_count: int
    compliance_score: float = Field(..., ge=0.0, le=100.0)


# ─────────────────────────────────────────────
# Gap Detection
# ─────────────────────────────────────────────

class Gap(BaseModel):
    gap_id: str
    gap_type: str = Field(..., description="missing_evidence | expired_evidence | conflict | incomplete | ambiguous")
    severity: Priority
    description: str
    related_requirement_id: str
    related_requirement_title: str
    affected_documents: List[str] = Field(default_factory=list)
    recommended_action: str
    conflict_detail: Optional[ConflictDetail] = Field(default=None, description="Associated fact-level conflict if gap_type is conflict")


class GapsResult(BaseModel):
    gaps: List[Gap]
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int


# ─────────────────────────────────────────────
# Remediation Plan
# ─────────────────────────────────────────────

class RemediationTask(BaseModel):
    task_id: str
    title: str
    description: str
    severity: Priority
    required_action: str
    related_requirement_id: str
    related_requirement_title: str
    status: TaskStatus = TaskStatus.OPEN


class RemediationPlanResult(BaseModel):
    tasks: List[RemediationTask]
    total_tasks: int
    estimated_effort: str = Field(..., description="e.g. 'Upload 2 documents and resolve 1 address conflict'")


# ─────────────────────────────────────────────
# Verification & Versioned Snapshots
# ─────────────────────────────────────────────

class VerificationRunTrigger(str, Enum):
    INITIAL_ANALYSIS = "INITIAL_ANALYSIS"
    REMEDIATION_VERIFICATION = "REMEDIATION_VERIFICATION"
    MANUAL_RECHECK = "MANUAL_RECHECK"


class VerificationRunSnapshot(BaseModel):
    """An immutable point-in-time snapshot of a compliance verification run."""
    run_id: str
    project_id: str
    run_number: int = 1
    timestamp: str
    trigger: str = "INITIAL_ANALYSIS"
    overall_status: OverallStatus
    compliance_score: float = Field(..., ge=0.0, le=100.0)
    satisfied_count: int = 0
    total_count: int = 0
    requirements_snapshot: List[Dict[str, Any]] = Field(default_factory=list)
    matches_snapshot: List[Dict[str, Any]] = Field(default_factory=list)
    issues_snapshot: List[Dict[str, Any]] = Field(default_factory=list)
    tasks_snapshot: List[Dict[str, Any]] = Field(default_factory=list)
    documents_used: List[str] = Field(default_factory=list)
    resolved_gaps: List[str] = Field(default_factory=list)
    remaining_gaps: List[str] = Field(default_factory=list)
    summary: str


class RequirementDelta(BaseModel):
    """Status transition for a single requirement between two runs."""
    requirement_id: str
    title: str = ""
    status_before: str
    status_after: str
    confidence_before: Optional[float] = None
    confidence_after: Optional[float] = None
    change_type: str = "UNCHANGED"  # "RESOLVED" | "NEWLY_FAILED" | "UNCHANGED" | "IMPROVED"
    reasoning_before: Optional[str] = None
    reasoning_after: Optional[str] = None


class VerificationDeltaResult(BaseModel):
    """Deterministic comparative delta between two verification run snapshots."""
    from_run_id: str
    to_run_id: str
    from_run_number: int
    to_run_number: int
    score_before: float
    score_after: float
    score_diff: float
    status_before: str
    status_after: str
    resolved_count: int
    newly_failed_count: int
    unchanged_count: int
    resolved_requirements: List[RequirementDelta] = Field(default_factory=list)
    newly_failed_requirements: List[RequirementDelta] = Field(default_factory=list)
    unchanged_requirements: List[RequirementDelta] = Field(default_factory=list)
    resolved_issues: List[Dict[str, Any]] = Field(default_factory=list)
    new_issues: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str


class VerificationResult(BaseModel):
    overall_status: OverallStatus
    compliance_score: float = Field(..., ge=0.0, le=100.0)
    satisfied_count: int
    total_count: int
    resolved_gaps: List[str] = Field(default_factory=list, description="Gap IDs that were resolved")
    remaining_gaps: List[str] = Field(default_factory=list, description="Gap IDs still open")
    new_issues: List[str] = Field(default_factory=list, description="Any new issues found")
    summary: str
    matches: List[EvidenceMatch] = Field(default_factory=list)
    run_id: Optional[str] = None
    run_number: Optional[int] = None


# ─────────────────────────────────────────────
# Agent Event
# ─────────────────────────────────────────────

class AgentEvent(BaseModel):
    event_id: str
    project_id: str
    type: AgentEventType
    tool: Optional[str] = None
    status: str  # "started" | "completed" | "error"
    timestamp: str
    summary: str
    data: Optional[dict] = None


# ─────────────────────────────────────────────
# Project
# ─────────────────────────────────────────────

class ProjectStatus(str, Enum):
    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    READY = "READY"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    ERROR = "ERROR"


class Project(BaseModel):
    project_id: str
    user_id: str = "demo-user"
    name: str
    status: ProjectStatus = ProjectStatus.PENDING
    compliance_score: Optional[float] = None
    overall_status: Optional[OverallStatus] = None
    requirements_count: int = 0
    documents_count: int = 0
    issues_count: int = 0
    created_at: str
    updated_at: str
