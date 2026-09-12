# CC Expense Coder

**Portfolio demo** of a multi-entity credit-card expense coding bot.

This repository reconstructs a common close-period *pattern*: take a messy card statement, make it bookable, split it by legal entity without losing the original file, code merchants from memory then a chart of accounts, and emit balanced journals. It is **not** production software, **not** an employer artifact, and **not** trained on anyone’s live books.

Synthetic universe only:

| Role | Names |
| --- | --- |
| People | Bruce Wayne, Peter Parker, Clark Kent, Diana Prince, Tony Stark |
| Entities | Wayne Enterprises LLC, Daily Bugle Media LLC, Stark Industries Holdings |
| Money | Whole round dollars (`1000`, `5000`, `100000`, `1000000`) |
| GLs | Invented 4-digit dummy chart (`5100` Office Supplies … `2100` Card Payable) |

No real emails, phones, client names, firm names, or product brands beyond ordinary public merchants (Amazon, Uber, Starbucks).

## Quickstart

From the repo root, Python 3.10+ stdlib only (`python3` if `python` is not on PATH):

```bash
python3 -m cc_coder
```

That reads `fixtures/` and writes `output/`. Useful flags:

```bash
python3 -m cc_coder --fixtures fixtures --output output
python3 -m unittest
```

Done means those commands produce per-entity journals plus a reconciliation summary that **reports** variance instead of forcing the statement to tie.

## What the one command does

```
raw statement CSV
    → CLEAN   drop online-payment thank-you rows;
              normalize country to UNITED STATES;
              fix vendor-first extended details;
              first-name cardholders;
              sort charges then credits
    → SPLIT   map first name → entity; keep Origin intact
    → CODE    Reference merchant memory, then COA keywords;
              never invent a GL; flag misses for review
    → FINALIZE  increment Reference times_seen for auto-approved rows
    → JOURNAL   per-entity file: GL Code, Debit, Credit, Description
```

Journal rules the demo implements:

- Description is `mm/dd/yy - appears-as`
- Positive charges → Debit the expense GL
- Negative credits → Credit the expense GL as a positive
- One Card Payable (`2100`) balancer per entity
- Debit total must equal Credit total or the run fails

## Fixture story (March 2026)

`fixtures/raw_statement.csv` is intentionally messy: `WAYNE, BRUCE` vs `BRUCE WAYNE`, `US` / `USA` / `U.S.A.`, a processor-prefixed Starbucks that only names the vendor in Extended Details, a parenthesized Amazon refund, and an `ONLINE PAYMENT THANK YOU` row.

Issuer-reported activity in `fixtures/statement_meta.json` is `1055000` because it still includes the `$100000` thank-you payment. After CLEAN, bookable activity is `1155000`. Variance is `100000` and is **left in the report**.

One merchant, Iron Works Rental (`$1000000`, Tony / Stark Industries Holdings), is absent from both Reference and COA keywords. It is written to `output/review_queue.csv` with an empty GL. The Stark journal balances on the *coded* remainder only.

## Outputs

| Path | Meaning |
| --- | --- |
| `output/origin.csv` | Full cleaned population. Split never deletes this. |
| `output/cleaned.csv` | Same rows after entity + coding fields are filled |
| `output/split/*.csv` | Per-entity copies |
| `output/coded.csv` | Auto-approved rows |
| `output/review_queue.csv` | Uncertain rows; no invented GLs |
| `output/reference_updated.csv` | Seed memory + times_seen bumps (fixtures stay unchanged) |
| `output/journals/*.csv` | Bookable entries, one file per entity |
| `output/reconciliation.md` | Human-readable variance story |
| `output/reconciliation.json` | Same numbers for tests / tools |

## Honest scope

**This shows**

- Statement hygiene (payments vs charges, country, cardholder, vendor-first details)
- Multi-entity split that preserves Origin
- Memory-first coding with a hard “do not invent GLs” rule
- Reconciliation that can be off and still be useful
- Journals a reviewer can add to zero

**This does not show**

- A live card issuer feed, SSO, or ERP post
- Human approval UI (the demo auto-approves confident rows)
- LLM guessing of accounts
- Anyone’s real chart of accounts, SOP text, or client file

If you have seen a similar workflow in practice, treat this as a clean-room reconstruction of the *shape*, written from generic accounting mechanics.

## Tests

`python -m unittest` checks the fixtures stay inside the synthetic cast, journals debit-equal-credit, thank-you rows are dropped, Reference wins over COA, Iron Works stays uncoded, and shipped text has no emails / phones / denylisted firm or product strings.
