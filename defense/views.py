"""
Views (see AGENT_PROMPT.md, section 6). Score math is delegated to scoring.py.

    dashboard            list of defenses (all for managers, assigned ones for panelists)
    defense_create/edit  manager only: defense info, proponents, panel
    defense_toggle       manager only: open/close scoring
    defense_evaluate     shortcut: redirect to the current user's own evaluation
    evaluate             panelist rates the rubric, saves draft or submits
    evaluation_unlock    manager only: reopen a submitted evaluation
    results              each panelist's scores + the 2-of-3 panel decision
    results_status_json  polled by static/js/results.js for live updates
    print_results        printable summary sheet with 3 signature lines
    print_panelist_form  one panelist's filled form, printable
    panelist_list/form   manager only: panelist accounts
    scoring_settings     manager only: decision cutoffs
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import scoring
from .forms import (
    DefenseForm, EvaluationForm, PanelForm, PanelistForm, ProponentFormSet,
    ScoringSettingsForm,
)
from .models import (
    Defense, Evaluation, GroupRating, IndividualRating, PanelAssignment, Panelist,
    ScoringSettings,
)

# ------------------------------------------------------------------ access --


def is_manager(user):
    return user.is_authenticated and user.is_active and user.is_staff


def manager_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_manager(request.user):
            raise PermissionDenied("Managers only.")
        return view(request, *args, **kwargs)
    return wrapper


def assignment_for(defense, user):
    """The user's PanelAssignment on this defense, or None."""
    for a in defense.assignments.all():
        if a.panelist.user_id == user.pk:
            return a
    return None


def get_defense_for_viewer(request, pk):
    """The defense if the user is a manager or assigned to it; 403 otherwise."""
    defense = get_object_or_404(
        Defense.objects.prefetch_related("assignments__panelist__user"), pk=pk)
    mine = assignment_for(defense, request.user)
    if mine is None and not is_manager(request.user):
        raise PermissionDenied("You are not on this defense's panel.")
    return defense, mine


def _redirect_next(request, fallback, **kwargs):
    nxt = request.POST.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect(fallback, **kwargs)


def get_evaluation(assignment):
    try:
        return assignment.evaluation
    except Evaluation.DoesNotExist:
        return None


# --------------------------------------------------------------- dashboard --


@login_required
def dashboard(request):
    qs = Defense.objects.prefetch_related(
        "proponents", "assignments__panelist__user", "assignments__evaluation")
    manager = is_manager(request.user)
    if not manager:
        qs = qs.filter(assignments__panelist__user=request.user).distinct()

    items = []
    for d in qs:
        progress = scoring.defense_progress(d)
        mine = next((a for a, _ in progress if a.panelist.user_id == request.user.pk), None)
        my_status = next((s for a, s in progress if a is mine), None)
        submitted = sum(1 for _, s in progress if s == scoring.SUBMITTED)
        items.append({
            "defense": d,
            "proponents": list(d.proponents.all()),
            "progress": [{"assignment": a, "status": s, "label": scoring.STATUS_LABELS[s]}
                         for a, s in progress],
            "submitted": submitted,
            "total": scoring.REQUIRED_PANELISTS,
            "done": submitted == scoring.REQUIRED_PANELISTS,
            "mine": mine,
            "my_status": my_status,
        })
    return render(request, "defense/dashboard.html", {
        "items": items, "is_manager": manager,
    })


# ----------------------------------------------------------------- defense --


def _apply_panel(defense, chosen):
    """Create/update the 3 assignments. A role reassigned to another person
    loses its old assignment and evaluation."""
    existing = {a.role: a for a in defense.assignments.all()}
    changed_roles = []
    for role, a in existing.items():
        if role not in chosen or a.panelist_id != chosen[role].pk:
            changed_roles.append(role)
            a.delete()  # cascades to the evaluation and its ratings
    for role, panelist in chosen.items():
        if role not in existing or role in changed_roles:
            PanelAssignment.objects.create(defense=defense, panelist=panelist, role=role)
    return changed_roles


def _reopen_incomplete(defense):
    """Submitted evaluations that no longer cover every proponent go back to draft."""
    criteria = scoring.active_criteria()
    proponents = list(defense.proponents.all())
    reopened = []
    for ev in Evaluation.objects.filter(assignment__defense=defense, submitted=True):
        if not scoring.compute_panelist(ev, criteria, proponents).complete:
            ev.submitted = False
            ev.submitted_at = None
            ev.save(update_fields=["submitted", "submitted_at", "updated_at"])
            reopened.append(ev)
    return reopened


