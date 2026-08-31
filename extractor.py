"""
Entity extraction: pulls structured facts out of raw customer text.

Design choice: this is regex/keyword based, NOT an LLM call.
Why: amounts, invoice numbers and reference numbers are exactly the kind of
short, high-stakes tokens where an LLM can silently hallucinate or transpose
digits (e.g. reading "12,000" as "1,2000" or inventing an invoice number that
"sounds right"). Regex extraction is slower to write and less flexible to
phrasing, but it is deterministic and auditable -- if it extracts ₹4,500,
you can point at the exact substring that produced it. That property matters
a lot when the extracted number can trigger a financial action.

An LLM extractor could be added later as a *fallback* for messages regex
can't parse (e.g. amounts written as words: "twelve thousand rupees"), but
its output should still be validated (e.g. re-checked against digits present
in the text) before being trusted -- see classifier.py docstring for more on
this validate-don't-trust-blindly pattern.
"""

import re
from app.models import ExtractedEntities

AMOUNT_PATTERN = re.compile(r"₹\s?([\d,]+(?:\.\d+)?)")
# Identifier tokens (invoice/order/txn numbers) must contain at least one digit.
# Without this constraint, phrases like "invoice says" or "order still" get
# misread as if "says"/"still" were the identifier -- a real bug caught during
# testing. Requiring a digit is a cheap, effective filter since every real
# invoice/order/reference number NextBill would issue contains digits.
_ID_TOKEN = r"([A-Za-z]*\d[A-Za-z0-9\-]*)"
INVOICE_PATTERN = re.compile(rf"\b(?:invoice|inv)[\s#:.\-]*{_ID_TOKEN}\b", re.IGNORECASE)
ORDER_PATTERN = re.compile(rf"\border[\s#:.\-]*{_ID_TOKEN}\b", re.IGNORECASE)
TXN_PATTERN = re.compile(rf"\b(?:txn|transaction id|utr|ref(?:erence)?)[\s#:.\-]*{_ID_TOKEN}\b", re.IGNORECASE)
TIME_WORDS = ["yesterday", "today", "last week", "last month", "this morning", "just now"]
THIRD_PARTY_WORDS = ["company", "director", "employer", "office", "organisation", "organization"]
DUPLICATE_WORDS = ["twice", "duplicate", "double charged", "charged again", "two transactions", "both transactions"]


def extract_entities(message: str) -> ExtractedEntities:
    text = message.lower()

    amounts = [float(a.replace(",", "")) for a in AMOUNT_PATTERN.findall(message)]

    # Invoice/order/txn regexes only fire when the message contains an actual
    # identifier next to the keyword (e.g. "invoice INV-2291"), not just the
    # bare word "invoice" -- that distinction itself is useful signal: if the
    # word "invoice" appears but no INVOICE_PATTERN match, we know the
    # customer referenced an invoice but didn't give us its number, which
    # later becomes a "missing_information" prompt.
    invoice_numbers = [m for m in INVOICE_PATTERN.findall(message) if not m.isdigit() or len(m) > 3]
    order_numbers = ORDER_PATTERN.findall(message)
    transaction_refs = TXN_PATTERN.findall(message)

    time_references = [w for w in TIME_WORDS if w in text]
    mentions_duplicate_charge = any(w in text for w in DUPLICATE_WORDS)
    mentions_third_party_payer = any(w in text for w in THIRD_PARTY_WORDS)

    # crude sanity counter: how many distinct numeric tokens appear at all
    # (used later to sanity check that we didn't miss an amount because it
    # wasn't prefixed with ₹, e.g. "Rs 4500" or "4500 rupees")
    raw_numbers_found = len(re.findall(r"\d[\d,]*", message))

    return ExtractedEntities(
        amounts=amounts,
        invoice_numbers=invoice_numbers,
        order_numbers=order_numbers,
        transaction_refs=transaction_refs,
        time_references=time_references,
        mentions_duplicate_charge=mentions_duplicate_charge,
        mentions_third_party_payer=mentions_third_party_payer,
        raw_numbers_found=raw_numbers_found,
    )
