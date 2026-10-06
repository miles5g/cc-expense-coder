"""Optional Claude step for rows the rules could not code.

Claude may only pick a GL that exists on the chart of accounts. Anything below
the confidence floor, or any answer that does not parse, stays in review.
Runs only with --llm and ANTHROPIC_API_KEY set. Stdlib HTTP, no SDK.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from cc_coder.models import ChartAccount, ReferenceRow, Transaction

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-5"
CONFIDENCE_FLOOR = 0.8
LLM_ELIGIBLE = {"no_gl", "ambiguous_coa"}

Caller = Callable[[str], str]


@dataclass
class LlmSummary:
    attempted: int = 0
    coded: int = 0
    still_review: int = 0
    errors: int = 0


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def build_prompt(row: Transaction, coa: list[ChartAccount], reference: list[ReferenceRow]) -> str:
    accounts = "\n".join(f"{a.gl_code} {a.name}" for a in coa if a.name.lower() != "card payable")
    examples = "\n".join(f"{r.merchant_key} -> {r.gl_code}" for r in reference[:20])
    return (
        "You code credit card transactions to a chart of accounts.\n"
        "Pick exactly one GL code from the list, or null if none fits.\n"
        "Never invent a code. Reply with JSON only: "
        '{"gl_code": "5100" or null, "confidence": 0.0-1.0, "reason": "short"}\n\n'
        f"Chart of accounts:\n{accounts}\n\n"
        f"Past coding examples:\n{examples or '(none)'}\n\n"
        f"Transaction: merchant={row.appears_as!r}, details={row.extended_details!r}, "
        f"amount={row.amount}, entity={row.entity!r}"
    )


def call_claude(prompt: str) -> str:
    body = json.dumps({
        "model": os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "".join(part.get("text", "") for part in data.get("content", []))


def parse_suggestion(text: str, valid_codes: set[str]) -> tuple[str, float, str] | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        gl = data.get("gl_code")
        confidence = float(data.get("confidence", 0))
    except (ValueError, TypeError, AttributeError):
        return None
    gl = str(gl).strip() if gl is not None else ""
    if gl not in valid_codes:
        return None
    return gl, confidence, str(data.get("reason", "")).strip()


def suggest_for_review(
    rows: list[Transaction],
    coa: list[ChartAccount],
    reference: list[ReferenceRow],
    *,
    caller: Caller = call_claude,
) -> LlmSummary:
    by_code = {a.gl_code: a for a in coa if a.name.lower() != "card payable"}
    summary = LlmSummary()
    for row in rows:
        if row.confidence != "review" or row.coding_source not in LLM_ELIGIBLE:
            continue
        summary.attempted += 1
        try:
            text = caller(build_prompt(row, coa, reference))
        except Exception as exc:  # network, auth, rate limit: keep the row for a human
            summary.errors += 1
            summary.still_review += 1
            row.review_reason = f"{row.review_reason}; LLM call failed ({type(exc).__name__})"
            continue
        suggestion = parse_suggestion(text, set(by_code))
        if suggestion is None:
            summary.still_review += 1
            row.review_reason = f"{row.review_reason}; LLM found no valid GL"
            continue
        gl, confidence, reason = suggestion
        if confidence < CONFIDENCE_FLOOR:
            summary.still_review += 1
            row.review_reason = f"LLM suggests {gl} at {confidence:.2f} (below {CONFIDENCE_FLOOR}): {reason}"
            continue
        row.gl_code = gl
        row.gl_name = by_code[gl].name
        row.coding_source = "llm"
        row.confidence = "confident"
        row.review_reason = f"LLM {confidence:.2f}: {reason}"
        summary.coded += 1
    return summary
