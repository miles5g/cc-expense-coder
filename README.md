# CC Expense Coder

Turns a messy multi-person credit card statement into balanced, ready-to-import journal entries, one per entity.

This is a rebuild of a month-end workflow I run at work, on fake data so it can be public.

## Run it (30 seconds)

```bash
git clone https://github.com/miles5g/cc-expense-coder.git
cd cc-expense-coder
python3 -m cc_coder
```

Python 3.10+. Nothing to install. On Windows use `py -m cc_coder`.

Want each step explained as it runs? `python3 -m cc_coder --walkthrough`

## What happens

1. **Clean.** Drops card payments, standardizes names and countries.
2. **Split.** Groups each charge under the right entity based on who spent it.
3. **Code.** Assigns a GL account. Checks past coding first, then chart of accounts keywords. Anything unclear goes to a review queue instead of being guessed.
4. **Learn.** Approved matches update the merchant memory, so next month codes faster.
5. **Journal.** Writes one journal per entity. Debits equal credits. Review items stay out.

## What you get

```
coded / review:   12 / 1
journals:
  Daily Bugle Media LLC: debit=13000 credit=13000 [OK]
  Stark Industries Holdings: debit=125000 credit=125000 [OK]
  Wayne Enterprises LLC: debit=22000 credit=22000 [OK]
```

Files land in `output/`. Start with `output/journals/` and `output/reconciliation.md`.

## Optional: Claude for the leftovers

Rows the rules cannot code (here, a $1M equipment rental) can go to Claude:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m cc_coder --llm
```

Claude can only pick an account that exists on the chart. Answers under 0.8 confidence stay in review for a person. Without a key, the flag is skipped and the rules run alone.

## Tests

```bash
python3 -m unittest discover -s tests
```

Covers balanced journals, no guessed accounts, the Claude guardrails, and a check that no real client or firm names are in the repo.

## Data

All fake: comic book names, round dollar amounts, a made-up chart of accounts.
