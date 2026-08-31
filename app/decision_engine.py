"""
Decision engine: turns (entities, classification) into an actionable decision.

This is where the actual business judgement lives, and it's deliberately kept
as plain, readable if/else rules rather than another model. A few principles
drove the design:

1. Automation is about VERIFIABILITY, not just intent.
   "I paid ₹4,500 yesterday" is a *claim*, not a fact. The system should never
   auto-adjust an order's payment status just because the customer said they
   paid -- that's how you get free orders. What CAN be automated is the
   *verification step*: look up the transaction against the payment gateway
   ledger. So `automatable=True` here means "an automated backend check could
   resolve this without a human IF the customer supplies a verifiable
   reference (transaction id / UTR / invoice no.)" -- not "we believe the
   customer and act on it".

2. Some categories are automatable in principle but are still routed to a
   human because of financial or legal/compliance risk, independent of how
   confident the classifier is. Duplicate charges (refund risk, possible
   fraud pattern) and invoice name mismatches (GST/tax legal implications in
   India) fall in this bucket. `requires_human_review` therefore is not
   simply "NOT automatable" -- it's a separate, risk-driven flag layered on
   top.

3. A large amount is treated as an independent safety trigger. Even a
   category that's normally low-risk (e.g. payment not reflected) gets
   forced into human review above a threshold, because the cost of an
   automated system getting a large-value decision wrong is much higher than
   getting a small one wrong. This is a simple, explainable guardrail rather
   than a learned one.

4. Low classifier confidence (UNCERTAIN category) always requires a human.
   An automated system should never act confidently on a case it wasn't sure
   how to classify in the first place.

Everything below is intentionally table-driven (`CATEGORY_RULES`) so adding a
new issue type later means adding one dict entry, not rewriting branching
logic.
"""

from dataclasses import dataclass
from typing import List
from app.models import (
    Decision, ClassificationResult, ExtractedEntities, IssueCategory, RiskLevel
)

HIGH_VALUE_THRESHOLD = 20000.0  # INR; amounts at/above this always get a human look


@dataclass
class CategoryRule:
    risk_level: RiskLevel
    always_human_review: bool
    # entities whose absence should be requested from the customer before
    # any automation can proceed
    required_for_automation: List[str]
    missing_info_prompts: dict  # entity name -> prompt text
    action_if_automatable: str
    action_if_needs_human: str
    reasoning_template: str


CATEGORY_RULES = {
    IssueCategory.PAYMENT_NOT_REFLECTED: CategoryRule(
        risk_level=RiskLevel.MEDIUM,
        always_human_review=False,
        required_for_automation=["transaction_refs"],
        missing_info_prompts={
            "transaction_refs": "UTR / transaction ID / payment reference number",
        },
        action_if_automatable="Auto-verify the transaction reference against the payment gateway "
                               "ledger and, if it matches, mark the order as paid.",
        action_if_needs_human="Ask the customer for the transaction reference; if provided but "
                               "the gateway lookup fails to find a matching payment, escalate to "
                               "finance/support for manual reconciliation.",
        reasoning_template="Customer claims a payment was made but the order still shows unpaid. "
                            "This must be verified against actual payment records before any "
                            "status change -- the customer's claim alone is not sufficient evidence.",
    ),
    IssueCategory.PARTIAL_PAYMENT_MISMATCH: CategoryRule(
        risk_level=RiskLevel.LOW,
        always_human_review=False,
        required_for_automation=["transaction_refs"],
        missing_info_prompts={
            "transaction_refs": "reference/receipt for the earlier partial payment",
        },
        action_if_automatable="Recompute due amount (invoice total - verified prior payment) and "
                               "update the invoice automatically once the prior payment is confirmed "
                               "in the ledger.",
        action_if_needs_human="Ask for the receipt/reference of the earlier partial payment to "
                               "confirm it before recalculating the invoice.",
        reasoning_template="Customer reports a partial payment that isn't reflected in the invoice "
                            "due amount. This is a straightforward recalculation once the earlier "
                            "payment is confirmed, so it's low risk and a good automation candidate.",
    ),
    IssueCategory.DUPLICATE_CHARGE: CategoryRule(
        risk_level=RiskLevel.HIGH,
        always_human_review=True,
        required_for_automation=["transaction_refs"],
        missing_info_prompts={
            "transaction_refs": "both transaction IDs (or a bank statement screenshot) showing the two charges",
        },
        action_if_automatable="N/A - always routed to a human regardless of data completeness.",
        action_if_needs_human="Collect both transaction references / bank statement evidence and "
                               "route to finance for refund or gateway dispute processing.",
        reasoning_template="Duplicate charges involve a refund decision and potential payment-gateway "
                            "or fraud investigation. Refunding money is not something this system "
                            "should ever trigger without a human sign-off, regardless of how clear-cut "
                            "the message looks.",
    ),
    IssueCategory.BILLING_NAME_MISMATCH: CategoryRule(
        risk_level=RiskLevel.MEDIUM,
        always_human_review=True,
        required_for_automation=["invoice_numbers"],
        missing_info_prompts={
            "invoice_numbers": "invoice number",
            "company_details": "correct company name, GSTIN, and billing address to reissue the invoice",
        },
        action_if_automatable="Draft a corrected invoice with the company's name/GSTIN for human "
                               "approval before issuing.",
        action_if_needs_human="Collect the correct company name, GSTIN and address; a human must "
                               "approve any invoice reissue due to tax/compliance implications.",
        reasoning_template="Reissuing an invoice under a different legal entity has GST/tax compliance "
                            "implications in India, so a human must approve it even though drafting the "
                            "corrected invoice itself could be automated.",
    ),
    IssueCategory.UNMATCHED_PAYMENT: CategoryRule(
        risk_level=RiskLevel.MEDIUM,
        always_human_review=False,
        required_for_automation=["transaction_refs", "time_references"],
        missing_info_prompts={
            "transaction_refs": "transaction ID / UTR number",
            "time_references": "approximate date/time of the payment",
            "payment_mode": "payment mode used (UPI/card/net banking) and last 4 digits if available",
        },
        action_if_automatable="Run an automated reconciliation match: search open invoices for the "
                               "same amount within a nearby date window. If exactly one match is "
                               "found, link it automatically; if multiple match, escalate to a human.",
        action_if_needs_human="Ask for transaction ID, approximate date, and payment mode to narrow "
                               "down the matching invoice.",
        reasoning_template="An unmatched payment can often be resolved by matching amount + date "
                            "against outstanding invoices, but if more than one invoice could match "
                            "the amount, a human must disambiguate to avoid crediting the wrong account.",
    ),
    IssueCategory.UNCERTAIN: CategoryRule(
        risk_level=RiskLevel.MEDIUM,
        always_human_review=True,
        required_for_automation=[],
        missing_info_prompts={
            "clarification": "a plain description of what happened and what the customer expects to happen next",
        },
        action_if_automatable="N/A",
        action_if_needs_human="The message doesn't clearly match a known issue type; a human should "
                               "read it and either resolve it directly or add a new category/keyword "
                               "pattern for it.",
        reasoning_template="The classifier could not confidently place this message in a known "
                            "category. Acting automatically on a case we don't understand is riskier "
                            "than the cost of a human reading it.",
    ),
}


