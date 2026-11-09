"""
Score computation (see AGENT_PROMPT.md, section 4).

All math lives here, as functions over Decimal (never float):

    score_ratings(criteria, proponents, group, individual) -> PanelistScore   (pure)
    compute_panelist(evaluation, criteria, proponents)     -> PanelistScore   (loads ratings)
    get_verdict(score, cutoffs)                            -> PASSED / MINOR / MAJOR / FAILED
    panel_decision(verdicts)                               -> Decision        (2-of-3 rule)
    compute_defense(defense)                               -> DefenseResult   (decision once all 3 submitted)

Per panelist (matches the paper form):
    A = sum r*w of criteria 1-3, B = r*w of criterion 4 (rated once for the group)
    C = sum r*w of criteria 5-6, rated per proponent, so each proponent has their own C
    FINAL(proponent) = A + B + C(proponent);  Group FINAL = A + B + average C

Each panelist scores individually; there are no panel weights. A panelist's
FINAL is rounded to 2 decimals (ROUND_HALF_UP) and mapped to a verdict:
    PASSED >= 4.50, MINOR >= 3.50, MAJOR >= 2.50, else FAILED   (editable cutoffs)

Panel decision (all 3 submitted): the verdict that at least 2 of the 3
panelists agree on. If all three differ, the middle verdict is used and
flagged. The same rule is applied per proponent, using each panelist's
FINAL for that proponent.

static/js/evaluate.js mirrors score_ratings() for the live subtotals; the
server always recomputes from the saved ratings.
"""
from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
CENT = Decimal("0.01")
SECTIONS = ("A", "B", "C")

# ---------------------------------------------------------------- verdicts --

PASSED = "PASSED"
MINOR = "MINOR"
MAJOR = "MAJOR"
FAILED = "FAILED"
VERDICT_ORDER = (PASSED, MINOR, MAJOR, FAILED)
VERDICT_LABELS = {
    PASSED: "PASSED",
    MINOR: "PASSED with MINOR REVISIONS",
    MAJOR: "PASSED with MAJOR REVISIONS",
    FAILED: "FAILED",
}
VERDICT_NOTES = {
    PASSED: "Approved. Submit final hardbound.",
    MINOR: "Must revise the system/manuscript. To be checked by Adviser/Panel.",
    MAJOR: "Not yet passed. Must fix major bugs and re-defend.",
    FAILED: "Must re-enroll in Capstone 2.",
}
DEFAULT_CUTOFFS = (Decimal("4.50"), Decimal("3.50"), Decimal("2.50"))

# Evaluation status
NOT_STARTED = "not_started"
DRAFT = "draft"
SUBMITTED = "submitted"
STATUS_LABELS = {NOT_STARTED: "Not started", DRAFT: "Draft", SUBMITTED: "Submitted"}

REQUIRED_PANELISTS = 3


def to_decimal(value):
    """Convert int/str/Decimal to Decimal. Floats are refused on purpose."""
    if isinstance(value, float):
        raise TypeError("Scores must not be floats; pass a Decimal, int or str.")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round2(value):
    """Round to 2 decimals, half up (4.305 -> 4.31)."""
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def get_verdict(score, cutoffs=None):
    """Verdict code for a score. The score is rounded to 2 decimals first;
    each cutoff is an inclusive lower bound (>=)."""
    passed, minor, major = (to_decimal(c) for c in (cutoffs or DEFAULT_CUTOFFS))
    s = round2(score)
    if s >= passed:
        return PASSED
    if s >= minor:
        return MINOR
    if s >= major:
        return MAJOR
    return FAILED


def verdict_label(code):
    return VERDICT_LABELS.get(code, "")


def verdict_bands(cutoffs=None):
    """The 4 decision boxes with their score ranges, for display.

    Scores are rounded to 2 decimals, so a band ends 0.01 below the next cutoff.
    """
    passed, minor, major = (round2(c) for c in (cutoffs or DEFAULT_CUTOFFS))
    step = CENT
    ranges = {
        PASSED: f"{passed} – 5.00",
        MINOR: f"{minor} – {passed - step}",
        MAJOR: f"{major} – {minor - step}",
        FAILED: f"below {major}",
    }
    return [{"code": v, "label": VERDICT_LABELS[v], "note": VERDICT_NOTES[v],
             "range": ranges[v]} for v in VERDICT_ORDER]


# ------------------------------------------------------- per-panelist math --

def weighted_score(rating, weight):
    """r x w for one criterion."""
    return to_decimal(rating) * to_decimal(weight)


@dataclass
class ProponentScore:
    proponent: object
    sections: dict          # {"A": Decimal, "B": Decimal, "C": Decimal}
    final: Decimal
    cutoffs: tuple = DEFAULT_CUTOFFS

    @property
    def C(self):
        return self.sections["C"]

    @property
    def verdict(self):
        return get_verdict(self.final, self.cutoffs)

    @property
    def verdict_label(self):
        return verdict_label(self.verdict)

    @property
    def proponent_id(self):
        return getattr(self.proponent, "pk", self.proponent)


