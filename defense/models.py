"""
Data models (see AGENT_PROMPT.md, section 5).

    ScoringSettings   single row: decision cutoffs
    Criterion         rubric rows 1-6, seeded from docs/rubric.md
    Panelist          OneToOne to auth User: prefix (Engr.), suffix (LPT, CCpE)
    Defense           project title, schedule date/time, venue, status (open/closed)
    Proponent         FK Defense, full name, order
    PanelAssignment   FK Defense + Panelist, role (EX1 / EX2 / RC)
    Evaluation        OneToOne PanelAssignment, comments, submitted, submitted_at
    GroupRating       Evaluation x Criterion (sections A, B) -> rating 1-5
    IndividualRating  Evaluation x Criterion x Proponent (section C) -> rating 1-5

All score math lives in defense/scoring.py.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

RATING_VALIDATORS = [MinValueValidator(1), MaxValueValidator(5)]

# 5-point scale, worded as on the paper form.
RATING_LABELS = {5: "Excellence", 4: "Very Good", 3: "Good", 2: "Fair", 1: "Poor"}


class ScoringSettings(models.Model):
    """Single-row table of the decision cutoffs. Use ScoringSettings.load()."""

    passed_cutoff = models.DecimalField(
        "PASSED at or above", max_digits=3, decimal_places=2, default=Decimal("4.50"))
    minor_cutoff = models.DecimalField(
        "PASSED with MINOR REVISIONS at or above", max_digits=3, decimal_places=2,
        default=Decimal("3.50"))
    major_cutoff = models.DecimalField(
        "PASSED with MAJOR REVISIONS at or above", max_digits=3, decimal_places=2,
        default=Decimal("2.50"))

    class Meta:
        verbose_name = "scoring settings"
        verbose_name_plural = "scoring settings"

    def __str__(self):
        return "Scoring settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # the single row is never deleted

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def cutoffs(self):
        return (self.passed_cutoff, self.minor_cutoff, self.major_cutoff)


class Criterion(models.Model):
    SECTION_CHOICES = [
        ("A", "A. The System (Project Output)"),
        ("B", "B. The Manuscript (Final Document – Chapters 1-5)"),
        ("C", "C. The Oral Defense (Presentation)"),
    ]

    number = models.PositiveSmallIntegerField(
        unique=True, validators=[MinValueValidator(1), MaxValueValidator(6)])
    section = models.CharField(max_length=1, choices=SECTION_CHOICES)
    name = models.CharField(max_length=120)
    guide_question = models.TextField(blank=True)
    weight = models.DecimalField(
        max_digits=4, decimal_places=3, help_text="Fraction, e.g. 0.20 for 20%.")
    per_proponent = models.BooleanField(
        default=False, help_text="Rated separately for each proponent (oral defense).")
    desc_5 = models.TextField("5 – Excellence", blank=True)
    desc_4 = models.TextField("4 – Very Good", blank=True)
    desc_3 = models.TextField("3 – Good", blank=True)
    desc_2 = models.TextField("2 – Fair", blank=True)
    desc_1 = models.TextField("1 – Poor", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["number"]
        verbose_name_plural = "criteria"

    def __str__(self):
        return f"{self.number}. {self.name}"

    @property
    def weight_percent(self):
        return (self.weight * 100).normalize()

    @property
    def descriptors(self):
        """[(5, text), (4, text), ... (1, text)]"""
        return [(n, getattr(self, f"desc_{n}")) for n in (5, 4, 3, 2, 1)]

    @property
    def scale(self):
        """[{"n": 5, "label": "Excellence", "text": ...}, ... down to 1]"""
        return [{"n": n, "label": RATING_LABELS[n], "text": text}
                for n, text in self.descriptors]


class Panelist(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="panelist")
    prefix = models.CharField(max_length=20, blank=True, help_text="e.g. Engr., Dr.")
    suffix = models.CharField(max_length=40, blank=True, help_text="e.g. LPT, CCpE")

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        """e.g. "Engr. Jelmar L. Villaruel, LPT"."""
        full = " ".join(p for p in (self.user.first_name, self.user.last_name) if p).strip()
        full = full or self.user.username
        if self.prefix:
            full = f"{self.prefix} {full}"
        if self.suffix:
            full = f"{full}, {self.suffix}"
        return full


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_panelist_profile(sender, instance, created, raw=False, **kwargs):
    """Every user (including a createsuperuser admin) can be put on a panel."""
    if created and not raw:
        Panelist.objects.get_or_create(user=instance)


class Defense(models.Model):
    OPEN = "open"
    CLOSED = "closed"
    STATUS_CHOICES = [(OPEN, "Open"), (CLOSED, "Closed")]

    title = models.CharField("Project title", max_length=300)
    schedule_date = models.DateField()
    schedule_time = models.TimeField(null=True, blank=True)
    venue = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-schedule_date", "-schedule_time", "-pk"]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status == self.OPEN


class Proponent(models.Model):
    defense = models.ForeignKey(Defense, on_delete=models.CASCADE, related_name="proponents")
    full_name = models.CharField(max_length=150)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.full_name


class PanelAssignment(models.Model):
    EX1 = "EX1"
    EX2 = "EX2"
    RC = "RC"
    ROLE_CHOICES = [(EX1, "Examiner 1"), (EX2, "Examiner 2"), (RC, "Research Coordinator")]
    ROLES = [EX1, EX2, RC]

    defense = models.ForeignKey(Defense, on_delete=models.CASCADE, related_name="assignments")
    panelist = models.ForeignKey(Panelist, on_delete=models.PROTECT, related_name="assignments")
    role = models.CharField(max_length=3, choices=ROLE_CHOICES)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["defense", "role"], name="uniq_defense_role"),
            models.UniqueConstraint(fields=["defense", "panelist"], name="uniq_defense_panelist"),
        ]

    def __str__(self):
        return f"{self.defense} — {self.get_role_display()}: {self.panelist}"

    @property
    def role_order(self):
        return self.ROLES.index(self.role)


class Evaluation(models.Model):
    assignment = models.OneToOneField(
        PanelAssignment, on_delete=models.CASCADE, related_name="evaluation")
    comments = models.TextField("Required Revisions / Comments", blank=True)
    submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Evaluation by {self.assignment.panelist} ({self.assignment.get_role_display()})"


class GroupRating(models.Model):
    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="group_ratings")
    criterion = models.ForeignKey(Criterion, on_delete=models.PROTECT)
    rating = models.PositiveSmallIntegerField(validators=RATING_VALIDATORS)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["evaluation", "criterion"],
                                    name="uniq_group_rating"),
        ]

    def __str__(self):
        return f"{self.criterion.number}: {self.rating}"


class IndividualRating(models.Model):
    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="individual_ratings")
    criterion = models.ForeignKey(Criterion, on_delete=models.PROTECT)
    proponent = models.ForeignKey(Proponent, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(validators=RATING_VALIDATORS)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["evaluation", "criterion", "proponent"],
                                    name="uniq_individual_rating"),
        ]

    def __str__(self):
        return f"{self.criterion.number} / {self.proponent}: {self.rating}"