def _entity_present(entities: ExtractedEntities, field: str) -> bool:
    value = getattr(entities, field, None)
    if isinstance(value, list):
        return len(value) > 0
    return bool(value)


def decide(message: str, entities: ExtractedEntities, classification: ClassificationResult) -> Decision:
    rule = CATEGORY_RULES[classification.category]

    missing_information: List[str] = []
    for field in rule.required_for_automation:
        if not _entity_present(entities, field):
            missing_information.append(rule.missing_info_prompts.get(field, field))
    # category-specific extra prompts that aren't tied to a single extractable
    # field (e.g. "company details" for name mismatch) are always requested
    # for that category since we have no reliable extractor for them yet
    for extra_key, prompt in rule.missing_info_prompts.items():
        if extra_key not in rule.required_for_automation and extra_key not in ("transaction_refs", "time_references", "invoice_numbers"):
            missing_information.append(prompt)

    high_value = any(a >= HIGH_VALUE_THRESHOLD for a in entities.amounts)

    automation_data_complete = len(missing_information) == 0 or all(
        rule.missing_info_prompts.get(f) not in missing_information for f in rule.required_for_automation
    )
    # automatable reflects whether the *category* is ever eligible for
    # automation, and whether the specific message currently has the data
    # needed -- both must hold.
    category_eligible_for_automation = not rule.always_human_review
    has_required_entities = all(_entity_present(entities, f) for f in rule.required_for_automation)
    automatable = category_eligible_for_automation and has_required_entities

    requires_human_review = (
        rule.always_human_review
        or classification.category == IssueCategory.UNCERTAIN
        or high_value
        or not has_required_entities  # missing critical data -> can't safely automate -> ask or escalate
    )

    if automatable and not requires_human_review:
        next_action = rule.action_if_automatable
    else:
        next_action = rule.action_if_needs_human

    reasoning_parts = [rule.reasoning_template]
    if high_value:
        reasoning_parts.append(
            f"Additionally, this involves an amount >= ₹{HIGH_VALUE_THRESHOLD:,.0f}, "
            "which is always routed to a human as a safety threshold regardless of category."
        )
    if not has_required_entities and not rule.always_human_review:
        reasoning_parts.append(
            "Required verification data is missing from the message, so it cannot be "
            "safely automated yet -- see missing_information."
        )

    return Decision(
        message=message,
        entities=entities,
        classification=classification,
        risk_level=rule.risk_level,
        automatable=automatable,
        requires_human_review=requires_human_review,
        missing_information=missing_information,
        recommended_next_action=next_action,
        reasoning=" ".join(reasoning_parts),
    )