@dataclass
class PanelistScore:
    A: Decimal
    B: Decimal
    C: Decimal              # average C across proponents (the single C on paper)
    final: Decimal          # group FINAL = A + B + average C
    proponents: list        # [ProponentScore], in proponent order
    missing: int            # number of ratings not yet given
    cutoffs: tuple = DEFAULT_CUTOFFS

    @property
    def complete(self):
        return self.missing == 0

    @property
    def verdict(self):
        return get_verdict(self.final, self.cutoffs)

    @property
    def verdict_label(self):
        return verdict_label(self.verdict)

    def for_proponent(self, proponent):
        pid = getattr(proponent, "pk", proponent)
        for p in self.proponents:
            if p.proponent_id == pid:
                return p
        return None


def score_ratings(criteria, proponents, group_ratings, individual_ratings,
                  cutoffs=DEFAULT_CUTOFFS):
    """Pure computation of one panelist's scores.

    criteria:           objects with .pk, .section, .weight, .per_proponent
    proponents:         objects with .pk (or plain ids)
    group_ratings:      {criterion_pk: rating}
    individual_ratings: {(criterion_pk, proponent_pk): rating}

    Missing ratings count as 0 (so a draft gets partial subtotals) and are
    counted in .missing.
    """
    criteria = list(criteria)
    proponents = list(proponents)
    pids = [getattr(p, "pk", p) for p in proponents]
    missing = 0

    shared = {s: ZERO for s in SECTIONS}      # rated once for the group
    for c in criteria:
        if c.per_proponent:
            continue
        r = group_ratings.get(c.pk)
        if r is None:
            missing += 1
        else:
            shared[c.section] += weighted_score(r, c.weight)

    prop_scores = []
    for proponent, pid in zip(proponents, pids):
        sections = dict(shared)
        for c in criteria:
            if not c.per_proponent:
                continue
            r = individual_ratings.get((c.pk, pid))
            if r is None:
                missing += 1
            else:
                sections[c.section] += weighted_score(r, c.weight)
        prop_scores.append(ProponentScore(
            proponent=proponent, sections=sections,
            final=sum(sections.values(), ZERO), cutoffs=tuple(cutoffs)))

    if prop_scores:
        n = len(prop_scores)
        group = {s: sum((p.sections[s] for p in prop_scores), ZERO) / n for s in SECTIONS}
    else:
        group = dict(shared)

    return PanelistScore(
        A=group["A"], B=group["B"], C=group["C"],
        final=group["A"] + group["B"] + group["C"],
        proponents=prop_scores, missing=missing, cutoffs=tuple(cutoffs))


def rating_lines(criteria, proponents, group_ratings, individual_ratings):
    """Per-criterion rows for printed forms.

    [{"criterion", "rating", "weighted"}]                  for group criteria
    [{"criterion", "per_proponent": [{"proponent", "rating", "weighted"}]}]
    (rating/weighted are None when not yet rated)
    """
    lines = []
    for c in criteria:
        if c.per_proponent:
            cells = []
            for p in proponents:
                r = individual_ratings.get((c.pk, getattr(p, "pk", p)))
                cells.append({"proponent": p, "rating": r,
                              "weighted": None if r is None else weighted_score(r, c.weight)})
            lines.append({"criterion": c, "per_proponent": cells})
        else:
            r = group_ratings.get(c.pk)
            lines.append({"criterion": c, "rating": r,
                          "weighted": None if r is None else weighted_score(r, c.weight)})
    return lines


def load_ratings(evaluation):
    group = {g.criterion_id: g.rating for g in evaluation.group_ratings.all()}
    individual = {(i.criterion_id, i.proponent_id): i.rating
                  for i in evaluation.individual_ratings.all()}
    return group, individual


def compute_panelist(evaluation, criteria, proponents, cutoffs=DEFAULT_CUTOFFS):
    """Scores for one Evaluation (missing ratings count as 0)."""
    group, individual = load_ratings(evaluation)
    return score_ratings(criteria, proponents, group, individual, cutoffs)


def active_criteria():
    from .models import Criterion

    return list(Criterion.objects.filter(is_active=True).order_by("number"))


def current_cutoffs():
    from .models import ScoringSettings

    return ScoringSettings.load().cutoffs


def evaluation_status(evaluation):
    if evaluation is None:
        return NOT_STARTED
    return SUBMITTED if evaluation.submitted else DRAFT


# ---------------------------------------------------------- panel decision --

