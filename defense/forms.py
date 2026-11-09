"""
Forms (see AGENT_PROMPT.md, section 6).

    DefenseForm          title, schedule_date, schedule_time, venue
    ProponentFormSet     inline formset of proponent names (1-8)
    PanelForm            Examiner 1, Examiner 2, Research Coordinator (three different people)
    EvaluationForm       one panelist's 1-5 ratings + comments (draft or submit)
    PanelistForm         create/edit panelist accounts
    ScoringSettingsForm  decision cutoffs
"""
from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q

from .models import Defense, PanelAssignment, Panelist, Proponent, ScoringSettings

MAX_PROPONENTS = 8


class DefenseForm(forms.ModelForm):
    class Meta:
        model = Defense
        fields = ["title", "schedule_date", "schedule_time", "venue"]
        widgets = {
            "title": forms.Textarea(attrs={"rows": 2}),
            "schedule_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "schedule_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }


class BaseProponentFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        names = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            name = (form.cleaned_data.get("full_name") or "").strip().lower()
            if name in names:
                raise forms.ValidationError("Each proponent may be listed only once.")
            names.append(name)


ProponentFormSet = forms.inlineformset_factory(
    Defense, Proponent, formset=BaseProponentFormSet,
    fields=["full_name"], labels={"full_name": "Full name"},
    extra=0, min_num=1, max_num=MAX_PROPONENTS,
    validate_min=True, validate_max=True, can_delete=True,
)


class PanelistChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.display_name


class PanelForm(forms.Form):
    """Three role dropdowns. Every panelist scores on their own; there are no
    panel weights (the decision is the 2-of-3 rule in scoring.py)."""

    ROLE_FIELDS = [
        (PanelAssignment.EX1, "ex1", "Examiner 1"),
        (PanelAssignment.EX2, "ex2", "Examiner 2"),
        (PanelAssignment.RC, "rc", "Research Coordinator"),
    ]

    def __init__(self, *args, defense=None, **kwargs):
        super().__init__(*args, **kwargs)
        existing = {}
        if defense is not None and defense.pk:
            existing = {a.role: a for a in defense.assignments.all()}
        # Active accounts, plus anyone already on this panel (even if since deactivated).
        queryset = Panelist.objects.filter(
            Q(user__is_active=True) | Q(pk__in=[a.panelist_id for a in existing.values()])
        ).select_related("user")
        for role, key, label in self.ROLE_FIELDS:
            a = existing.get(role)
            self.fields[key] = PanelistChoiceField(
                queryset=queryset, label=label, empty_label="— select —",
                initial=a.panelist_id if a else None)

    def role_rows(self):
        """[(label, panelist field)] for the template."""
        return [(label, self[key]) for _, key, label in self.ROLE_FIELDS]

    def clean(self):
        data = super().clean()
        chosen = [data.get(key) for _, key, _ in self.ROLE_FIELDS]
        if all(chosen) and len({p.pk for p in chosen}) != 3:
            raise forms.ValidationError("Choose three different panelists.")
        return data

    def assignments(self):
        """{role: panelist} from cleaned data."""
        return {role: self.cleaned_data[key] for role, key, _ in self.ROLE_FIELDS}


