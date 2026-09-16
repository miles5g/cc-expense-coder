# CC Expense Coder

**30-second demo** — Python 3.10+, stdlib only. No pip, no `.env`. Run from the repo root.

```bash
python3 -m cc_coder
python3 -m unittest
```

Windows: `py -3 -m cc_coder` then `py -3 -m unittest`.

You should see three `[OK]` journals (Wayne / Daily Bugle / Stark) and `wrote output/`. Open `output/journals/` and `output/reconciliation.md` — variance is reported, not forced.

---

**Portfolio demo** — multi-entity credit-card coding bot: clean → split → code → journal.

Recruiter-safe recreation of a close-period *pattern* (messy statement → bookable journals). **Not** production software and **not** an employer artifact.

## What it does

1. **Clean** raw statement CSV (drop thank-you payments, normalize country, vendor-first details, first-name cardholders)
2. **Split** by entity without deleting Origin; reconcile vs statement balance (reports variance, never force-matches)
3. **Code** merchants via Reference memory, then COA — never invents GLs; flags review rows
4. **Finalize** reference `times_seen` for approved rows
5. **Journal** per entity: `GL Code / Debit / Credit / Description` + Card Payable balancer

## Synthetic-data rules

| | |
| --- | --- |
| People | Bruce Wayne, Peter Parker, Clark Kent, Diana Prince, Tony Stark |
| Entities | Wayne Enterprises LLC, Daily Bugle Media LLC, Stark Industries Holdings |
| Money | Whole round dollars only (`1000`, `5000`, `100000`, `1000000`) |
| GLs | Dummy 4-digit chart only (`5100` Office Supplies … `2100` Card Payable) |

No real emails, phones, clients, firm names, or employer SOP text.

## Quickstart

```bash
git clone https://github.com/miles5g/cc-expense-coder.git
cd cc-expense-coder
python3 -m cc_coder
```

## Pipeline

```
raw statement CSV
  → CLEAN → SPLIT → CODE → FINALIZE → JOURNAL → output/
```

## Status

Runnable. Tests cover journal balance, Origin kept, Reference-then-COA, and scrub guards.

## Author

Miles Johnson — [@miles5g](https://github.com/miles5g)
