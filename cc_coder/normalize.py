"""String and money normalizers. No issuer-specific parsers — generic patterns only."""

from __future__ import annotations

import re
from datetime import datetime


PAYMENT_THANK_YOU = re.compile(
    r"(online\s+payment.*thank\s+you)|(payment\s+thank\s+you)|"
    r"(thank\s+you\s+for\s+(your\s+)?payment)|(autopay\s+payment)|"
    r"(payment\s+received\s+thank\s+you)",
    re.IGNORECASE,
)

PROCESSOR_PREFIX = re.compile(
    r"^(sq\s*\*|tst\s*\*|paypal\s*\*|spp\s*\*|pos\s*\*)\s*",
    re.IGNORECASE,
)

TRAILING_LOCATION = re.compile(
    r"\s+\d{5}(?:-\d{4})?$|"
    r"\s+[A-Z]{2}$|"
    r"\s+(united\s+states|usa|us)$",
    re.IGNORECASE,
)

STORE_NUMBER = re.compile(r"\s+#?\d{3,}$")

COUNTRY_ALIASES = {
    "US": "UNITED STATES",
    "USA": "UNITED STATES",
    "U.S.": "UNITED STATES",
    "U.S.A.": "UNITED STATES",
    "U.S.A": "UNITED STATES",
    "UNITED STATES OF AMERICA": "UNITED STATES",
    "UNITED STATES": "UNITED STATES",
}

# Public-merchant aliases only. Keys are already loosely normalized.
MERCHANT_ALIASES = {
    "amazon.com": "amazon",
    "amzn": "amazon",
    "amazon mktplace": "amazon",
    "amazon marketplace": "amazon",
    "uber trip": "uber",
    "uber *trip": "uber",
    "starbucks store": "starbucks",
}

PUBLIC_MERCHANT_ROOTS = {"amazon", "uber", "starbucks"}


def parse_amount(raw: str) -> int:
    """Parse a whole-dollar amount. Credits may be parenthesized or signed."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty amount")
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").replace(" ", "")
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if text.startswith("+"):
        text = text[1:]
    if "." in text:
        whole, frac = text.split(".", 1)
        if int(frac or "0") != 0:
            raise ValueError(f"non-whole-dollar amount not allowed: {raw!r}")
        text = whole
    if not text.isdigit():
        raise ValueError(f"invalid amount: {raw!r}")
    value = int(text)
    return -value if negative else value


def parse_date(raw: str) -> str:
    """Accept a few common statement date shapes; emit ISO YYYY-MM-DD."""
    text = (raw or "").strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {raw!r}")


def format_journal_date(iso_date: str) -> str:
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    return dt.strftime("%m/%d/%y")


def normalize_country(raw: str) -> str:
    key = re.sub(r"\s+", " ", (raw or "").strip().upper())
    return COUNTRY_ALIASES.get(key, key)


def first_name(cardholder: str) -> str:
    """Issuer files often ship LAST, FIRST or FIRST LAST. Keep the first name only."""
    text = re.sub(r"\s+", " ", (cardholder or "").strip())
    if not text:
        return ""
    if "," in text:
        after = text.split(",", 1)[1].strip()
        token = after.split(" ")[0] if after else ""
    else:
        token = text.split(" ")[0]
    return token[:1].upper() + token[1:].lower() if token else ""


def is_payment_thank_you(description: str, txn_type: str) -> bool:
    if (txn_type or "").strip().lower() == "payment":
        return True
    return bool(PAYMENT_THANK_YOU.search(description or ""))


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_vendor_first(description: str, extended_details: str) -> str:
    """If extended details lead with the vendor, prefer that over processor junk.

    Typical raw shape: Description is ``SQ *THE DAILY CUP`` while Extended Details
    starts with ``STARBUCKS 123 MAIN ST``. Take the leading vendor run and drop
    store numbers / city-state / ZIP tails.
    """
    desc = _collapse(description or "")
    ext = _collapse(extended_details or "")

    vendor_source = desc
    if ext:
        leading = _leading_vendor(ext)
        desc_is_processor = bool(PROCESSOR_PREFIX.match(desc))
        desc_is_generic = bool(
            re.match(r"^(purchase|pos|sale)(\s+authorized)?(\s+on\s+\d|/)", desc, re.I)
        )
        if leading and (desc_is_processor or desc_is_generic or not desc):
            vendor_source = leading
        elif leading and len(leading) >= len(_leading_vendor(desc) or ""):
            # Extended details still win when they start with a clearer vendor.
            if desc_is_processor or not _looks_like_vendor(desc):
                vendor_source = leading

    vendor = _leading_vendor(vendor_source) or vendor_source
    vendor = PROCESSOR_PREFIX.sub("", vendor)
    vendor = _strip_location_tail(vendor)
    vendor = STORE_NUMBER.sub("", vendor)
    vendor = re.sub(r"\*+[A-Z0-9]+$", "", vendor, flags=re.I)
    vendor = _collapse(vendor)
    return vendor or desc


def _looks_like_vendor(text: str) -> bool:
    cleaned = PROCESSOR_PREFIX.sub("", text)
    return bool(re.search(r"[A-Za-z]{3,}", cleaned))


def _leading_vendor(text: str) -> str:
    tokens = _collapse(text).split(" ")
    kept: list[str] = []
    for token in tokens:
        if re.fullmatch(r"\d{3,}", token):
            break
        if re.fullmatch(r"[A-Za-z]{2}", token) and kept:
            # likely state code after vendor
            break
        if re.fullmatch(r"\d{5}(?:-\d{4})?", token):
            break
        if token.upper() in {"US", "USA", "UNITED"} and kept:
            break
        kept.append(token)
        if len(kept) >= 4:
            break
    return _collapse(" ".join(kept))


def _strip_location_tail(text: str) -> str:
    current = text
    for _ in range(4):
        nxt = TRAILING_LOCATION.sub("", current).rstrip(" ,-")
        if nxt == current:
            break
        current = nxt
    return current


def merchant_key(appears_as: str) -> str:
    text = appears_as or ""
    text = PROCESSOR_PREFIX.sub("", text)
    text = text.lower()
    text = text.replace(".com", "")
    text = re.sub(r"[^a-z0-9\s*]", " ", text)
    text = re.sub(r"\*+", " ", text)
    text = _collapse(text)
    if text in MERCHANT_ALIASES:
        return MERCHANT_ALIASES[text]
    parts = text.split(" ")
    if parts and parts[0] in PUBLIC_MERCHANT_ROOTS:
        return parts[0]
    key = " ".join(parts[:3])
    return MERCHANT_ALIASES.get(key, key)


def slug_entity(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return text or "unmapped"


def title_merchant(appears_as: str) -> str:
    text = _collapse(appears_as or "")
    if not text:
        return ""
    if text.isupper() or text.islower():
        return text.title()
    return text
