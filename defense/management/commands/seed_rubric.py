"""
`python manage.py seed_rubric` — load the 6 criteria from docs/rubric.md into Criterion.

Idempotent: update_or_create by criterion number. The data migration
0002_seed_rubric calls seed_criteria() with the historical model, so a fresh
`migrate` always has the rubric.
"""
import re
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

RUBRIC_PATH = Path(__file__).resolve().parents[3] / "docs" / "rubric.md"

SECTION_RE = re.compile(r"^##\s+([ABC])\.\s")
CRITERION_RE = re.compile(
    r"^###\s+(\d+)\.\s+(.+?)\s+[—-]\s+(\d+(?:\.\d+)?)%\s+\((group|per proponent)\)\s*$")
GUIDE_RE = re.compile(r"^Guide:\s*(.*)$")
DESC_RE = re.compile(r"^-\s*([1-5]):\s*(.*)$")


def parse_rubric(text):
    """Parse docs/rubric.md into a list of criterion dicts."""
    criteria = []
    section = None
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        m = SECTION_RE.match(line)
        if m:
            section = m.group(1)
            current = None
            continue
        if line.startswith("## "):  # e.g. "## Panel's Decision"
            section = None
            current = None
            continue
        m = CRITERION_RE.match(line)
        if m:
            if section is None:
                raise ValueError(f"Criterion outside a section: {line!r}")
            current = {
                "number": int(m.group(1)),
                "section": section,
                "name": m.group(2).strip(),
                "weight": (Decimal(m.group(3)) / 100).quantize(Decimal("0.001")),
                "per_proponent": m.group(4) == "per proponent",
                "guide_question": "",
            }
            criteria.append(current)
            continue
        if current is None:
            continue
        m = GUIDE_RE.match(line)
        if m:
            current["guide_question"] = m.group(1).strip()
            continue
        m = DESC_RE.match(line)
        if m:
            current[f"desc_{m.group(1)}"] = m.group(2).strip()

    numbers = sorted(c["number"] for c in criteria)
    if numbers != [1, 2, 3, 4, 5, 6]:
        raise ValueError(f"Expected criteria 1-6 in the rubric, found {numbers}")
    for c in criteria:
        missing = [n for n in range(1, 6) if f"desc_{n}" not in c]
        if missing:
            raise ValueError(f"Criterion {c['number']} is missing descriptors {missing}")
    total = sum(c["weight"] for c in criteria)
    if total != Decimal("1"):
        raise ValueError(f"Rubric weights total {total * 100}%, expected 100%")
    return criteria


def seed_criteria(criterion_model, path=RUBRIC_PATH):
    """Create/update the criteria. Works with the real or a historical model."""
    data = parse_rubric(Path(path).read_text(encoding="utf-8"))
    created = 0
    for item in data:
        number = item.pop("number")
        _, was_created = criterion_model.objects.update_or_create(
            number=number, defaults={**item, "is_active": True})
        created += was_created
    return len(data), created


class Command(BaseCommand):
    help = "Seed the final defense rubric (criteria 1-6) from docs/rubric.md."

    def handle(self, *args, **options):
        from defense.models import Criterion

        try:
            total, created = seed_criteria(Criterion)
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Rubric seeded: {total} criteria ({created} created, {total - created} updated)."))
