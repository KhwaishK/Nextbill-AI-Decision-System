# Design Notes

## How I approached it

I split the problem into three simple steps, one message at a time:

1. **Pull out the facts** — amount, invoice number, order number, transaction
   ID, anything mentioned like "yesterday". 
2. **Figure out what kind of problem it is** — payment not showing up,
   partial payment confusion, double charge, wrong name on invoice, or "I
   don't know which invoice this is for." Done with keyword matching, not an
   LLM.
3. **Decide what to do about it** — can this be handled automatically, does
   it need a human anyway, and what's missing before anything can happen.
   This part is just a table of rules, one row per issue type.

That's it. No ML model, no LLM call in the main flow. Each of those three
steps is its own file so any one of them could be swapped out later (say,
step 2 becomes an LLM call) without touching the other two.

## The decisions that actually matter here

**The customer saying "I paid" doesn't mean they paid, at least not as far
as the system is concerned.**
This is probably the most important thing in the whole design. The system
never marks an order as paid, reverses a charge, or fixes an invoice just
because the message says so. All it ever says is "this could be checked
automatically if we had a transaction ID to look up." If there's no way to
verify a claim, it doesn't get acted on, it gets asked for more proof, or
sent to a person. This is basically the whole point of not just handing
this straight to an LLM and letting it "decide" things — it has no way to
actually verify anything, it can only read words.

**"Can this be automated" and "should a human look at it anyway" are two
different questions, not one.**
I kept these as two separate flags instead of one. Why? Because sometimes a
case has all the data needed to be handled by a script, but you still don't
want to let it run without a person's eyes on it. Example: someone getting
charged twice. Even if we have both transaction IDs and everything lines up
perfectly, I still send that to a human because it ends in a refund, and
refunds are exactly the kind of thing you don't want a rule-based system
approving on its own.

**Two blunt safety nets sit on top of everything else:**
- Anything ₹20,000 or more automatically gets flagged for a human, no matter
  what category it is. It's not a smart rule, it's a deliberately dumb one,
  easy to explain to anyone, and it puts a ceiling on how bad an automated
  mistake could get.
- If the system genuinely isn't sure what category a message belongs to, it
  doesn't guess, it just says "uncertain" and hands it to a person. I'd
  rather it admit it doesn't know than confidently pick the wrong bucket.

**Why keywords instead of an LLM for classification.**
There's only five categories here, and they're pretty distinct in the
language people use to describe them. A short list of phrases per category
gets every one of the five sample messages right, and this is the part I
actually care about. I can point at exactly which words made it pick that
category. No LLM API, no cost, no chance of it inventing something. The
honest downside: it's bad at anything worded differently than expected
slang, typos, mixed languages. I made sure to include a test case that
shows this weakness rather than hide it (a Hinglish message that correctly
comes back "uncertain" instead of getting misclassified with false
confidence).

**A bug I actually hit while testing, worth mentioning.**
My first version of the "find the invoice number" regex grabbed whatever
word came right after "invoice", so "invoice says ₹12,000" extracted
"says" as if it were an invoice number. Found it by literally running the
code on the sample messages and reading the output, not by staring at the
regex. Fixed it by requiring the extracted text to contain a digit, since
every real invoice number would have one anyway.

## Assumptions I made

- Money is always in rupees, written with a ₹ symbol. If it's written as
  "Rs 9,000" or spelled out in words, the extractor won't catch it, that's
  a known gap.
- I'm assuming there's some actual backend somewhere (payment gateway,
  ledger, whatever) that the "automatable" checks would call into. I didn't
  build that backend. I only figured out whether calling it would make
  sense for a given case.
- The ₹20,000 cutoff for "always needs a human" is a number I picked to
  make a point, not a real business threshold. A real one would come from
  NextBill's actual risk appetite.
- "Needs a human" just means it goes into a queue for someone to look at,
  it doesn't mean the customer hears nothing back. In a real system you'd
  still want an automatic "we're looking into it" reply sent immediately.

## Where this system isn't confident, and I'm not pretending otherwise

- **Messages that aren't written in plain English.** Hinglish, typos, heavy
  slang, the keyword matching just won't catch it, and it'll (correctly,
  but not helpfully) say "uncertain." Test case 6 shows this on purpose.
- **Problems that aren't one of the five categories at all**  like a refund
  that's taking too long. It'll land in "uncertain," which is safe, but the
  system has no way of noticing "hey, this keeps happening, maybe it should
  be its own category." That noticing has to happen by a person reviewing
  the uncertain pile.
- **One message, two problems.** If someone mentions a double charge *and*
  says the amount was wrong, the system just picks one category and sends
  it to a human which is safe, but it doesn't flag that there were
  actually two separate issues bundled together.
- **Amounts without the ₹ symbol.** "Rs 9,000" just won't get picked up as
  an amount at all right now. The message still classifies fine off other
  words in the text, but anything downstream that needed the actual number
  (like matching an unmatched payment to an invoice by amount) wouldn't have
  it.

## What I'd do next if I had more time

1. Add an LLM as a **fallback**, not the main classifier only kick in when
   the keyword approach isn't confident. I'd force its output to match the
   same fixed set of categories rather than letting it return free text, so
   it can't go off script.
2. Actually log the "uncertain" cases and the ones a human overrides, and
   go back through them periodically to add new keywords or even whole new
   categories. Right now the rules are frozen at whatever I wrote today 
   they should learn from real traffic over time.
3. Handle more ways of writing amounts "Rs", "INR", spelled-out numbers 
   and make sure duplicate mentions of the same amount don't get
   double-counted.
4. Let one message get tagged with more than one issue instead of forcing
   everything into a single category.
5. Wrap it in a small FastAPI endpoint so it could actually plug into a real
   support tool, and build a small labeled test set to track accuracy as I
   keep tweaking the keyword lists.
