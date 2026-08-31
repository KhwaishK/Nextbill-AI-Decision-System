"""
Thin orchestrator wiring extractor -> classifier -> decision engine together.

Kept deliberately as a plain function rather than a class/graph framework
(e.g. LangGraph) because the pipeline is a strict 3-step linear chain with no
branching or retries in this version. Introducing a graph framework here
would add indirection without adding capability. If a later version needs
retries, conditional branches (e.g. "if classifier confidence low, call
LLM"), or parallel entity-extraction calls, that's when a framework like
LangGraph starts paying for itself -- see README "What I'd improve".
"""

from app.models import Decision
from app.extractor import extract_entities
from app.classifier import classify
from app.decision_engine import decide


def process_message(message: str) -> Decision:
    entities = extract_entities(message)
    classification = classify(message, entities)
    decision = decide(message, entities, classification)
    return decision
