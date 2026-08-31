# Design Notes

## Approach

I treated this as a 3-stage pipeline: **extract → classify → decide**.

1. **Extract** structured entities (amounts, invoice/order/transaction
   numbers, time references, a couple of boolean flags) from the raw text
   using regex/keyword matching.
2. **Classify** the message into one of five issue categories (or
   `UNCERTAIN`) using keyword scoring, boosted by a few structural signals
   from the extracted entities (e.g. two distinct amounts nudges the score
   toward "partial payment mismatch").
3. **Decide**, using a table of per-category business rules, whether the
   case is automatable, whether it always needs a human regardless, what
   information is missing, and what to do next — with a couple of
   cross-cutting safety overrides (large amount, low classifier confidence)
   applied on top of the per-category rules.

I kept every stage in independent, testable Python modules with a shared
Pydantic schema between them (`app/models.py`), so any stage — most likely
the classifier — can be replaced with an LLM-backed version later without
changing anything else.

## Important design decisions (and why)

**1. Claims from the customer are evidence, not facts.**
Nowhere does the system take an action (mark paid, reverse a charge, reissue
an invoice) purely because the customer said so. "Automatable" is always
defined relative to *verifying the claim against a backend record* (a
payment gateway, a ledger), not acting on the text directly. This is the
single most important safety property of the design — an LLM-only system
that reads "I paid ₹4,500" and just... marks the order paid, is a fraud
vector.

**2. Automation-eligibility and human-review are separate, independent
flags**, not two ends of the same switch.
- `automatable` = "given the required verification data, could an automated
  backend check resolve this with no human?" — purely a data/complexity
  question.
- `requires_human_review` = "should a human look at this anyway, because of
  risk?" — a business/compliance/fraud question layered on top.

A case can be automatable but still routed to a human (duplicate charges,
name mismatches, large amounts). This mirrors how I'd actually want a real
support system to behave: "could" and "should" are different questions.

**3. Two independent safety overrides, applied regardless of category:**
- **High amount (≥ ₹20,000)** always forces human review. This is a blunt
  threshold, not learned, but it's explainable to a non-technical
  stakeholder in one sentence, and it bounds the system's downside: even if
  every other rule is wrong, a large-value mistake still gets caught.
- **Low classification confidence (`UNCERTAIN`)** always forces human
  review. An automated system should never act confidently on a case it
  wasn't confident how to classify in the first place.

**4. Rule-based classification over an LLM, for this task.**
With only five known categories and small, controllable keyword lists, rules
get full coverage of the given examples with zero hallucination risk and
complete auditability (every classification names the exact phrases that
triggered it). The trade-off — brittleness to paraphrasing/colloquial
language — is real and is called out explicitly below and in the additional
test cases (see message 6, the Hinglish example, which the current keyword
list correctly fails to confidently classify rather than guessing wrong).

**5. Regex-based entity extraction, with a caught bug worth mentioning.**
My first version of the invoice/order regex matched *any* word following
"invoice"/"order" (so "invoice says" extracted "says" as if it were an
invoice number). I caught this by actually running the pipeline on the
sample messages and inspecting the output rather than just reading the code
— a reminder that entity extraction regexes need adversarial testing, not
just "does it match the happy path." The fix requires the captured token to
contain a digit, since every real identifier NextBill would issue does.

## Assumptions

- Currency is always INR and amounts are written with a "₹" symbol in the
  primary path; amounts written as "Rs 9,000" or in words are a known gap
  (see below), not handled by the regex extractor, though the pipeline still
  behaves safely (missing entities → routed for more info / human review).
- There is a backend (payment gateway API, ledger/reconciliation system)
  that the "automatable" actions describe calling — this system does not
  implement that backend, only decides *whether* such a call could resolve
  the case if it existed.
- The ₹20,000 high-value threshold is illustrative; a real deployment would
  set this based on NextBill's actual fraud/chargeback risk tolerance and
  average order value, not a number I picked.
- "Human review" means routing to a support/finance agent queue with the
  extracted entities and reasoning attached — not that the system stops
  responding to the customer. In practice you'd still want an automatic
  acknowledgment sent to the customer even for human-routed cases.

## Cases the system cannot confidently handle

- **Colloquial / code-switched language** (e.g. Hinglish, heavy slang,
  typos). The keyword classifier will often fall back to `UNCERTAIN` here,
  which is the safe behavior but not a *good* one — see additional test
  case 6.
- **Genuinely new issue types** not in the five categories (e.g. refund
  delays, subscription cancellation billing, currency conversion disputes —
  see additional test case 4). These correctly land in `UNCERTAIN`, but the
  system offers no automatic way to *notice* that a new category should be
  created; that's a manual step for whoever reviews the `UNCERTAIN` queue.
- **Compound messages** describing two distinct issues at once (see
  additional test case 5: duplicate charge + wrong amount). The system picks
  a single primary category and routes to a human, which is safe, but it
  doesn't surface the second issue as a separate, trackable item.
- **Amounts without the ₹ symbol** ("Rs 9,000", "9000 rupees") are invisible
  to the current extractor (test case 7). The message still gets classified
  correctly from other keywords, but downstream automation that depends on
  amount matching (e.g. unmatched-payment reconciliation) would not have the
  number it needs.

## What I'd improve with more time

1. **LLM fallback for low-confidence cases**, constrained to the same
   `IssueCategory` enum via structured output/function calling, triggered
   only when the rule-based classifier's confidence is below threshold —
   keeping the fast/free/explainable path as the default and reserving the
   LLM for exactly the paraphrase-robustness gap it's good at.
2. **A feedback loop**: log every `UNCERTAIN` case and every
   human-override, and periodically mine them for new keyword phrases or
   entirely new categories, so the rule base actually improves from real
   traffic instead of staying frozen at whatever I wrote today.
3. **Better amount parsing**: handle "Rs", "INR", "rupees", and
   written-out numbers, and reconcile multiple representations of the same
   number in one message.
4. **Multi-issue detection**: instead of forcing one category per message,
   score all categories above a threshold and return a ranked list, so
   compound complaints aren't silently reduced to a single label.
5. **A thin FastAPI wrapper** exposing `POST /classify` for integration
   testing with an actual support-ticketing frontend, plus a small
   evaluation set with hand-labeled expected categories to track precision/
   recall as the keyword lists evolve.
