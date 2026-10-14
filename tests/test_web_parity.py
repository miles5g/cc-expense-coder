"""The browser pipeline must write the same files as the Python CLI."""

import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from cc_coder.pipeline import REQUIRED_FIXTURES, run_pipeline


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
DOCS = ROOT / "docs"


def _files(folder: Path) -> dict[str, bytes]:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in folder.rglob("*")
        if path.is_file()
    }


class WebParityTests(unittest.TestCase):
    def test_published_fixtures_match_the_repo(self):
        for name in REQUIRED_FIXTURES:
            repo = (FIXTURES / name).read_bytes()
            published = (DOCS / "fixtures" / name).read_bytes()
            self.assertEqual(published, repo, name)

    def test_browser_outputs_match_python(self):
        node = shutil.which("node")
        if node is None:
            self.fail("node is required to run the browser pipeline")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            py_out = root / "py"
            js_out = root / "js"
            zip_path = root / "out.zip"
            run_pipeline(FIXTURES, py_out)
            subprocess.run(
                [node, str(DOCS / "render_outputs.js"), str(FIXTURES), str(js_out), str(zip_path)],
                check=True,
            )
            py_files = _files(py_out)
            js_files = _files(js_out)
            self.assertEqual(sorted(js_files), sorted(py_files))
            for name, payload in py_files.items():
                self.assertEqual(js_files[name], payload, name)
            with zipfile.ZipFile(zip_path) as archive:
                self.assertEqual(sorted(archive.namelist()), sorted(py_files))
                for name, payload in py_files.items():
                    self.assertEqual(archive.read(name), payload, name)

    def test_readme_leads_with_the_demo_link(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(
            text.startswith(
                "**[Open the demo](https://miles5g.github.io/cc-expense-coder/)**"
            )
        )

    def test_pages_workflow_deploys_docs(self):
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("path: docs", workflow)
        self.assertIn("actions/deploy-pages", workflow)

    def test_demo_copy_stays_plain(self):
        text = "\n".join(
            (DOCS / name).read_text(encoding="utf-8")
            for name in ("index.html", "app.js", "styles.css")
        )
        self.assertIn("Sample data only", text)
        self.assertIn("Comic-book names", text)
        for banned in ("Powered by", "gradient", "Say in interview", "✨", "🚀"):
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main()
