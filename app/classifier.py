"""
Issue classification.

Design choice: keyword/rule-based scoring as the DEFAULT, with a documented
seam for swapping in an LLM classifier (see `classify_with_llm` stub at the
bottom, unused by default).

Why rules first, not an LLM, for a task this small:
- The category set is small and known in advance (5 categories + uncertain).
  A few keyword lists get ~80% of the way there for a v1 with zero API cost,
  zero latency, and fully explainable decisions ("matched: 'charged twice',
  'both transactions'") -- important when you need to justify a "no human
  review needed" decision to a regulator or auditor later.
- Rules fail *loudly*: if nothing matches, confidence is 0 and the category
  becomes UNCERTAIN, which the decision engine always routes to a human.
  An LLM, by contrast, tends to fail *quietly* -- it will confidently pick a
  category even for a message that doesn't clearly belong anywhere, because
  next-token prediction doesn't have a built-in "I don't know" floor.

Where an LLM genuinely earns its cost is on paraphrase robustness: "the
system deducted money but I can't tell what for" should hit the same
UNMATCHED_PAYMENT bucket as our test message, but a keyword list will miss
it. The recommended extension path (see README) is:
  1. Run the rule-based classifier first (cheap, deterministic).
  2. If confidence < threshold, escalate to an LLM call constrained to
     return one of the fixed enum values (function calling / structured
     output), never free text.
  3. Validate the LLM's category against the same Pydantic enum used here --
     if it returns something outside the enum, treat as UNCERTAIN rather
     than crashing or silently accepting garbage.
  4. Always keep BOTH the rule-based and LLM verdicts in the log so
     disagreements can be reviewed and used to improve the keyword lists
     over time.
"""

from typing import Dict, List, Tuple
from app.models import ClassificationResult, IssueCategory, ExtractedEntities

# Each category maps to a list of phrases. Order doesn't matter; scoring is a
# simple count of matches, which is transparent and easy for a human reviewer
# to sanity-check ("why did it pick duplicate_charge? -> because it matched
# 'charged twice' and 'both transactions'").
KEYWORD_MAP: Dict[IssueCategory, List[str]] = {
    IssueCategory.PAYMENT_NOT_REFLECTED: [
        "still shows unpaid", "shows as unpaid", "still unpaid", "not reflecting",
        "not updated", "hasn't updated", "already paid", "i paid", "we paid",
    ],
    IssueCategory.PARTIAL_PAYMENT_MISMATCH: [
        "already paid", "partial payment", "partially paid", "full amount", "showing as due",
        "showing due", "why is the full amount", "already been paid",
    ],
    IssueCategory.DUPLICATE_CHARGE: [
        "charged twice", "double charged", "duplicate", "two transactions",
        "both transactions", "charged again", "same order twice",
    ],
    IssueCategory.BILLING_NAME_MISMATCH: [
        "director's name", "director name", "company name", "invoice is under",
        "wrong name on invoice", "billed to the wrong", "name on the invoice",
    ],
    IssueCategory.UNMATCHED_PAYMENT: [
        "don't know which invoice", "not sure which invoice", "which invoice this",
        "deducted from my bank", "deducted from my account", "don't know what this payment",
        "unknown payment", "can't identify",
    ],
}

CONFIDENCE_THRESHOLD = 0.15  # below this, category is forced to UNCERTAIN


def classify(message: str, entities: ExtractedEntities) -> ClassificationResult:
    text = message.lower()
    scores: Dict[str, int] = {}
    matched: Dict[str, List[str]] = {}

    for category, phrases in KEYWORD_MAP.items():
        hits = [p for p in phrases if p in text]
        scores[category.value] = len(hits)
        matched[category.value] = hits

    # A couple of structural (non-keyword) signals nudge scores using
    # extracted entities rather than text matching -- these are cases where
    # *structure* of the message is more reliable than wording.
    if entities.mentions_duplicate_charge:
        scores[IssueCategory.DUPLICATE_CHARGE.value] += 2
    if entities.mentions_third_party_payer:
        scores[IssueCategory.BILLING_NAME_MISMATCH.value] += 1
    if len(entities.amounts) >= 2:
        # two distinct amounts in one message is a strong signal of an
        # invoice-vs-payment reconciliation question
        scores[IssueCategory.PARTIAL_PAYMENT_MISMATCH.value] += 1
    if len(entities.invoice_numbers) == 0 and len(entities.transaction_refs) == 0 and \
       "which invoice" in text or "don't know" in text:
        scores[IssueCategory.UNMATCHED_PAYMENT.value] += 1

    best_category, best_score = max(scores.items(), key=lambda kv: kv[1])
    total = sum(scores.values()) or 1
    confidence = best_score / total if best_score > 0 else 0.0

    if best_score == 0 or confidence < CONFIDENCE_THRESHOLD:
        return ClassificationResult(
            category=IssueCategory.UNCERTAIN,
            confidence=confidence,
            matched_keywords=[],
            scores=scores,
        )

    return ClassificationResult(
        category=IssueCategory(best_category),
        confidence=round(confidence, 2),
        matched_keywords=matched[best_category],
        scores=scores,
    )


# --- Extension seam (not used by default) -----------------------------------
def classify_with_llm(message: str) -> Tuple[IssueCategory, float]:
    """
    Placeholder showing where an LLM-based classifier would plug in, e.g.
    using the OpenAI/Azure OpenAI structured-output / function-calling API
    to force the response into the IssueCategory enum. Left unimplemented
    here to avoid an unnecessary external dependency/API key requirement
    for a task of this size; see README for the recommended integration.
    """
    raise NotImplementedError("LLM classification not wired up in this reference implementation.")