@manager_required
def defense_form(request, pk=None):
    defense = get_object_or_404(Defense, pk=pk) if pk else Defense()
    if request.method == "POST":
        form = DefenseForm(request.POST, instance=defense)
        formset = ProponentFormSet(request.POST, instance=defense, prefix="proponents")
        panel = PanelForm(request.POST, defense=defense)
        if form.is_valid() and formset.is_valid() and panel.is_valid():
            with transaction.atomic():
                defense = form.save()
                for f in formset.deleted_forms:
                    if f.instance.pk:
                        f.instance.delete()
                order = 0
                for f in formset.forms:
                    if f in formset.deleted_forms or not f.cleaned_data:
                        continue
                    if not f.instance.pk and not f.has_changed():
                        continue
                    obj = f.save(commit=False)
                    obj.defense = defense
                    obj.order = order
                    obj.save()
                    order += 1
                changed = _apply_panel(defense, panel.assignments())
                reopened = _reopen_incomplete(defense)
            messages.success(request, "Defense saved.")
            if pk and changed:
                roles = ", ".join(dict(PanelAssignment.ROLE_CHOICES)[r] for r in changed)
                messages.warning(request, f"Reassigned: {roles}. The previous panelist's "
                                          "evaluation for that role was deleted.")
            for ev in reopened:
                messages.warning(request, f"{ev.assignment.panelist} must rate the new "
                                          "proponent(s); their evaluation was reopened as a draft.")
            return redirect("defense:dashboard")
    else:
        form = DefenseForm(instance=defense)
        formset = ProponentFormSet(instance=defense, prefix="proponents")
        if not pk:
            formset.extra = 1  # one required row + one blank row to start
        panel = PanelForm(defense=defense)
    return render(request, "defense/defense_form.html", {
        "form": form, "formset": formset, "panel": panel, "defense": defense if pk else None,
        "max_proponents": formset.max_num,
    })


@manager_required
@require_POST
def defense_toggle(request, pk):
    defense = get_object_or_404(Defense, pk=pk)
    defense.status = Defense.CLOSED if defense.is_open else Defense.OPEN
    defense.save(update_fields=["status"])
    messages.success(request, f"Scoring for “{defense.title}” is now {defense.get_status_display().lower()}.")
    return _redirect_next(request, "defense:dashboard")


@manager_required
@require_POST
def defense_delete(request, pk):
    defense = get_object_or_404(Defense, pk=pk)
    title = defense.title
    with transaction.atomic():
        # Cascades to proponents, panel assignments, evaluations and ratings.
        defense.delete()
    messages.success(request, f"Deleted the defense “{title}” and all of its scores.")
    return redirect("defense:dashboard")


@login_required
def defense_evaluate(request, pk):
    defense = get_object_or_404(
        Defense.objects.prefetch_related("assignments__panelist__user"), pk=pk)
    mine = assignment_for(defense, request.user)
    if mine is None:
        raise PermissionDenied("You are not on this defense's panel.")
    return redirect("defense:evaluate", pk=mine.pk)


# -------------------------------------------------------------- evaluation --


class EvaluationLocked(Exception):
    pass


def _save_evaluation(assignment, form, submit):
    """Persist ratings in one short transaction."""
    with transaction.atomic():
        defense = Defense.objects.get(pk=assignment.defense_id)
        if not defense.is_open:
            raise EvaluationLocked("Scoring for this defense is closed.")
        ev, _ = Evaluation.objects.select_for_update().get_or_create(assignment=assignment)
        if ev.submitted and not submit:
            # A submitted evaluation counts toward the result, so it can only be
            # replaced by another complete one, never turned back into a draft.
            raise EvaluationLocked("Your evaluation is already submitted. Use Save changes, "
                                   "with every item rated, to update it.")
        group, individual = form.ratings()
        GroupRating.objects.filter(evaluation=ev).delete()
        IndividualRating.objects.filter(evaluation=ev).delete()
        GroupRating.objects.bulk_create(
            GroupRating(evaluation=ev, criterion=c, rating=r) for c, r in group.items())
        IndividualRating.objects.bulk_create(
            IndividualRating(evaluation=ev, criterion=c, proponent=p, rating=r)
            for (c, p), r in individual.items())
        ev.comments = form.cleaned_data.get("comments", "")
        if submit:
            ev.submitted = True
            ev.submitted_at = timezone.now()
        ev.save()
    return ev


