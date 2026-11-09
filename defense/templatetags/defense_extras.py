"""Template helpers: display formatting only — no score math lives here."""
from decimal import Decimal

from django import template

from .. import scoring

register = template.Library()


@register.filter
def get_item(mapping, key):
    """{{ mydict|get_item:key }}"""
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def fmt2(value, blank="—"):
    """Show a score with exactly 2 decimals (ROUND_HALF_UP); blank for None."""
    if value is None or value == "":
        return blank
    return f"{scoring.round2(value):.2f}"


@register.filter
def pct(value):
    """Decimal percent without trailing zeros: 35.00 -> 35, 33.50 -> 33.5"""
    if value is None:
        return ""
    d = Decimal(value).normalize()
    return f"{d:f}"


@register.filter
def verdict_label(code):
    return scoring.verdict_label(code)


@register.filter
def verdict_short(code):
    return {scoring.PASSED: "PASSED", scoring.MINOR: "MINOR",
            scoring.MAJOR: "MAJOR", scoring.FAILED: "FAILED"}.get(code, "")


@register.filter
def verdict_class(code):
    return {scoring.PASSED: "v-passed", scoring.MINOR: "v-minor",
            scoring.MAJOR: "v-major", scoring.FAILED: "v-failed"}.get(code, "")


@register.filter
def status_class(status):
    return {scoring.SUBMITTED: "chip-ok", scoring.DRAFT: "chip-warn"}.get(status, "chip-muted")
