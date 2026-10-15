from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("inventory", "0006_reconcile_obsolete_alerts")]

    operations = [
        migrations.RemoveConstraint(
            model_name="systempartplacement",
            name="unique_part_placement_per_system",
        ),
        migrations.AddConstraint(
            model_name="systempartplacement",
            constraint=models.UniqueConstraint(
                fields=("system", "part", "equipment", "section"),
                condition=Q(section__isnull=False),
                name="uniq_placement_section",
            ),
        ),
        migrations.AddConstraint(
            model_name="systempartplacement",
            constraint=models.UniqueConstraint(
                fields=("system", "part", "equipment"),
                condition=Q(section__isnull=True),
                name="uniq_placement_no_section",
            ),
        ),
    ]
