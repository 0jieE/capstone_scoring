"""Seed the 6 rubric criteria from docs/rubric.md on a fresh migrate."""
from django.db import migrations


def seed(apps, schema_editor):
    from defense.management.commands.seed_rubric import seed_criteria

    seed_criteria(apps.get_model("defense", "Criterion"))


class Migration(migrations.Migration):

    dependencies = [
        ("defense", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
