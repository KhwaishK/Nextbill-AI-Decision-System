"""
Data models for the AI Decision System.

Using Pydantic here for two reasons:
1. It forces every stage of the pipeline (extraction -> classification -> decision)
   to produce structured, typed output instead of loose dicts/strings. This matters
   a lot if a stage is later swapped for an LLM call -- the LLM's output gets
   validated against a schema instead of being trusted blindly.
2. It gives us free serialization to JSON for logging / API responses.
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class IssueCategory(str, Enum):
    PAYMENT_NOT_REFLECTED = "payment_not_reflected"
    PARTIAL_PAYMENT_MISMATCH = "partial_payment_mismatch"
    DUPLICATE_CHARGE = "duplicate_charge"
    BILLING_NAME_MISMATCH = "billing_name_mismatch"
    UNMATCHED_PAYMENT = "unmatched_payment"
    UNCERTAIN = "uncertain"  # classifier could not confidently assign a category


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExtractedEntities(BaseModel):
    """Everything the system could pull out of the raw message text."""
    amounts: List[float] = Field(default_factory=list, description="All currency amounts found, in INR")
    invoice_numbers: List[str] = Field(default_factory=list)
    order_numbers: List[str] = Field(default_factory=list)
    transaction_refs: List[str] = Field(default_factory=list, description="UTR / txn id / reference numbers")
    time_references: List[str] = Field(default_factory=list, description="e.g. 'yesterday', 'today'")
    mentions_duplicate_charge: bool = False
    mentions_third_party_payer: bool = False  # e.g. "my company", "director"
    raw_numbers_found: int = 0  # sanity-check counter, see extractor.py


class ClassificationResult(BaseModel):
    category: IssueCategory
    confidence: float = Field(ge=0.0, le=1.0)
    matched_keywords: List[str] = Field(default_factory=list)
    scores: dict = Field(default_factory=dict, description="Raw score per candidate category, for debuggability")


class Decision(BaseModel):
    """
    Final structured output for a message. This is the contract the rest of the
    business (support dashboard, ticketing system, etc.) would consume.
    """
    message: str
    entities: ExtractedEntities
    classification: ClassificationResult
    risk_level: RiskLevel
    automatable: bool = Field(
        description="Could this be resolved end-to-end by an automated backend check "
                    "(payment gateway lookup, ledger reconciliation) with NO human, "
                    "assuming all required information is present?"
    )
    requires_human_review: bool = Field(
        description="Should a human agent look at this regardless of automation, "
                    "due to financial/legal/fraud/reputational risk or low confidence?"
    )
    missing_information: List[str] = Field(default_factory=list)
    recommended_next_action: str
    reasoning: str
