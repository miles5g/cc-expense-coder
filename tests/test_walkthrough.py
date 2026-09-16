import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from cc_coder.pipeline import build_parser, main
from cc_coder.walkthrough import (
    INNER_WIDTH,
    INTRO_PARAS,
    INTRO_TITLE,
    STAGE_NOTES,
    STAGES,
    render_box,
    render_stage_box,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def _run_main(argv: list[str], input_patch):
    stdout = StringIO()
    stderr = StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "out"
        argv = [*argv, "--fixtures", str(FIXTURES), "--output", str(output)]
        with (
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
            patch("builtins.input", input_patch),
        ):
            code = main(argv)
        journals = list((output / "journals").glob("*.csv"))
        wrote_recon = (output / "reconciliation.md").is_file()
    return code, stdout.getvalue(), stderr.getvalue(), wrote_recon, len(journals)


class WalkthroughTests(unittest.TestCase):
    def test_short_flag_enables_walkthrough(self):
        args = build_parser().parse_args(["-w", "--no-pause"])
        self.assertTrue(args.walkthrough)
        self.assertTrue(args.no_pause)

    def test_box_matches_dialogue_shape(self):
        box = render_box(
            "Step 2/5 · SPLIT",
            (
                "What you're seeing: Original file stays put. Split by "
                "entity. I don't force the totals.",
                'Say in interview: "I leave the original alone."',
            ),
        )
        lines = box.splitlines()
        self.assertTrue(lines[0].startswith("┌─ Step 2/5 · SPLIT "))
        self.assertTrue(lines[0].endswith("─"))
        self.assertTrue(any(line.startswith("│ What you're seeing:") for line in lines))
        self.assertTrue(any("Say in interview:" in line for line in lines))
        self.assertTrue(lines[-1].startswith("└"))
        self.assertEqual(len(lines[0]), 1 + INNER_WIDTH)
        self.assertEqual(len(lines[-1]), 1 + INNER_WIDTH)

    def test_walkthrough_no_pause_prints_banners(self):
        code, text, err, wrote_recon, journal_count = _run_main(
            ["--walkthrough", "--no-pause"],
            input_patch=Mock(side_effect=AssertionError("should not pause")),
        )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertTrue(wrote_recon)
        self.assertEqual(journal_count, 3)
        self.assertIn("┌─ Interview walkthrough ", text)
        self.assertIn("comic-book names", text)
        self.assertIn("Dummy GLs", text)
        self.assertIn("Not a real client file", text)
        self.assertIn("All fake data.", text)
        self.assertIn("I leave the original alone.", text)
        self.assertIn("I'm not guessing GL codes.", text)
        self.assertIn("Each entity journal balances.", text)
        self.assertNotIn("I keep the control file", text)
        intro_lines = [
            line
            for line in render_box(INTRO_TITLE, INTRO_PARAS).splitlines()
            if line.startswith("│")
        ]
        self.assertGreaterEqual(len(intro_lines), 2)
        self.assertLessEqual(len(intro_lines), 4)
        for index, name in enumerate(STAGES, start=1):
            self.assertIn(f"Step {index}/5 · {name}", text)
            banner = render_stage_box(index, 5, STAGE_NOTES[name])
            body_lines = [line for line in banner.splitlines() if line.startswith("│")]
            self.assertGreaterEqual(len(body_lines), 2, name)
            self.assertLessEqual(len(body_lines), 4, name)
        self.assertIn("What you're seeing:", text)
        self.assertIn("Say in interview:", text)
        self.assertIn("[OK]", text)
        self.assertNotIn("Press Enter to continue", text)

    def test_walkthrough_pauses_after_each_box(self):
        paused = Mock(return_value="")
        code, text, err, _, _ = _run_main(["--walkthrough"], input_patch=paused)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("Step 1/5 · CLEAN", text)
        self.assertEqual(paused.call_count, 1 + len(STAGES))

    def test_default_run_is_fast_labels_only(self):
        code, text, err, _, _ = _run_main(
            [],
            input_patch=Mock(side_effect=AssertionError("should not pause")),
        )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertIn("CC Expense Coder — synthetic portfolio run", text)
        for name in STAGES:
            self.assertIn(f"  {name}", text)
        self.assertNotIn("┌", text)
        self.assertNotIn("Say in interview:", text)
        self.assertNotIn("Press Enter to continue", text)


if __name__ == "__main__":
    unittest.main()
