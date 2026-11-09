"""
Tests (see AGENT_PROMPT.md, section 8).

Worked example from the paper form:
ratings 4, 5, 4 | 4 | 5, 4  ->  A 1.95, B 0.80, C 1.55, FINAL 4.30, PASSED with MINOR REVISIONS

Panel decision: each panelist's FINAL gets a verdict; the panel's decision is
the verdict at least 2 of the 3 panelists agree on (no panel weights).
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import scoring
from .models import (
    Criterion, Defense, Evaluation, GroupRating, IndividualRating, PanelAssignment, Panelist,
    Proponent, ScoringSettings,
)

D = Decimal
WORKED_GROUP = {1: 4, 2: 5, 3: 4, 4: 4}
WORKED_ORAL = {5: 5, 6: 4}
ALL = lambda r: ({1: r, 2: r, 3: r, 4: r}, {5: r, 6: r})  # noqa: E731  FINAL = r


def make_user(username, staff=False, first="", last=""):
    return User.objects.create_user(username, password="pw123456", is_staff=staff,
                                    first_name=first or username.title(), last_name=last or "Test")


def make_defense(n_proponents=2, users=None):
    defense = Defense.objects.create(title="Test Capstone", schedule_date=datetime.date(2026, 5, 1))
    proponents = [Proponent.objects.create(defense=defense, full_name=f"Proponent {i + 1}", order=i)
                  for i in range(n_proponents)]
    users = users or [make_user(u) for u in ("ex1", "ex2", "rc")]
    assignments = []
    for user, role in zip(users, PanelAssignment.ROLES):
        assignments.append(PanelAssignment.objects.create(
            defense=defense, panelist=user.panelist, role=role))
    return defense, proponents, assignments


def rate(assignment, group, oral, submit=True):
    """group: {criterion number: rating}; oral: {criterion number: rating or [per proponent]}"""
    ev, _ = Evaluation.objects.get_or_create(assignment=assignment)
    crit = {c.number: c for c in Criterion.objects.all()}
    for num, r in group.items():
        GroupRating.objects.update_or_create(evaluation=ev, criterion=crit[num],
                                             defaults={"rating": r})
    proponents = list(assignment.defense.proponents.all())
    for num, r in oral.items():
        values = r if isinstance(r, (list, tuple)) else [r] * len(proponents)
        for p, v in zip(proponents, values):
            IndividualRating.objects.update_or_create(
                evaluation=ev, criterion=crit[num], proponent=p, defaults={"rating": v})
    if submit:
        ev.submitted = True
        ev.submitted_at = timezone.now()
        ev.save()
    return ev


class RubricSeedTests(TestCase):
    def test_migration_seeds_six_criteria(self):
        crit = list(Criterion.objects.order_by("number"))
        self.assertEqual([c.number for c in crit], [1, 2, 3, 4, 5, 6])
        self.assertEqual([c.section for c in crit], ["A", "A", "A", "B", "C", "C"])
        self.assertEqual([c.per_proponent for c in crit], [False] * 4 + [True] * 2)
        self.assertEqual(sum(c.weight for c in crit), D("1"))
        self.assertTrue(all(c.desc_1 and c.desc_5 for c in crit))


class ScoringMathTests(TestCase):
    def setUp(self):
        self.criteria = list(Criterion.objects.order_by("number"))
        self.by_num = {c.number: c for c in self.criteria}

    def score(self, group, oral, proponents=(1, 2)):
        g = {self.by_num[n].pk: r for n, r in group.items()}
        ind = {}
        for n, r in oral.items():
            values = r if isinstance(r, (list, tuple)) else [r] * len(proponents)
            for pid, v in zip(proponents, values):
                ind[(self.by_num[n].pk, pid)] = v
        return scoring.score_ratings(self.criteria, list(proponents), g, ind)

    def test_worked_example(self):
        s = self.score(WORKED_GROUP, WORKED_ORAL)
        self.assertEqual(s.A, D("1.95"))
        self.assertEqual(s.B, D("0.80"))
        self.assertEqual(s.C, D("1.55"))
        self.assertEqual(s.final, D("4.30"))
        self.assertTrue(s.complete)
        self.assertEqual(s.verdict, scoring.MINOR)
        self.assertEqual(s.verdict_label, "PASSED with MINOR REVISIONS")
        for p in s.proponents:
            self.assertEqual(p.C, D("1.55"))
            self.assertEqual(p.final, D("4.30"))

    def test_verdict_boundaries(self):
        cases = {"4.50": scoring.PASSED, "4.49": scoring.MINOR, "3.50": scoring.MINOR,
                 "3.49": scoring.MAJOR, "2.50": scoring.MAJOR, "2.49": scoring.FAILED,
                 "5.00": scoring.PASSED, "1.00": scoring.FAILED}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(scoring.get_verdict(D(value)), expected)

    def test_verdict_applies_to_rounded_value(self):
        self.assertEqual(scoring.get_verdict(D("4.495")), scoring.PASSED)    # -> 4.50
        self.assertEqual(scoring.get_verdict(D("4.4949")), scoring.MINOR)    # -> 4.49

    def test_custom_cutoffs(self):
        cutoffs = (D("4.00"), D("3.00"), D("2.00"))
        self.assertEqual(scoring.get_verdict(D("4.30"), cutoffs), scoring.PASSED)
        self.assertEqual(scoring.get_verdict(D("1.99"), cutoffs), scoring.FAILED)

    def test_round_half_up(self):
        self.assertEqual(scoring.round2(D("4.035")), D("4.04"))
        self.assertEqual(scoring.round2(D("3.805")), D("3.81"))
        self.assertEqual(scoring.round2(D("2.345")), D("2.35"))

    def test_floats_rejected(self):
        with self.assertRaises(TypeError):
            scoring.weighted_score(4, 0.2)

    def test_panel_decision_two_of_three(self):
        P, MI, MA, F = scoring.PASSED, scoring.MINOR, scoring.MAJOR, scoring.FAILED
        d = scoring.panel_decision([MI, MI, P])
        self.assertEqual((d.verdict, d.agreeing, d.majority), (MI, 2, True))
        d = scoring.panel_decision([P, MA, P])
        self.assertEqual((d.verdict, d.agreeing, d.majority), (P, 2, True))
        d = scoring.panel_decision([F, F, F])
        self.assertEqual((d.verdict, d.agreeing, d.summary), (F, 3, "3 of 3 panelists"))

    def test_panel_decision_no_majority_uses_middle(self):
        P, MI, MA = scoring.PASSED, scoring.MINOR, scoring.MAJOR
        for votes in ([P, MI, MA], [MA, P, MI], [MI, MA, P]):
            with self.subTest(votes=votes):
                d = scoring.panel_decision(votes)
                self.assertEqual(d.verdict, MI)
                self.assertFalse(d.majority)
        self.assertEqual(scoring.panel_decision(
            [P, MA, scoring.FAILED]).verdict, MA)

    def test_decision_from_individual_scores(self):
        # 4.30 (MINOR), 4.00 (MINOR), 5.00 (PASSED): 2 of 3 say MINOR
        s1 = self.score(WORKED_GROUP, WORKED_ORAL)
        s2 = self.score(*ALL(4))
        s3 = self.score(*ALL(5))
        self.assertEqual((s1.final, s2.final, s3.final), (D("4.30"), D("4.00"), D("5.00")))
        d = scoring.decide([s1, s2, s3])
        self.assertEqual(d.verdict, scoring.MINOR)
        self.assertEqual(d.group.agreeing, 2)
        self.assertEqual(d.group.verdicts, [scoring.MINOR, scoring.MINOR, scoring.PASSED])
        self.assertEqual([p.decision.verdict for p in d.proponents], [scoring.MINOR] * 2)
        self.assertFalse(d.has_split)

    def test_no_panel_weights_each_panelist_counts_the_same(self):
        # Two panelists give 3.00 (MAJOR), one gives 5.00 (PASSED). An average
        # (3.67) would say MINOR; the 2-of-3 rule says MAJOR.
        d = scoring.decide([self.score(*ALL(3)), self.score(*ALL(5)), self.score(*ALL(3))])
        self.assertEqual(d.verdict, scoring.MAJOR)
        # Two PASSED (5.00), one FAILED (1.00): average 3.67 would be MINOR; rule says PASSED.
        d = scoring.decide([self.score(*ALL(5)), self.score(*ALL(1)), self.score(*ALL(5))])
        self.assertEqual(d.verdict, scoring.PASSED)

    def test_per_proponent_scores_differ_but_a_b_shared(self):
        # Proponent 1: 5/5 oral, proponent 2: 2/3 oral
        s = self.score(WORKED_GROUP, {5: [5, 2], 6: [5, 3]})
        p1, p2 = s.proponents
        self.assertEqual(p1.sections["A"], p2.sections["A"])
        self.assertEqual(p1.sections["B"], p2.sections["B"])
        self.assertEqual(p1.C, D("1.75"))     # 0.75 + 1.00
        self.assertEqual(p2.C, D("0.90"))     # 0.30 + 0.60
        self.assertEqual(p1.final, D("4.50"))
        self.assertEqual(p2.final, D("3.65"))
        self.assertEqual(s.C, D("1.325"))     # average C
        self.assertEqual(s.final, D("4.075"))
        self.assertEqual(scoring.round2(s.final), D("4.08"))

    def test_partial_ratings_count_missing(self):
        s = self.score({1: 4}, {})
        self.assertEqual(s.A, D("0.80"))
        self.assertEqual(s.missing, 3 + 2 * 2)
        self.assertFalse(s.complete)


class ComputeDefenseTests(TestCase):
    def test_all_three_worked_example(self):
        defense, _, assignments = make_defense()
        for a in assignments:
            rate(a, WORKED_GROUP, WORKED_ORAL)
        result = scoring.compute_defense(defense)
        self.assertTrue(result.complete)
        self.assertEqual([r.score.final for r in result.rows], [D("4.30")] * 3)
        self.assertEqual(result.decision.verdict, scoring.MINOR)
        self.assertEqual(result.decision.group.agreeing, 3)
        self.assertEqual([p.decision.verdict for p in result.decision.proponents],
                         [scoring.MINOR] * 2)

    def test_two_of_three_from_db(self):
        defense, _, (a1, a2, a3) = make_defense()
        rate(a1, WORKED_GROUP, WORKED_ORAL)      # 4.30 MINOR
        rate(a2, *ALL(5))                        # 5.00 PASSED
        rate(a3, *ALL(4))                        # 4.00 MINOR
        d = scoring.compute_defense(defense).decision
        self.assertEqual(d.verdict, scoring.MINOR)
        self.assertEqual(d.group.summary, "2 of 3 panelists")

    def test_each_student_decided_by_two_of_three(self):
        # Same A and B for everyone; oral ratings differ per student.
        defense, _, (a1, a2, a3) = make_defense()
        # A + B = 1.95 + 0.80 = 2.75 on every form.
        # Student 1 gets 5/5 orals from all -> C 1.75, FINAL 4.50 each -> PASSED
        # Student 2: panelists 1 and 2 give 2/2 -> 3.45 MAJOR; panelist 3 gives 4/4 -> 4.15 MINOR
        rate(a1, WORKED_GROUP, {5: [5, 2], 6: [5, 2]})
        rate(a2, WORKED_GROUP, {5: [5, 2], 6: [5, 2]})
        rate(a3, WORKED_GROUP, {5: [5, 4], 6: [5, 4]})
        d = scoring.compute_defense(defense).decision
        p1, p2 = d.proponents
        self.assertEqual([s.final for s in p1.scores], [D("4.50")] * 3)
        self.assertEqual(p1.decision.verdict, scoring.PASSED)
        self.assertEqual([s.final for s in p2.scores], [D("3.45"), D("3.45"), D("4.15")])
        self.assertEqual(p2.decision.verdict, scoring.MAJOR)
        self.assertEqual(p2.decision.agreeing, 2)
        # A and B are shared by both students within each panelist's form
        for row in scoring.compute_defense(defense).rows:
            s1, s2 = row.score.proponents
            self.assertEqual((s1.sections["A"], s1.sections["B"]),
                             (s2.sections["A"], s2.sections["B"]))

    def test_no_decision_until_all_three_submitted(self):
        defense, _, (a1, a2, a3) = make_defense()
        rate(a1, WORKED_GROUP, WORKED_ORAL)
        rate(a2, WORKED_GROUP, WORKED_ORAL)
        result = scoring.compute_defense(defense)
        self.assertIsNone(result.decision)
        self.assertEqual(result.submitted_count, 2)
        self.assertEqual([r.status for r in result.rows],
                         [scoring.SUBMITTED, scoring.SUBMITTED, scoring.NOT_STARTED])
        rate(a3, WORKED_GROUP, WORKED_ORAL, submit=False)
        result = scoring.compute_defense(defense)
        self.assertIsNone(result.decision)
        self.assertEqual(result.rows[2].status, scoring.DRAFT)
        Evaluation.objects.filter(assignment=a3).update(submitted=True)
        self.assertIsNotNone(scoring.compute_defense(defense).decision)

    def test_cutoffs_from_settings(self):
        defense, _, assignments = make_defense()
        for a in assignments:
            rate(a, WORKED_GROUP, WORKED_ORAL)
        s = ScoringSettings.load()
        s.passed_cutoff = D("4.30")
        s.save()
        self.assertEqual(scoring.compute_defense(defense).decision.verdict, scoring.PASSED)


def eval_post(assignment, ratings=None, action="draft", comments=""):
    """Build POST data. ratings: {criterion number: rating or [per proponent]}"""
    data = {"action": action, "comments": comments}
    proponents = list(assignment.defense.proponents.all())
    for c in Criterion.objects.all():
        if ratings is None or c.number not in ratings:
            continue
        r = ratings[c.number]
        if c.per_proponent:
            values = r if isinstance(r, (list, tuple)) else [r] * len(proponents)
            for p, v in zip(proponents, values):
                data[f"c{c.number}_p{p.pk}"] = str(v)
        else:
            data[f"c{c.number}"] = str(r)
    return data


FULL = {**WORKED_GROUP, **WORKED_ORAL}


class AccessTests(TestCase):
    def setUp(self):
        self.defense, self.proponents, self.assignments = make_defense()
        self.outsider = make_user("outsider")
        self.manager = make_user("boss", staff=True)

    def test_panelist_cannot_open_another_panelists_evaluation(self):
        self.client.force_login(self.assignments[0].panelist.user)
        r = self.client.get(reverse("defense:evaluate", args=[self.assignments[1].pk]))
        self.assertEqual(r.status_code, 403)
        r = self.client.post(reverse("defense:evaluate", args=[self.assignments[1].pk]),
                             eval_post(self.assignments[1], FULL, "submit"))
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Evaluation.objects.filter(assignment=self.assignments[1]).exists())

    def test_manager_cannot_fill_someone_elses_evaluation(self):
        self.client.force_login(self.manager)
        r = self.client.get(reverse("defense:evaluate", args=[self.assignments[0].pk]))
        self.assertEqual(r.status_code, 403)

    def test_unassigned_panelist_gets_403(self):
        self.client.force_login(self.outsider)
        for name in ("defense_evaluate", "results", "results_status", "print_results"):
            with self.subTest(view=name):
                r = self.client.get(reverse(f"defense:{name}", args=[self.defense.pk]))
                self.assertEqual(r.status_code, 403)
        r = self.client.get(reverse("defense:print_form", args=[self.assignments[0].pk]))
        self.assertEqual(r.status_code, 403)

    def test_dashboard_lists_only_own_defenses(self):
        make_defense(users=[make_user(u) for u in ("x1", "x2", "x3")])
        self.client.force_login(self.assignments[0].panelist.user)
        r = self.client.get(reverse("defense:dashboard"))
        self.assertEqual([i["defense"] for i in r.context["items"]], [self.defense])
        self.assertContains(r, "Score now")
        self.client.force_login(self.manager)
        r = self.client.get(reverse("defense:dashboard"))
        self.assertEqual(len(r.context["items"]), 2)

    def test_manager_only_pages(self):
        self.client.force_login(self.assignments[0].panelist.user)
        for url in (reverse("defense:defense_create"),
                    reverse("defense:defense_edit", args=[self.defense.pk]),
                    reverse("defense:panelist_list"), reverse("defense:panelist_create"),
                    reverse("defense:scoring_settings")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        r = self.client.post(reverse("defense:evaluation_unlock", args=[self.assignments[0].pk]))
        self.assertEqual(r.status_code, 403)
        r = self.client.post(reverse("defense:defense_toggle", args=[self.defense.pk]))
        self.assertEqual(r.status_code, 403)
        self.client.force_login(self.manager)
        for url in (reverse("defense:defense_create"),
                    reverse("defense:defense_edit", args=[self.defense.pk]),
                    reverse("defense:panelist_list"), reverse("defense:panelist_create"),
                    reverse("defense:scoring_settings")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_login_required(self):
        r = self.client.get(reverse("defense:dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r["Location"])


class EvaluateViewTests(TestCase):
    def setUp(self):
        self.defense, self.proponents, self.assignments = make_defense()
        self.a = self.assignments[0]
        self.url = reverse("defense:evaluate", args=[self.a.pk])
        self.client.force_login(self.a.panelist.user)

    def test_get_renders_rubric(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Functionality &amp; Correctness")
        self.assertContains(r, f'name="c5_p{self.proponents[1].pk}"')
        self.assertContains(r, "CAPSTONE PROJECT AND RESEARCH FINAL DEFENSE FORM")

    def test_draft_accepts_partial_ratings(self):
        r = self.client.post(self.url, eval_post(self.a, {1: 4, 5: [5]}, "draft", "wip"))
        self.assertRedirects(r, self.url)
        ev = Evaluation.objects.get(assignment=self.a)
        self.assertFalse(ev.submitted)
        self.assertEqual(ev.comments, "wip")
        self.assertEqual(ev.group_ratings.count(), 1)
        self.assertEqual(ev.individual_ratings.count(), 1)

    def test_submit_rejected_when_rating_missing(self):
        partial = {k: v for k, v in FULL.items() if k != 6}
        r = self.client.post(self.url, eval_post(self.a, partial, "submit"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Every rating is required")
        ev = Evaluation.objects.get(assignment=self.a)
        self.assertFalse(ev.submitted)                 # rejected...
        self.assertEqual(ev.group_ratings.count(), 4)  # ...but the work is kept as a draft

    def test_submit_rejected_when_one_proponent_unrated(self):
        data = eval_post(self.a, FULL, "submit")
        del data[f"c6_p{self.proponents[1].pk}"]
        self.client.post(self.url, data)
        self.assertFalse(Evaluation.objects.get(assignment=self.a).submitted)

    def test_invalid_rating_value_rejected(self):
        data = eval_post(self.a, FULL, "submit")
        data["c1"] = "7"
        self.client.post(self.url, data)
        self.assertFalse(Evaluation.objects.filter(assignment=self.a, submitted=True).exists())

    def test_submit_then_edit_while_open(self):
        r = self.client.post(self.url, eval_post(self.a, FULL, "submit"))
        self.assertRedirects(r, reverse("defense:results", args=[self.defense.pk]))
        ev = Evaluation.objects.get(assignment=self.a)
        self.assertTrue(ev.submitted)
        self.assertIsNotNone(ev.submitted_at)
        score = scoring.compute_panelist(ev, Criterion.objects.all(), self.proponents)
        self.assertEqual(score.final, D("4.30"))

        # Still editable after submitting: the form offers "Save changes", not drafts.
        r = self.client.get(self.url)
        self.assertContains(r, "Save changes")
        self.assertNotContains(r, 'value="draft"')
        self.assertNotContains(r, "disabled")

        # A complete re-save replaces the scores and stays submitted.
        r = self.client.post(self.url, eval_post(self.a, {**FULL, 1: 5}, "submit", "updated"))
        self.assertRedirects(r, reverse("defense:results", args=[self.defense.pk]))
        ev.refresh_from_db()
        self.assertTrue(ev.submitted)
        self.assertEqual(ev.comments, "updated")
        self.assertEqual(GroupRating.objects.get(evaluation=ev, criterion__number=1).rating, 5)

    def test_submitted_evaluation_never_becomes_incomplete(self):
        self.client.post(self.url, eval_post(self.a, FULL, "submit"))
        ev = Evaluation.objects.get(assignment=self.a)
        # Missing a rating: rejected and nothing changes (no fallback to draft).
        partial = {**{k: v for k, v in FULL.items() if k != 6}, 1: 1}
        r = self.client.post(self.url, eval_post(self.a, partial, "submit"))
        self.assertContains(r, "Every rating is required")
        # A forged "draft" action is treated as a full save, so it is rejected too.
        self.client.post(self.url, eval_post(self.a, {1: 2}, "draft"))
        ev.refresh_from_db()
        self.assertTrue(ev.submitted)
        self.assertEqual(GroupRating.objects.get(evaluation=ev, criterion__number=1).rating, 4)
        self.assertEqual(ev.individual_ratings.count(), 4)

    def test_submitted_evaluation_locked_once_scoring_closed(self):
        self.client.post(self.url, eval_post(self.a, FULL, "submit"))
        self.defense.status = Defense.CLOSED
        self.defense.save()
        self.client.post(self.url, eval_post(self.a, {**FULL, 1: 1}, "submit"))
        ev = Evaluation.objects.get(assignment=self.a)
        self.assertEqual(GroupRating.objects.get(evaluation=ev, criterion__number=1).rating, 4)
        r = self.client.get(self.url)
        self.assertContains(r, "read-only")
        self.assertContains(r, "disabled")

    def test_manager_can_return_submission_to_draft(self):
        self.client.post(self.url, eval_post(self.a, FULL, "submit"))
        self.client.force_login(make_user("boss", staff=True))
        self.client.post(reverse("defense:evaluation_unlock", args=[self.a.pk]))
        self.assertFalse(Evaluation.objects.get(assignment=self.a).submitted)

    def test_closed_defense_rejects_edits(self):
        self.defense.status = Defense.CLOSED
        self.defense.save()
        self.client.post(self.url, eval_post(self.a, FULL, "submit"))
        self.assertFalse(Evaluation.objects.filter(assignment=self.a).exists())

    def test_defense_evaluate_redirects_to_own_form(self):
        r = self.client.get(reverse("defense:defense_evaluate", args=[self.defense.pk]))
        self.assertRedirects(r, self.url)


class ResultsViewTests(TestCase):
    def setUp(self):
        self.defense, self.proponents, self.assignments = make_defense()
        self.url = reverse("defense:results", args=[self.defense.pk])

    def test_no_scores_shown_until_all_submitted(self):
        rate(self.assignments[0], WORKED_GROUP, WORKED_ORAL)
        rate(self.assignments[1], WORKED_GROUP, WORKED_ORAL, submit=False)
        self.client.force_login(self.assignments[0].panelist.user)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["result"].decision)
        self.assertNotContains(r, "4.30")
        self.assertContains(r, "Not started")
        self.assertContains(r, "Draft")
        self.assertContains(r, "1/3 submitted")
        data = self.client.get(reverse("defense:results_status", args=[self.defense.pk])).json()
        self.assertEqual(data["submitted"], 1)
        self.assertFalse(data["complete"])
        self.assertEqual([p["status"] for p in data["panelists"]],
                         ["submitted", "draft", "not_started"])

    def test_results_after_all_submitted(self):
        for a in self.assignments:
            rate(a, WORKED_GROUP, WORKED_ORAL, submit=True)
        for a in self.assignments:
            self.client.force_login(a.panelist.user)
            r = self.client.get(self.url)
            self.assertContains(r, "4.30")
            self.assertContains(r, "PASSED with MINOR REVISIONS")
            self.assertTrue(self.client.get(
                reverse("defense:results_status", args=[self.defense.pk])).json()["complete"])
            self.assertContains(self.client.get(
                reverse("defense:print_results", args=[self.defense.pk])),
                "Signature Over Printed Name", count=3)
            self.assertContains(self.client.get(
                reverse("defense:print_form", args=[a.pk])), "Signature Over Printed Name")


class DefenseFormTests(TestCase):
    def setUp(self):
        self.manager = make_user("boss", staff=True)
        self.users = [make_user(u) for u in ("p1", "p2", "p3", "p4")]
        self.client.force_login(self.manager)

    def post_data(self, panel, names=("Ana", "Ben")):
        data = {"title": "New System", "schedule_date": "2026-11-20", "schedule_time": "09:00",
                "venue": "Room 1", "proponents-TOTAL_FORMS": str(len(names)),
                "proponents-INITIAL_FORMS": "0", "proponents-MIN_NUM_FORMS": "1",
                "proponents-MAX_NUM_FORMS": "8"}
        for i, n in enumerate(names):
            data[f"proponents-{i}-full_name"] = n
        for key, user in zip(("ex1", "ex2", "rc"), panel):
            data[key] = str(user.panelist.pk)
        return data

    def test_create_defense(self):
        r = self.client.post(reverse("defense:defense_create"), self.post_data(self.users[:3]))
        self.assertRedirects(r, reverse("defense:dashboard"))
        d = Defense.objects.get()
        self.assertEqual([p.full_name for p in d.proponents.all()], ["Ana", "Ben"])
        self.assertEqual(sorted(a.role for a in d.assignments.all()), ["EX1", "EX2", "RC"])

    def test_no_weight_fields_on_panel_form(self):
        r = self.client.get(reverse("defense:defense_create"))
        self.assertNotContains(r, "_weight")

    def test_three_different_panelists(self):
        r = self.client.post(reverse("defense:defense_create"),
                             self.post_data([self.users[0], self.users[0], self.users[1]]))
        self.assertContains(r, "three different panelists")
        self.assertFalse(Defense.objects.exists())

    def test_at_least_one_proponent(self):
        r = self.client.post(reverse("defense:defense_create"),
                             self.post_data(self.users[:3], names=("",)))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Defense.objects.exists())

    def test_reassigning_role_deletes_old_evaluation(self):
        defense, _, assignments = make_defense(users=self.users[:3])
        for a in assignments:
            rate(a, WORKED_GROUP, WORKED_ORAL)
        data = self.post_data([self.users[0], self.users[1], self.users[3]])
        data["proponents-INITIAL_FORMS"] = "2"
        for i, p in enumerate(defense.proponents.all()):
            data[f"proponents-{i}-id"] = str(p.pk)
            data[f"proponents-{i}-full_name"] = p.full_name
        r = self.client.post(reverse("defense:defense_edit", args=[defense.pk]), data)
        self.assertRedirects(r, reverse("defense:dashboard"))
        rc = PanelAssignment.objects.get(defense=defense, role=PanelAssignment.RC)
        self.assertEqual(rc.panelist, self.users[3].panelist)
        self.assertFalse(Evaluation.objects.filter(assignment=rc).exists())
        self.assertEqual(Evaluation.objects.filter(assignment__defense=defense).count(), 2)
        self.assertFalse(Evaluation.objects.filter(
            assignment__panelist=self.users[2].panelist).exists())

    def test_swapping_examiners_is_allowed(self):
        defense, _, _ = make_defense(users=self.users[:3])
        data = self.post_data([self.users[1], self.users[0], self.users[2]])
        data["proponents-INITIAL_FORMS"] = "2"
        for i, p in enumerate(defense.proponents.all()):
            data[f"proponents-{i}-id"] = str(p.pk)
            data[f"proponents-{i}-full_name"] = p.full_name
        r = self.client.post(reverse("defense:defense_edit", args=[defense.pk]), data)
        self.assertRedirects(r, reverse("defense:dashboard"))
        ex1 = PanelAssignment.objects.get(defense=defense, role=PanelAssignment.EX1)
        self.assertEqual(ex1.panelist, self.users[1].panelist)

    def test_manager_deletes_defense_and_all_its_scores(self):
        defense, _, assignments = make_defense(users=self.users[:3])
        for a in assignments:
            rate(a, WORKED_GROUP, WORKED_ORAL)
        keep, _, _ = make_defense(users=[make_user(u) for u in ("k1", "k2", "k3")])
        r = self.client.post(reverse("defense:defense_delete", args=[defense.pk]))
        self.assertRedirects(r, reverse("defense:dashboard"))
        self.assertFalse(Defense.objects.filter(pk=defense.pk).exists())
        self.assertFalse(Proponent.objects.filter(defense_id=defense.pk).exists())
        self.assertFalse(PanelAssignment.objects.filter(defense_id=defense.pk).exists())
        self.assertEqual(Evaluation.objects.count(), 0)
        self.assertEqual(GroupRating.objects.count() + IndividualRating.objects.count(), 0)
        self.assertTrue(Defense.objects.filter(pk=keep.pk).exists())
        # Panelist accounts are kept, and can now be deleted if wanted.
        self.assertTrue(User.objects.filter(pk=self.users[0].pk).exists())

    def test_delete_defense_requires_post_and_manager(self):
        defense, _, assignments = make_defense(users=self.users[:3])
        r = self.client.get(reverse("defense:defense_delete", args=[defense.pk]))
        self.assertEqual(r.status_code, 405)
        self.client.force_login(self.users[0])  # a panelist on this defense
        r = self.client.post(reverse("defense:defense_delete", args=[defense.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Defense.objects.filter(pk=defense.pk).exists())

    def test_adding_proponent_reopens_submitted_evaluations(self):
        defense, props, assignments = make_defense(users=self.users[:3])
        for a in assignments:
            rate(a, WORKED_GROUP, WORKED_ORAL)
        data = self.post_data(self.users[:3], names=("A", "B", "Carla"))
        data["proponents-INITIAL_FORMS"] = "2"
        for i, p in enumerate(props):
            data[f"proponents-{i}-id"] = str(p.pk)
        self.client.post(reverse("defense:defense_edit", args=[defense.pk]), data)
        self.assertEqual(defense.proponents.count(), 3)
        self.assertFalse(Evaluation.objects.filter(submitted=True).exists())
        self.assertIsNone(scoring.compute_defense(defense).decision)


class SettingsAndAccountsTests(TestCase):
    def setUp(self):
        self.manager = make_user("boss", staff=True)
        self.client.force_login(self.manager)
        self.url = reverse("defense:scoring_settings")

    def settings_data(self, **kw):
        data = {"passed_cutoff": "4.50", "minor_cutoff": "3.50", "major_cutoff": "2.50"}
        data.update(kw)
        return data

    def test_settings_validation(self):
        r = self.client.post(self.url, self.settings_data(minor_cutoff="4.60"))
        self.assertContains(r, "strictly decrease")
        r = self.client.post(self.url, self.settings_data(passed_cutoff="5.50"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ScoringSettings.load().passed_cutoff, D("4.50"))
        r = self.client.post(self.url, self.settings_data(passed_cutoff="4.40"))
        self.assertRedirects(r, self.url)
        self.assertEqual(ScoringSettings.load().passed_cutoff, D("4.40"))

    def test_create_panelist_account(self):
        r = self.client.post(reverse("defense:panelist_create"), {
            "prefix": "Engr.", "first_name": "Jelmar L.", "last_name": "Villaruel",
            "suffix": "LPT", "username": "jvillaruel", "password": "secret99",
            "can_manage": "on"})
        self.assertRedirects(r, reverse("defense:panelist_list"))
        u = User.objects.get(username="jvillaruel")
        self.assertTrue(u.is_staff)
        self.assertTrue(u.check_password("secret99"))
        self.assertEqual(u.panelist.display_name, "Engr. Jelmar L. Villaruel, LPT")

    def test_delete_panelist_not_on_any_panel(self):
        u = make_user("spare")
        r = self.client.post(reverse("defense:panelist_delete", args=[u.panelist.pk]))
        self.assertRedirects(r, reverse("defense:panelist_list"))
        self.assertFalse(User.objects.filter(username="spare").exists())
        self.assertFalse(Panelist.objects.filter(pk=u.panelist.pk).exists())

    def test_cannot_delete_panelist_on_a_panel(self):
        defense, _, assignments = make_defense()
        rate(assignments[0], WORKED_GROUP, WORKED_ORAL)
        target = assignments[0].panelist
        r = self.client.post(reverse("defense:panelist_delete", args=[target.pk]), follow=True)
        self.assertContains(r, "is on the panel of")
        self.assertTrue(User.objects.filter(pk=target.user_id).exists())
        self.assertTrue(Evaluation.objects.filter(assignment=assignments[0]).exists())

    def test_cannot_delete_self_or_by_get(self):
        r = self.client.post(reverse("defense:panelist_delete", args=[self.manager.panelist.pk]),
                             follow=True)
        self.assertContains(r, "cannot delete your own account")
        self.assertTrue(User.objects.filter(pk=self.manager.pk).exists())
        u = make_user("spare")
        r = self.client.get(reverse("defense:panelist_delete", args=[u.panelist.pk]))
        self.assertEqual(r.status_code, 405)
        self.assertTrue(User.objects.filter(username="spare").exists())

    def test_manager_cannot_delete_superuser(self):
        su = User.objects.create_superuser("root", password="pw123456")
        self.client.post(reverse("defense:panelist_delete", args=[su.panelist.pk]))
        self.assertTrue(User.objects.filter(username="root").exists())

    def test_panelist_cannot_delete_accounts(self):
        u = make_user("spare")
        self.client.force_login(make_user("plain"))
        r = self.client.post(reverse("defense:panelist_delete", args=[u.panelist.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(User.objects.filter(username="spare").exists())

    def test_every_user_gets_a_panelist_profile(self):
        self.assertTrue(Panelist.objects.filter(user=self.manager).exists())


class DemoCommandTests(TestCase):
    def test_load_demo_reproduces_worked_example(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("load_demo", stdout=StringIO())
        call_command("load_demo", stdout=StringIO())  # safe to re-run
        defense = Defense.objects.get()
        result = scoring.compute_defense(defense)
        self.assertEqual([r.score.final for r in result.rows], [D("4.30")] * 3)
        self.assertEqual(result.decision.verdict, scoring.MINOR)
        for username in ("examiner1", "examiner2", "coordinator"):
            self.assertTrue(self.client.login(username=username, password="demo1234"))
            r = self.client.get(reverse("defense:results", args=[defense.pk]))
            self.assertContains(r, "4.30")
            self.assertContains(r, "PASSED with MINOR REVISIONS")
