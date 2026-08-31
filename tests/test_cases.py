"""
Test messages.

GIVEN_MESSAGES: the 5 messages from the task prompt.
ADDITIONAL_MESSAGES: 8 messages I wrote to probe edge cases the original 5
don't cover -- see comments on each for what it's meant to test.
"""

GIVEN_MESSAGES = [
    "I paid ₹4,500 yesterday but my order still shows unpaid.",
    "My invoice says ₹12,000, but ₹2,000 was already paid. Why is the full amount showing as due?",
    "I was charged twice for the same order. Both transactions are showing in my bank statement.",
    "The payment was made by my company, but the invoice is under our director's name.",
    "₹25,000 was deducted from my bank account, but I don't know which invoice this payment belongs to.",
]

ADDITIONAL_MESSAGES = [
    # 1. Same core issue as case 1, but WITH a transaction reference supplied
    #    up front -- tests that automatable flips to True when the required
    #    entity is actually present, unlike case 1 which lacks it.
    "I paid ₹4,500 via UPI yesterday, transaction ID UTR-88213345, but my order still shows unpaid.",

    # 2. High-value version of "payment not reflected" -- tests the
    #    high-value safety threshold forcing human review even though the
    #    category itself is normally automatable.
    "I transferred ₹55,000 for order ORD-9931 two days ago but it still shows as unpaid.",

    # 3. Vague/ambiguous message with no clear category -- tests that the
    #    classifier correctly falls back to UNCERTAIN instead of guessing.
    "Something is wrong with my payment, please check and fix it.",

    # 4. Refund request, not covered by any of the 5 original categories --
    #    tests behaviour on a genuinely new issue type (should land in
    #    UNCERTAIN with a note that a new category may be needed).
    "I cancelled my order but haven't received my refund of ₹3,200 after 10 days.",

    # 5. Mixed/compound issue -- a duplicate charge AND a wrong amount in one
    #    message. Tests whether the system picks a reasonable primary
    #    category and still forces human review via the duplicate-charge rule.
    "I was charged ₹8,000 twice for order ORD-1123, and even the amount charged was wrong -- "
    "it should have been ₹6,500.",

    # 6. Hinglish / colloquial phrasing -- tests robustness of keyword
    #    matching to real-world informal language (expected: partial or no
    #    match, likely UNCERTAIN, highlighting a real limitation of the
    #    keyword approach).
    "Maine payment kar diya tha lekin order abhi bhi unpaid dikha raha hai, kya scene hai?",

    # 7. Currency/amount edge case -- amount written without the ₹ symbol.
    #    Tests the extractor's blind spot around symbol-only amount matching
    #    (expected: amounts list will be empty, which itself is informative).
    "I paid Rs 9,000 for invoice INV-4521 but it's still marked pending.",

    # 8. Legitimate invoice-name-mismatch case that ALSO includes an invoice
    #    number -- tests that automatable data-completeness logic works
    #    correctly for the billing_name_mismatch category too.
    "Our company paid invoice INV-7788, but it was issued in my personal name instead of "
    "the company's name -- can this be corrected?",
]

ALL_MESSAGES = GIVEN_MESSAGES + ADDITIONAL_MESSAGES
