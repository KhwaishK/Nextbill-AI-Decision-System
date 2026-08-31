# NextBill — AI Billing/Payment Message Decision System

A small system that reads a customer support message about a payment/billing
issue and decides:
- what the likely issue is,
- what entities (amounts, invoice/order/transaction numbers) are present,
- whether it can be automated end-to-end,
- whether a human must review it regardless, and
- what information is still missing before anything can be done.

## Why this approach

The 5 sample messages all resolve to a small, fixed set of issue types, and
getting them wrong has real financial/legal consequences (wrong refund,
wrong invoice reissued, wrongly marking an order as paid). Given that, I
optimized for **explainability and safety** over cleverness:

- **Rule-based classification, not an LLM**, as the default. A keyword/regex
  approach is fully auditable — for every decision I can point to the exact
  phrase or entity that produced it. It also fails safely: when nothing
  matches, confidence is 0 and the message is routed to a human, whereas an
  LLM will often confidently guess a category even when it shouldn't.
- **The customer's claim is never trusted as fact.** "I paid ₹4,500" is
  evidence, not proof. The system never auto-changes a payment/order status
  based on the text alone — it only ever says "this *could* be verified
  automatically *if* a transaction reference is supplied," and separately
  decides whether a human must look at it regardless of whether that
  verification succeeds.
- **Automation and human-review are two independent flags**, not opposites.
  A case can be automatable (all needed data present, low risk) yet still
  forced to a human because of a business rule (e.g. duplicate charges =
  potential refund + fraud investigation, always human; large amounts =
  always human, as a blunt but explainable safety net).

See `DESIGN.md` for the full reasoning, assumptions, and limitations.

## Project structure

```
nextbill-ai-decision-system/
├── app/
│   ├── models.py           # Pydantic schemas (entities, classification, decision)
│   ├── extractor.py        # Regex-based entity extraction
│   ├── classifier.py       # Rule-based issue classification (+ LLM extension seam)
│   ├── decision_engine.py  # Business rules: automatable? human review? missing info?
│   └── pipeline.py         # Wires the three stages together
├── tests/
│   └── test_cases.py       # The 5 given messages + 8 additional test messages I wrote
├── main.py                 # CLI entry point
├── requirements.txt
├── README.md
└── DESIGN.md                # Approach, decisions, assumptions, limitations, next steps
```

## How to run

Requires Python 3.9+.

```bash
pip install -r requirements.txt

# Run all test messages (given + additional) and print structured JSON decisions
python main.py

# Run a single custom message
python main.py "I paid ₹4,500 yesterday but my order still shows unpaid."
```

Each message produces output like:

```json
{
  "message": "I paid ₹4,500 yesterday but my order still shows unpaid.",
  "entities": {
    "amounts": [4500.0],
    "invoice_numbers": [],
    "order_numbers": [],
    "transaction_refs": [],
    "time_references": ["yesterday"],
    "mentions_duplicate_charge": false,
    "mentions_third_party_payer": false,
    "raw_numbers_found": 1
  },
  "classification": {
    "category": "payment_not_reflected",
    "confidence": 1.0,
    "matched_keywords": ["still shows unpaid", "i paid"],
    "scores": { "...": "..." }
  },
  "risk_level": "medium",
  "automatable": false,
  "requires_human_review": true,
  "missing_information": ["UTR / transaction ID / payment reference number"],
  "recommended_next_action": "Ask the customer for the transaction reference; ...",
  "reasoning": "Customer claims a payment was made but the order still shows unpaid. ..."
}
```

## Extending with an LLM

The system is structured so an LLM can be dropped in at two specific seams
without touching the rest of the pipeline:

1. **`app/classifier.py::classify_with_llm`** — a stub for using an LLM
   (e.g. OpenAI/Azure OpenAI structured outputs or function calling) as a
   *fallback* when the rule-based classifier's confidence is below
   threshold, rather than as the primary classifier. The LLM's output should
   be constrained to the same `IssueCategory` enum and validated against it —
   if it returns anything outside the enum, treat it as `UNCERTAIN` rather
   than trusting it.
2. **Entity extraction fallback** — for messages where amounts are written
   in words ("twelve thousand rupees") or without symbols, an LLM extractor
   could run after the regex extractor, but its output should be
   cross-checked against digit sequences actually present in the raw text
   before being accepted, to guard against hallucinated numbers.

I deliberately did not wire up a live LLM call for this submission, both to
avoid an API-key dependency for something this size, and because the rule
engine already fully explains every one of the 5 given cases with 100%/high
confidence — adding an LLM here wouldn't have demonstrated more judgement,
just more infrastructure.