@login_required
def evaluate(request, pk):
    assignment = get_object_or_404(
        PanelAssignment.objects.select_related("defense", "panelist__user"), pk=pk)
    if assignment.panelist.user_id != request.user.pk:
        raise PermissionDenied("You can only open your own evaluation.")
    defense = assignment.defense
    criteria = scoring.active_criteria()
    proponents = list(defense.proponents.all())
    cutoffs = scoring.current_cutoffs()
    evaluation = get_evaluation(assignment)
    # Panelists may change their scores, even after submitting, until the
    # coordinator closes scoring for the defense.
    locked_reason = "" if defense.is_open else "closed"
    was_submitted = bool(evaluation and evaluation.submitted)

    if request.method == "POST":
        if locked_reason:
            messages.error(request, "Scoring for this defense is closed; changes were not saved.")
            return redirect("defense:evaluate", pk=pk)
        submit = was_submitted or request.POST.get("action") == "submit"
        form = EvaluationForm(request.POST, criteria=criteria, proponents=proponents,
                              submit=submit)
        try:
            if form.is_valid():
                _save_evaluation(assignment, form, submit)
                if was_submitted:
                    messages.success(request, "Your changes were saved. Your submitted scores are updated.")
                    return redirect("defense:results", pk=defense.pk)
                if submit:
                    messages.success(request, "Evaluation submitted. Thank you!")
                    return redirect("defense:results", pk=defense.pk)
                messages.success(request, "Draft saved.")
                return redirect("defense:evaluate", pk=pk)
            if submit and not was_submitted:
                # Keep the panelist's work: save what was given as a draft.
                draft = EvaluationForm(request.POST, criteria=criteria,
                                       proponents=proponents, submit=False)
                if draft.is_valid():
                    _save_evaluation(assignment, draft, False)
                    messages.warning(request, "Not submitted — some ratings are missing. "
                                              "Your ratings were saved as a draft.")
                evaluation = get_evaluation(assignment)
        except EvaluationLocked as exc:
            messages.error(request, str(exc))
            return redirect("defense:evaluate", pk=pk)
    else:
        form = EvaluationForm(
            initial=EvaluationForm.initial_from(evaluation, criteria, proponents),
            criteria=criteria, proponents=proponents)

    score = scoring.compute_panelist(evaluation, criteria, proponents, cutoffs) \
        if evaluation else scoring.score_ratings(criteria, proponents, {}, {}, cutoffs)
    return render(request, "defense/evaluate.html", {
        "defense": defense,
        "assignment": assignment,
        "evaluation": evaluation,
        "panel": sorted(defense.assignments.select_related("panelist__user"),
                        key=lambda a: a.role_order),
        "proponents": proponents,
        "form": form,
        "sections": form.sections(),
        "score": score,
        "cutoffs": cutoffs,
        "locked": bool(locked_reason),
        "locked_reason": locked_reason,
        "was_submitted": was_submitted,
        "verdict_labels": scoring.VERDICT_LABELS,
    })


@manager_required
@require_POST
def evaluation_unlock(request, pk):
    assignment = get_object_or_404(PanelAssignment, pk=pk)
    with transaction.atomic():
        updated = Evaluation.objects.filter(assignment=assignment, submitted=True).update(
            submitted=False, submitted_at=None, updated_at=timezone.now())
    if updated:
        messages.success(request, f"Unlocked the evaluation of {assignment.panelist}.")
    else:
        messages.info(request, "That evaluation was not submitted.")
    return _redirect_next(request, "defense:results", pk=assignment.defense_id)


# ----------------------------------------------------------------- results --


def _scores_version(defense):
    """Changes whenever a submitted evaluation is saved again, so an open
    results page knows to reload."""
    latest = Evaluation.objects.filter(assignment__defense=defense, submitted=True)         .aggregate(m=Max("submitted_at"))["m"]
    return latest.isoformat() if latest else ""


def _results_context(request, defense, mine):
    result = scoring.compute_defense(defense)
    return {
        "scores_version": _scores_version(defense),
        "defense": defense,
        "result": result,
        "mine": mine,
        "is_manager": is_manager(request.user),
        "verdict_choices": scoring.verdict_bands(result.cutoffs),
        "cutoffs": result.cutoffs,
    }


@login_required
def results(request, pk):
    defense, mine = get_defense_for_viewer(request, pk)
    return render(request, "defense/results.html", _results_context(request, defense, mine))