@dataclass
class Decision:
    verdict: str
    verdicts: list                # each panelist's verdict, in panel order
    agreeing: int                 # how many panelists gave this verdict

    @property
    def majority(self):
        return self.agreeing * 2 > len(self.verdicts)

    @property
    def verdict_label(self):
        return verdict_label(self.verdict)

    @property
    def summary(self):
        if self.majority:
            return f"{self.agreeing} of {len(self.verdicts)} panelists"
        return "No 2-of-3 agreement: middle result used"


def panel_decision(verdicts):
    """The verdict at least 2 of the 3 panelists agree on.

    With no majority (all different), the middle verdict by severity is used
    and Decision.majority is False so the page can flag it. For 3 panelists
    this is the median verdict, which equals the majority whenever 2 agree.
    """
    verdicts = list(verdicts)
    if not verdicts:
        raise ValueError("panel_decision() needs at least one verdict")
    counts = Counter(verdicts)
    code, n = counts.most_common(1)[0]
    if n * 2 > len(verdicts):
        return Decision(verdict=code, verdicts=verdicts, agreeing=n)
    ordered = sorted(verdicts, key=VERDICT_ORDER.index)
    middle = ordered[len(ordered) // 2]
    return Decision(verdict=middle, verdicts=verdicts, agreeing=counts[middle])


@dataclass
class PanelRow:
    assignment: object
    evaluation: object            # or None
    status: str
    score: PanelistScore = None   # None when not started

    @property
    def status_label(self):
        return STATUS_LABELS[self.status]

    @property
    def submitted(self):
        return self.status == SUBMITTED


@dataclass
class ProponentDecision:
    proponent: object
    scores: list                  # [ProponentScore], one per panelist, in panel order
    decision: Decision


@dataclass
class PanelResult:
    group: Decision               # from each panelist's group FINAL (A + B + average C)
    proponents: list              # [ProponentDecision]

    @property
    def verdict(self):
        return self.group.verdict

    @property
    def verdict_label(self):
        return self.group.verdict_label

    @property
    def has_split(self):
        """True when the group or any student had no 2-of-3 agreement."""
        return not self.group.majority or any(not p.decision.majority for p in self.proponents)


@dataclass
class DefenseResult:
    defense: object
    rows: list                    # [PanelRow] in role order EX1, EX2, RC
    proponents: list
    criteria: list
    cutoffs: tuple
    decision: PanelResult = None
    notes: list = field(default_factory=list)

    @property
    def submitted_count(self):
        return sum(1 for r in self.rows if r.submitted)

    @property
    def total(self):
        return REQUIRED_PANELISTS

    @property
    def complete(self):
        return self.decision is not None


def decide(scores):
    """Panel decision from the panelists' PanelistScores (all complete)."""
    scores = list(scores)
    group = panel_decision(s.verdict for s in scores)
    proponents = []
    for i, ps in enumerate(scores[0].proponents):
        cells = [s.proponents[i] for s in scores]
        proponents.append(ProponentDecision(
            proponent=ps.proponent, scores=cells,
            decision=panel_decision(c.verdict for c in cells)))
    return PanelResult(group=group, proponents=proponents)


def defense_progress(defense):
    """[(assignment, status)] in role order (cheap, no score math)."""
    from .models import Evaluation

    out = []
    for a in sorted(defense.assignments.all(), key=lambda a: a.role_order):
        try:
            ev = a.evaluation
        except Evaluation.DoesNotExist:
            ev = None
        out.append((a, evaluation_status(ev)))
    return out


def compute_defense(defense, criteria=None, cutoffs=None):
    """Per-panelist scores plus the panel decision.

    .decision stays None until all 3 roles are assigned and all 3
    evaluations are submitted with every rating present.
    """
    from .models import Evaluation, PanelAssignment

    criteria = active_criteria() if criteria is None else list(criteria)
    cutoffs = current_cutoffs() if cutoffs is None else tuple(cutoffs)
    proponents = list(defense.proponents.all())

    rows = []
    for a in sorted(defense.assignments.select_related("panelist__user"),
                    key=lambda a: a.role_order):
        try:
            ev = a.evaluation
        except Evaluation.DoesNotExist:
            ev = None
        score = compute_panelist(ev, criteria, proponents, cutoffs) if ev else None
        rows.append(PanelRow(assignment=a, evaluation=ev,
                             status=evaluation_status(ev), score=score))

    result = DefenseResult(defense=defense, rows=rows, proponents=proponents,
                           criteria=criteria, cutoffs=cutoffs)

    roles = {r.assignment.role for r in rows}
    if roles != set(PanelAssignment.ROLES) or not proponents:
        return result
    if not all(r.submitted for r in rows):
        return result
    if any(not r.score.complete for r in rows):
        result.notes.append(
            "A submitted evaluation is missing ratings (the rubric or proponents changed "
            "after submission). Unlock it so the panelist can complete it.")
        return result

    result.decision = decide(r.score for r in rows)
    return result
