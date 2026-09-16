"""Interview walkthrough banners for the CLI demo.

Boxed stage notes are opt-in (`--walkthrough`). The default path stays a
fast, unattended 30-second run.
"""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

INNER_WIDTH = 50
STAGES = ("CLEAN", "SPLIT", "CODE", "FINALIZE", "JOURNAL")
PAUSE_PROMPT = "Press Enter to continue… "


@dataclass(frozen=True)
class StageNote:
    name: str
    seeing: str
    say: str


STAGE_NOTES: dict[str, StageNote] = {
    "CLEAN": StageNote(
        name="CLEAN",
        seeing=(
            "Payments drop out; merchants normalize. Origin is the cleaned "
            "control copy."
        ),
        say='"I keep Origin intact."',
    ),
    "SPLIT": StageNote(
        name="SPLIT",
        seeing=(
            "Origin stays intact; each entity sheet gets its charges. "
            "Variance is reported, never forced."
        ),
        say='"I keep the control file…"',
    ),
    "CODE": StageNote(
        name="CODE",
        seeing=(
            "Reference first, then COA. Unknown merchants go to review — "
            "no invented GLs."
        ),
        say='"I never guess an account."',
    ),
    "FINALIZE": StageNote(
        name="FINALIZE",
        seeing="Approved codes bump times_seen. Review rows do not rewrite memory.",
        say='"Only confident hits stick."',
    ),
    "JOURNAL": StageNote(
        name="JOURNAL",
        seeing=(
            "Per-entity journals plus Card Payable. Debits equal credits; "
            "review stays out."
        ),
        say='"Each journal balances."',
    ),
}

INTRO_TITLE = "Interview walkthrough"
INTRO_PARAS = (
    "Synthetic comic-book names, dummy 4-digit GLs, round dollars. "
    "Not production. Not an employer file.",
    'Say in interview: "This is synthetic data."',
)


def render_box(
    title: str, paragraphs: Sequence[str], inner_width: int = INNER_WIDTH
) -> str:
    """Unicode dialogue box. `inner_width` is the dash count on the bottom rule."""
    label = f"─ {title} "
    fill = inner_width - len(label)
    if fill < 1:
        label = label[: max(inner_width - 1, 1)]
        fill = max(inner_width - len(label), 0)
    top = f"┌{label}{'─' * fill}"
    text_width = max(inner_width - 1, 1)
    body: list[str] = []
    for para in paragraphs:
        chunks = textwrap.wrap(para, width=text_width) or [""]
        body.extend(f"│ {chunk}" for chunk in chunks)
    bottom = f"└{'─' * inner_width}"
    return "\n".join([top, *body, bottom])


def render_stage_box(index: int, total: int, note: StageNote) -> str:
    title = f"Step {index}/{total} · {note.name}"
    return render_box(
        title,
        (
            f"What you're seeing: {note.seeing}",
            f"Say in interview: {note.say}",
        ),
    )


class Narrator:
    """Prints stage labels (default) or boxed interview notes (walkthrough)."""

    def __init__(
        self,
        *,
        walkthrough: bool,
        pause: bool,
        out: TextIO | None = None,
        pause_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.walkthrough = walkthrough
        self.pause = pause
        self.out = out if out is not None else sys.stdout
        self._pause_fn = pause_fn if pause_fn is not None else input
        self._total = len(STAGES)

    def intro(self) -> None:
        if not self.walkthrough:
            return
        print(render_box(INTRO_TITLE, INTRO_PARAS), file=self.out, flush=True)
        print(file=self.out, flush=True)
        self._wait()

    def stage(self, name: str) -> None:
        if self.walkthrough:
            try:
                index = STAGES.index(name) + 1
            except ValueError:
                index = 0
            note = STAGE_NOTES.get(name) or StageNote(name=name, seeing="", say="")
            print(render_stage_box(index, self._total, note), file=self.out, flush=True)
            print(file=self.out, flush=True)
            self._wait()
            return
        print(f"  {name}", file=self.out, flush=True)

    def _wait(self) -> None:
        if not self.pause:
            return
        try:
            self._pause_fn(PAUSE_PROMPT)
        except EOFError:
            print(file=self.out)
