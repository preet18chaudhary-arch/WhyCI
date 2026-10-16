"""Pydantic request and response models for the WhyCI API."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class LogLineModel(BaseModel):
    line_number: int
    text: str


class FailureClusterModel(BaseModel):
    start_line: int
    end_line: int
    lines: list[LogLineModel]


class RootCauseModel(BaseModel):
    line_number: int
    text: str
    category: str
    priority_score: float
    score_reasons: list[str]
    explanation: str


class RedactionStats(BaseModel):
    applied: bool
    replacement_count: int
    matched_rules: list[str]


class AnalysisResponse(BaseModel):
    status: str = "ok"
    source_name: str
    total_lines: int
    error_count: int
    warning_count: int
    failure_clusters: list[FailureClusterModel]
    root_cause: Optional[RootCauseModel]
    primary_evidence: list[LogLineModel]
    supporting_evidence: list[LogLineModel]
    cascading_failures: list[LogLineModel]
    relevant_context: list[LogLineModel]
    debugging_suggestions: list[str]
    redaction: Optional[RedactionStats]
    analysis_notes: list[str] = Field(default_factory=list)
    repeat_detected: bool = False
    repeat_count: int = 0
    history_id: Optional[int] = None

class SampleInfo(BaseModel):
    id: str
    name: str
    description: str
    filename: str


class HealthResponse(BaseModel):
    status: str
    version: str
    engine: str
