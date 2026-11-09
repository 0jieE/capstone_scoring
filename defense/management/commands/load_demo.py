"""
`python manage.py load_demo` — demo data for a quick test run.

Creates 3 demo panelists (password `demo1234`), one demo defense with 2
proponents, and submitted ratings from all three that reproduce the worked
example: A 1.95, B 0.80, C 1.55, FINAL 4.30 -> PASSED with MINOR REVISIONS
from each panelist, so the panel decision is MINOR (3 of 3).

Safe to run again: the demo accounts are updated and the demo defense is
recreated.
"""
import datetime

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from defense import scoring
from defense.models import (
    Criterion, Defense, Evaluation, GroupRating, IndividualRating, PanelAssignment, Panelist,
    Proponent,
)

DEMO_PASSWORD = "demo1234"
DEMO_TITLE = "DEMO: Barangay Health Records Management System with SMS Notification"
DEMO_PANELISTS = [
    # username, prefix, first name, last name, suffix, role, manager?
    ("examiner1", "Engr.", "Juan A.", "Dela Cruz", "CCpE", PanelAssignment.EX1, False),
    ("examiner2", "Dr.", "Maria B.", "Santos", "", PanelAssignment.EX2, False),
    ("coordinator", "", "Ana C.", "Reyes", "LPT", PanelAssignment.RC, True),
]
DEMO_PROPONENTS = ["Carlo D. Mendoza", "Liza E. Bautista"]
# The worked example (AGENT_PROMPT.md section 4): criterion number -> rating
WORKED_EXAMPLE = {1: 4, 2: 5, 3: 4, 4: 4, 5: 5, 6: 4}


class Command(BaseCommand):
    help = "Load demo panelists, a defense, and sample ratings (worked example, FINAL 4.30)."

    def handle(self, *args, **options):
        if Criterion.objects.count() < 6:
            call_command("seed_rubric", verbosity=0)
        criteria = list(Criterion.objects.filter(is_active=True).order_by("number"))

        with transaction.atomic():
            panelists = {}
            for username, prefix, first, last, suffix, role, manager in DEMO_PANELISTS:
                user, _ = User.objects.get_or_create(username=username)
                user.first_name, user.last_name = first, last
                user.is_staff = manager
                user.is_active = True
                user.set_password(DEMO_PASSWORD)
                user.save()
                p, _ = Panelist.objects.get_or_create(user=user)
                p.prefix, p.suffix = prefix, suffix
                p.save()
                panelists[role] = p

            Defense.objects.filter(title=DEMO_TITLE).delete()
            defense = Defense.objects.create(
                title=DEMO_TITLE,
                schedule_date=timezone.localdate(),
                schedule_time=datetime.time(9, 0),
                venue="ITE Function Room",
            )
            proponents = [Proponent.objects.create(defense=defense, full_name=name, order=i)
                          for i, name in enumerate(DEMO_PROPONENTS)]

            for role in PanelAssignment.ROLES:
                a = PanelAssignment.objects.create(
                    defense=defense, panelist=panelists[role], role=role)
                ev = Evaluation.objects.create(
                    assignment=a, submitted=True, submitted_at=timezone.now(),
                    comments="Demo comment: tighten input validation and update Chapter 5 "
                             "recommendations to match the results.")
                for c in criteria:
                    r = WORKED_EXAMPLE[c.number]
                    if c.per_proponent:
                        IndividualRating.objects.bulk_create(
                            IndividualRating(evaluation=ev, criterion=c, proponent=p, rating=r)
                            for p in proponents)
                    else:
                        GroupRating.objects.create(evaluation=ev, criterion=c, rating=r)

        result = scoring.compute_defense(defense)
        d = result.decision
        self.stdout.write(self.style.SUCCESS(f"Demo defense created: {defense.title}"))
        for row in result.rows:
            self.stdout.write(
                f"  {row.assignment.get_role_display():<22} {row.assignment.panelist.user.username:<12}"
                f" A {scoring.round2(row.score.A)}  B {scoring.round2(row.score.B)}"
                f"  C {scoring.round2(row.score.C)}  FINAL {scoring.round2(row.score.final)}")
        self.stdout.write(f"  Panel decision: {d.verdict_label} ({d.group.summary})")
        self.stdout.write(
            f"Log in as examiner1 / examiner2 / coordinator (manager) with password "
            f"'{DEMO_PASSWORD}'.")