@login_required
def results_status_json(request, pk):
    defense, _ = get_defense_for_viewer(request, pk)
    progress = scoring.defense_progress(defense)
    submitted = sum(1 for _, s in progress if s == scoring.SUBMITTED)
    complete = submitted == scoring.REQUIRED_PANELISTS and scoring.compute_defense(defense).complete
    return JsonResponse({
        "defense": defense.pk,
        "status": defense.status,
        "submitted": submitted,
        "total": scoring.REQUIRED_PANELISTS,
        "complete": complete,
        "version": _scores_version(defense),
        "panelists": [{
            "assignment": a.pk, "role": a.role, "role_label": a.get_role_display(),
            "name": a.panelist.display_name, "status": s,
            "status_label": scoring.STATUS_LABELS[s],
        } for a, s in progress],
    })


@login_required
def print_results(request, pk):
    defense, mine = get_defense_for_viewer(request, pk)
    return render(request, "defense/print_results.html",
                  _results_context(request, defense, mine))


@login_required
def print_panelist_form(request, pk):
    assignment = get_object_or_404(
        PanelAssignment.objects.select_related("defense", "panelist__user"), pk=pk)
    defense = assignment.defense
    own = assignment.panelist.user_id == request.user.pk
    if not own and not is_manager(request.user):
        raise PermissionDenied("You can only print your own evaluation.")
    criteria = scoring.active_criteria()
    proponents = list(defense.proponents.all())
    cutoffs = scoring.current_cutoffs()
    evaluation = get_evaluation(assignment)
    group, individual = scoring.load_ratings(evaluation) if evaluation else ({}, {})
    score = scoring.score_ratings(criteria, proponents, group, individual, cutoffs)
    return render(request, "defense/print_form.html", {
        "defense": defense,
        "assignment": assignment,
        "evaluation": evaluation,
        "panel": sorted(defense.assignments.select_related("panelist__user"),
                        key=lambda a: a.role_order),
        "proponents": proponents,
        "lines": scoring.rating_lines(criteria, proponents, group, individual),
        "score": score,
        "verdict_choices": scoring.verdict_bands(cutoffs),
        "cutoffs": cutoffs,
    })


# ---------------------------------------------------------------- accounts --


@manager_required
def panelist_list(request):
    panelists = Panelist.objects.select_related("user").annotate(
        panel_count=Count("assignments")).order_by(
        "-user__is_active", "user__last_name", "user__first_name")
    return render(request, "defense/panelist_list.html", {"panelists": panelists})


def _delete_blocker(request, panelist):
    """Why this account can't be deleted, or "" if it can."""
    if panelist.user_id == request.user.pk:
        return "You cannot delete your own account."
    if panelist.user.is_superuser and not request.user.is_superuser:
        return "Only a superuser can delete an administrator account."
    titles = list(panelist.assignments.values_list("defense__title", flat=True))
    if titles:
        return (f"{panelist.display_name} is on the panel of: {'; '.join(titles)}. "
                "Deleting the account would also delete their scores. Edit those defenses to "
                "assign someone else first, or untick Active to stop them signing in.")
    return ""


@manager_required
@require_POST
def panelist_delete(request, pk):
    panelist = get_object_or_404(Panelist.objects.select_related("user"), pk=pk)
    blocker = _delete_blocker(request, panelist)
    if blocker:
        messages.error(request, blocker)
        return redirect("defense:panelist_list")
    name = panelist.display_name
    with transaction.atomic():
        panelist.user.delete()  # cascades to the Panelist profile
    messages.success(request, f"Deleted the account of {name}.")
    return redirect("defense:panelist_list")


@manager_required
def panelist_form(request, pk=None):
    panelist = get_object_or_404(Panelist.objects.select_related("user"), pk=pk) if pk else None
    if request.method == "POST":
        form = PanelistForm(request.POST, panelist=panelist)
        if form.is_valid():
            if panelist and panelist.user_id == request.user.pk and (
                    not form.cleaned_data["can_manage"] or not form.cleaned_data["is_active"]):
                form.add_error(None, "You cannot remove your own manager access or "
                                     "deactivate yourself.")
            else:
                with transaction.atomic():
                    saved = form.save()
                messages.success(request, f"Saved {saved.display_name}.")
                return redirect("defense:panelist_list")
    else:
        form = PanelistForm(panelist=panelist)
    return render(request, "defense/panelist_form.html", {"form": form, "panelist": panelist})


# ---------------------------------------------------------------- settings --


@manager_required
def scoring_settings(request):
    obj = ScoringSettings.load()
    if request.method == "POST":
        form = ScoringSettingsForm(request.POST, instance=obj)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, "Scoring settings saved.")
            return redirect("defense:scoring_settings")
    else:
        form = ScoringSettingsForm(instance=obj)
    return render(request, "defense/settings_form.html", {"form": form})
