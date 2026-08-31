"""
Test messages.

GIVEN_MESSAGES: the 5 messages from the task prompt.
ADDITIONAL_MESSAGES: 8 additional test cases
"""

GIVEN_MESSAGES = [
    "I paid ₹4,500 yesterday but my order still shows unpaid.",
    "My invoice says ₹12,000, but ₹2,000 was already paid. Why is the full amount showing as due?",
    "I was charged twice for the same order. Both transactions are showing in my bank statement.",
    "The payment was made by my company, but the invoice is under our director's name.",
    "₹25,000 was deducted from my bank account, but I don't know which invoice this payment belongs to.",
]

ADDITIONAL_MESSAGES = [
    "I paid ₹4,500 via UPI yesterday, transaction ID UTR-88213345, but my order still shows unpaid.",

    "I transferred ₹55,000 for order ORD-9931 two days ago but it still shows as unpaid.",

    "Something is wrong with my payment, please check and fix it.",

    "I cancelled my order but haven't received my refund of ₹3,200 after 10 days.",

    "I was charged ₹8,000 twice for order ORD-1123, and even the amount charged was wrong -- "
    "it should have been ₹6,500.",

    "Maine payment kar diya tha lekin order abhi bhi unpaid dikha raha hai, kya scene hai?",

    "I paid Rs 9,000 for invoice INV-4521 but it's still marked pending.",

    "Our company paid invoice INV-7788, but it was issued in my personal name instead of "
    "the company's name -- can this be corrected?",
]

ALL_MESSAGES = GIVEN_MESSAGES + ADDITIONAL_MESSAGES
