"""Step 8's `report.md`: what came out of one job, for the job agent and for you.

`ReportWriter.render` turns the job's `CvResult`, its score rounds (`Round`) and the step-6
compare (`Comparison`) into Markdown; `write` saves it as `report.md` in the job's folder (next to
the PDF). Both refuse a report that contradicts itself: scores that don't match the rounds, or a
result saying Rezi read the same content when the compare found issues.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

from assistant.modules.cv.compare import Comparison
from assistant.modules.cv.data import CvResult, Round

REPORT_NAME = "report.md"
__all__ = ["REPORT_NAME", "ReportWriter", "Round"]


def _parts(result: CvResult, rounds: Iterable[Round], comparison: Comparison | None) -> tuple[list[Round], Comparison | None]:
    """The rounds and the compare given, else the result's own."""
    rounds = list(rounds) or list(result.rounds)
    if comparison is None and result.compare is not None:
        comparison = Comparison.from_value(result.compare)
    return rounds, comparison


def _cell(text: object) -> str:
    """Text safe in a Markdown table cell."""
    return str(text).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip() or "–"


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


class ReportWriter:
    """Writes `report.md`. `target_score`: the score the rounds aimed at (the config's, or the job's)."""

    def __init__(self, target_score: int = 90) -> None:
        self.target_score = target_score

    def check(self, result: CvResult, rounds: Iterable[Round] = (), comparison: Comparison | None = None) -> None:
        """ValueError if the parts disagree."""
        rounds, comparison = _parts(result, rounds, comparison)
        if rounds and result.scores and [r.score for r in rounds] != result.scores:
            raise ValueError(f"the result's scores {result.scores} aren't the rounds' {[r.score for r in rounds]}")
        if comparison is not None and result.match_ok and not comparison.match_ok:
            raise ValueError(f"the result says Rezi read the same content, but the compare found {comparison.summary()}")

    def render(
        self,
        result: CvResult,
        company: str,
        role: str = "",
        rounds: Iterable[Round] = (),
        comparison: Comparison | None = None,
        notes: str = "",
        today: date | None = None,
    ) -> str:
        """The report as Markdown. Raises what `check` raises."""
        rounds, comparison = _parts(result, rounds, comparison)
        self.check(result, rounds, comparison)
        scores = [r.score for r in rounds] or result.scores
        title = f"{company} – {role}" if role else company
        if result.status == "approved":
            outcome = "**Approved** by you"
        elif result.status == "ready":
            outcome = "**Ready** for your Submit"
        else:
            outcome = f"**Stopped:** {result.stop_reason.strip()}"
        out = [f"# CV report: {title}", "", f"{(today or date.today()).isoformat()} · {outcome}", ""]

        out += ["## Files", "", "| What | Where |", "|---|---|",
                f"| PDF | {_cell(result.pdf_path or '')} |"]  # fmt: skip
        for label, ref in (("Rezi resume", result.rezi_resume), ("Rezi check copy", result.check_copy)):
            out.append(f"| {label} | {_cell(f'{ref.name} ({ref.id})' if ref else '')} |")

        last = scores[-1] if scores else None
        reached = last is not None and last >= self.target_score
        out += ["", "## Rezi Score", "",
                f"Last: **{last if last is not None else 'none'}**, target {self.target_score} "
                f"({'reached' if reached else 'not reached'}), {len(scores)} round(s)."]  # fmt: skip
        if rounds:
            out += ["", "| Round | Score | Keywords added | Still missing | Note |", "|---|---|---|---|---|"]
            out += [f"| {n} | {r.score} | {_cell(', '.join(r.added))} | {_cell(', '.join(r.missing))} | {_cell(r.note)} |"
                    for n, r in enumerate(rounds, 1)]  # fmt: skip
        elif scores:
            out += ["", "Scores by round: " + ", ".join(str(s) for s in scores) + "."]

        out += ["", "## Keywords", "", "Still missing in Rezi at the end:", ""]
        out += [f"- {k}" for k in result.still_missing] or ["- none"]
        out += ["", "Left out: terms the JD asks for that aren't on your CVs, so not added:", ""]
        out += [f"- {k}" for k in result.keywords_left_out] or ["- none"]

        out += ["", "## Recommendations", ""]
        out += [f"- {r}" for r in result.recommendations] or ["- none"]

        out += ["", "## The page", "", f"- One page: {_yes(result.one_page)}",
                f"- Rezi read the same content: {_yes(result.match_ok)}"]  # fmt: skip
        if comparison is not None:
            out.append(f"- Compare ({comparison.mode}): {comparison.summary()}")
            out += [f"  - {issue.describe()}" for issue in comparison.issues]
        if result.section_order:
            out.append(f"- Section order: {', '.join(result.section_order)}")
        if result.order_reason:
            out.append(f"- Why: {result.order_reason}")
        out.append(f"- Your yes: {_yes(result.approved_by_user)}")

        if notes.strip():
            out += ["", "## Notes", "", notes.strip()]
        return "\n".join(out) + "\n"

    def write(
        self,
        folder: str | Path,
        result: CvResult,
        company: str,
        role: str = "",
        rounds: Iterable[Round] = (),
        comparison: Comparison | None = None,
        notes: str = "",
        today: date | None = None,
    ) -> Path:
        """`render`'s report saved as `<folder>/report.md` (replacing an older one); returns the path."""
        text = self.render(result, company, role, rounds, comparison, notes, today)
        path = Path(folder) / REPORT_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
