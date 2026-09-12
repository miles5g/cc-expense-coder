import re
import unittest
from pathlib import Path

from tests.forbidden_names import ALLOWED_ENTITIES, ALLOWED_PEOPLE, FIRM_AND_PRODUCT


ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("cc_coder", "fixtures")
SCAN_FILES = ("README.md",)
SKIP_SUFFIXES = {".pyc"}
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"\b(?:\+1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")


def _iter_text_files() -> list[Path]:
    paths: list[Path] = []
    for folder in SCAN_DIRS:
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.suffix not in SKIP_SUFFIXES:
                paths.append(path)
    for name in SCAN_FILES:
        path = ROOT / name
        if path.is_file():
            paths.append(path)
    return paths


class NoRealWorldLeakTests(unittest.TestCase):
    def test_no_denylisted_firm_or_product_names(self):
        leaks: list[str] = []
        for path in _iter_text_files():
            text = path.read_text(encoding="utf-8")
            for needle in FIRM_AND_PRODUCT:
                pattern = re.compile(rf"(?<![A-Za-z]){re.escape(needle)}(?![A-Za-z])", re.I)
                if pattern.search(text):
                    leaks.append(f"{path.relative_to(ROOT)}: {needle}")
        self.assertEqual(leaks, [])

    def test_no_emails_or_phone_numbers_in_shipped_text(self):
        leaks: list[str] = []
        for path in _iter_text_files():
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(ROOT)
            for match in EMAIL_RE.findall(text):
                leaks.append(f"{rel}: email {match}")
            for match in PHONE_RE.findall(text):
                leaks.append(f"{rel}: phone {match}")
        self.assertEqual(leaks, [])

    def test_people_and_entities_are_only_the_synthetic_cast(self):
        entity_map = (ROOT / "fixtures" / "entity_map.csv").read_text(encoding="utf-8")
        for person in ALLOWED_PEOPLE:
            self.assertIn(person, entity_map)
        for entity in ALLOWED_ENTITIES:
            self.assertIn(entity, entity_map)
        raw = (ROOT / "fixtures" / "raw_statement.csv").read_text(encoding="utf-8")
        for banned in ("@gmail.com", "@yahoo.com", "@outlook.com", "mailto:"):
            self.assertNotIn(banned, raw.lower())

    def test_gl_codes_are_dummy_four_digits(self):
        rows = (ROOT / "fixtures" / "chart_of_accounts.csv").read_text(encoding="utf-8").splitlines()[1:]
        for line in rows:
            code = line.split(",", 1)[0]
            self.assertRegex(code, r"^\d{4}$")
            self.assertTrue(code.startswith(("21", "51", "52", "53", "54", "55", "58")))


if __name__ == "__main__":
    unittest.main()