class EvaluationForm(forms.Form):
    """Ratings for one panelist.

    Field names: ``c<criterion number>`` for group criteria and
    ``c<number>_p<proponent pk>`` for per-proponent criteria. Every rating is
    optional for a draft; submit=True makes them all required.
    """

    RATING_CHOICES = [(str(n), str(n)) for n in (5, 4, 3, 2, 1)]

    comments = forms.CharField(
        label="Required Revisions / Comments", required=False,
        widget=forms.Textarea(attrs={"rows": 6}))

    def __init__(self, *args, criteria, proponents, submit=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.criteria = list(criteria)
        self.proponents = list(proponents)
        self.submit = submit
        for c in self.criteria:
            for name, label in self._cells(c):
                self.fields[name] = forms.TypedChoiceField(
                    label=label, choices=self.RATING_CHOICES, coerce=int,
                    required=False, empty_value=None, widget=forms.RadioSelect)

    @staticmethod
    def group_field(criterion):
        return f"c{criterion.number}"

    @staticmethod
    def individual_field(criterion, proponent):
        return f"c{criterion.number}_p{proponent.pk}"

    def _cells(self, criterion):
        if criterion.per_proponent:
            return [(self.individual_field(criterion, p), f"{criterion} — {p.full_name}")
                    for p in self.proponents]
        return [(self.group_field(criterion), str(criterion))]

    @classmethod
    def initial_from(cls, evaluation, criteria, proponents):
        if evaluation is None:
            return {}
        by_pk = {c.pk: c for c in criteria}
        props = {p.pk: p for p in proponents}
        initial = {"comments": evaluation.comments}
        for g in evaluation.group_ratings.all():
            if g.criterion_id in by_pk:
                initial[cls.group_field(by_pk[g.criterion_id])] = str(g.rating)
        for i in evaluation.individual_ratings.all():
            if i.criterion_id in by_pk and i.proponent_id in props:
                initial[cls.individual_field(by_pk[i.criterion_id], props[i.proponent_id])] = \
                    str(i.rating)
        return initial

    def clean(self):
        data = super().clean()
        if self.submit:
            missing = [self.fields[name].label for c in self.criteria
                       for name, _ in self._cells(c) if data.get(name) is None]
            if missing:
                raise forms.ValidationError(
                    "Every rating is required before submitting. Missing: " + "; ".join(missing))
        return data

    def ratings(self):
        """(group, individual) from cleaned data, missing ratings left out.

        group: {criterion: rating}; individual: {(criterion, proponent): rating}
        """
        group, individual = {}, {}
        for c in self.criteria:
            if c.per_proponent:
                for p in self.proponents:
                    v = self.cleaned_data.get(self.individual_field(c, p))
                    if v is not None:
                        individual[(c, p)] = v
            else:
                v = self.cleaned_data.get(self.group_field(c))
                if v is not None:
                    group[c] = v
        return group, individual

    def value_of(self, name):
        """Current value as a string (bound data first, then initial)."""
        if self.is_bound:
            return self.data.get(name) or ""
        return str(self.initial.get(name) or "")

    def sections(self):
        """Rubric grouped by section for the template.

        [{"code", "label", "weight", "criteria": [{"criterion", "rows": [
            {"label", "name", "value", "proponent"}]}]}]
        """
        from .models import Criterion

        labels = dict(Criterion.SECTION_CHOICES)
        out = []
        for c in self.criteria:
            if not out or out[-1]["code"] != c.section:
                out.append({"code": c.section, "label": labels.get(c.section, c.section),
                            "weight": Decimal(0), "criteria": []})
            sec = out[-1]
            sec["weight"] += c.weight
            rows = []
            for name, _ in self._cells(c):
                prop = None
                if c.per_proponent:
                    prop = next(p for p in self.proponents
                                if name == self.individual_field(c, p))
                rows.append({"label": prop.full_name if prop else "Group",
                             "name": name, "value": self.value_of(name), "proponent": prop})
            sec["criteria"].append({"criterion": c, "rows": rows})
        for sec in out:
            sec["weight_percent"] = (sec["weight"] * 100).normalize()
        return out


class PanelistForm(forms.Form):
    prefix = forms.CharField(max_length=20, required=False, help_text="e.g. Engr., Dr.")
    first_name = forms.CharField(
        label="First name (with middle initial)", max_length=150,
        help_text='e.g. "Jelmar L."')
    last_name = forms.CharField(max_length=150)
    suffix = forms.CharField(max_length=40, required=False, help_text="e.g. LPT, CCpE")
    username = forms.CharField(max_length=150)
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=False), required=False,
        help_text="At least 6 characters.")
    can_manage = forms.BooleanField(
        label="Can manage", required=False,
        help_text="Manager: create defenses, manage accounts and settings, view all results.")
    is_active = forms.BooleanField(label="Active", required=False, initial=True)

    def __init__(self, *args, panelist=None, **kwargs):
        self.panelist = panelist
        if panelist is not None:
            u = panelist.user
            kwargs.setdefault("initial", {
                "prefix": panelist.prefix, "suffix": panelist.suffix,
                "first_name": u.first_name, "last_name": u.last_name,
                "username": u.username, "can_manage": u.is_staff, "is_active": u.is_active,
            })
        super().__init__(*args, **kwargs)
        if panelist is None:
            self.fields["password"].required = True
        else:
            self.fields["password"].help_text = "Leave blank to keep the current password."

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        qs = User.objects.filter(username__iexact=username)
        if self.panelist is not None:
            qs = qs.exclude(pk=self.panelist.user_id)
        if qs.exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password

    def save(self):
        d = self.cleaned_data
        user = self.panelist.user if self.panelist else User()
        user.username = d["username"]
        user.first_name = d["first_name"].strip()
        user.last_name = d["last_name"].strip()
        user.is_staff = d["can_manage"]
        user.is_active = d["is_active"] if self.panelist else True
        if d.get("password"):
            user.set_password(d["password"])
        user.save()
        panelist, _ = Panelist.objects.get_or_create(user=user)
        panelist.prefix = d["prefix"].strip()
        panelist.suffix = d["suffix"].strip()
        panelist.save()
        return panelist


class ScoringSettingsForm(forms.ModelForm):
    class Meta:
        model = ScoringSettings
        fields = ["passed_cutoff", "minor_cutoff", "major_cutoff"]

    def clean(self):
        data = super().clean()
        cutoffs = [data.get(k) for k in ("passed_cutoff", "minor_cutoff", "major_cutoff")]
        if all(c is not None for c in cutoffs):
            if any(c < 1 or c > 5 for c in cutoffs):
                raise forms.ValidationError("Cutoffs must be between 1.00 and 5.00.")
            if not cutoffs[0] > cutoffs[1] > cutoffs[2]:
                raise forms.ValidationError(
                    "Cutoffs must strictly decrease: PASSED > MINOR > MAJOR.")
        return data
