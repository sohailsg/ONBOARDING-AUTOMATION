"""Pydantic schemas for the RAG HTTP surface (mirrors backend/openapi Chat*)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    doc: str
    page: int
    effective_date: str = ""


class RetrieveRequest(BaseModel):
    query: str
    region: str
    dept: str = "all"
    k: int = 30


class RetrievedChunk(BaseModel):
    text: str
    doc: str
    page: int
    effective_date: str = ""
    score: float = 0.0
    chunk_id: str = ""


class RetrieveResponse(BaseModel):
    chunks: list[RetrievedChunk]


class AnswerRequest(BaseModel):
    query: str = ""
    question: str = ""  # gateway (02) sends `question`; same meaning as query
    region: str = ""
    dept: str = "all"
    chunks: list[RetrievedChunk] = Field(default_factory=list)


class ChatRequest(BaseModel):
    question: str
    region: str = ""
    dept: str = "all"


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = 0.0
    abstained: bool = False


class ReindexRequest(BaseModel):
    doc_id: str
    version: int = 1
    region: str = ""
    department: str = "all"
    effective_date: str = ""
    path: str = ""  # local file path staged by admin upload
