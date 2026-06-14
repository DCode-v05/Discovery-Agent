"""Level 1 schemas — system inventory.

Two kinds of model live here:
  * LLM-facing (`ExtractedSystem`, `DocumentExtraction`) — the structured shape
    we ask the model to fill per document. Kept flat and simple so both Gemini
    `response_schema` and Groq JSON-schema modes produce it reliably.
  * Domain (`System`, `Inventory`) — the validated, grounded, merged result the
    API/CLI return.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Criticality(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class ConfidenceTier(str, Enum):
    explicit = "explicit"   # >= confidence_explicit, named directly
    inferred = "inferred"   # confidence_inferred..explicit, reasoned from context
    review = "review"       # < confidence_inferred, flagged for a human


# --------------------------------------------------------------------------- #
# LLM-facing extraction schema (one per document)                             #
# --------------------------------------------------------------------------- #
class ExtractedSystem(BaseModel):
    """A single system the model found in ONE document."""

    name: str = Field(description="Canonical product/system name, e.g. 'Salesforce', 'NetSuite'.")
    category: str = Field(description="System category, e.g. CRM, ERP, Procurement, Data Warehouse, HRIS, ITSM, Payments.")
    auth_method: str = Field(description="Authentication method if stated or strongly implied, else 'Unknown'. e.g. OAuth2, API Key, SAML SSO, Basic Auth.")
    key_entities: list[str] = Field(default_factory=list, description="Key data entities/objects this system owns, e.g. ['Account','Opportunity'].")
    business_processes: list[str] = Field(default_factory=list, description="Business processes it supports, e.g. ['Lead-to-cash','Invoicing'].")
    criticality: Criticality = Field(default=Criticality.unknown, description="Operational criticality if discernible, else 'unknown'.")
    confidence: float = Field(ge=0.0, le=1.0, description="0..1 — how strongly THIS document supports this system. 0.95+ only for explicit named mentions.")
    evidence_quote: str = Field(description="VERBATIM text copied from the document that supports this system. Must appear in the source exactly.")
    location: str = Field(description="Where in the document the evidence is, e.g. 'page 2', 'Sheet1!B4', 'line 12', 'image region: header'.")
    uncertainty_note: str = Field(default="", description="If anything was inferred rather than stated, say what was inferred and what evidence is missing. Empty string if fully explicit.")


class DocumentExtraction(BaseModel):
    """The model's full answer for one document."""

    systems: list[ExtractedSystem] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Domain schema (merged, grounded, returned to the caller)                    #
# --------------------------------------------------------------------------- #
class Evidence(BaseModel):
    quote: str
    source_doc: str
    location: str
    grounded: bool = Field(default=False, description="True once verified to appear in the source document.")


class System(BaseModel):
    name: str
    category: str
    auth_method: str
    key_entities: list[str] = Field(default_factory=list)
    business_processes: list[str] = Field(default_factory=list)
    criticality: Criticality = Criticality.unknown
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_tier: ConfidenceTier
    uncertainty_note: str | None = None
    needs_review: bool = False
    evidence: list[Evidence] = Field(default_factory=list)
    source_docs: list[str] = Field(default_factory=list)


class SkippedDocument(BaseModel):
    """A document that could not be processed — surfaced, never silently dropped."""

    document: str
    reason: str
    needs: str


class Inventory(BaseModel):
    run_id: str
    generated_at: str
    document_count: int
    systems_count: int
    systems: list[System] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    skipped_documents: list[SkippedDocument] = Field(default_factory=list)
