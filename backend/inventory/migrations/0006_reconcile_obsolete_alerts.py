"""Deduplicate legacy low-stock settings after parts are upgraded.

Old monitored revisions remain active while they still have stock and a newer
revision is not stocked. A newer monitored revision takes priority. Already
depleted obsolete revisions are removed.
"""
from collections import defaultdict

from django.db import migrations
from django.db.models import Case, F, IntegerField, Sum, When


def migrate_existing_alerts(apps, schema_editor):
    Part = apps.get_model("inventory", "PartMaster")
    Setting = apps.get_model("inventory", "StockAlertSetting")
    Movement = apps.get_model("inventory", "StockHistory")
    parents = dict(Part.objects.values_list("pk", "previous_part_id"))
    children = defaultdict(list)
    for pid, parent in parents.items():
        if parent is not None:
            children[parent].append(pid)

    def descendants(pid):
        result = []
        pending = [(pid, 0)]
        seen = {pid}
        while pending:
            cur, depth = pending.pop()
            for next_id in children.get(cur, ()):
                if next_id not in seen:
                    seen.add(next_id)
                    result.append((depth + 1, next_id))
                    pending.append((next_id, depth + 1))
        return sorted(result, reverse=True)

    for system_id in Setting.objects.values_list("system_id", flat=True).distinct():
        alerts = {
            row.part_id: row
            for row in Setting.objects.filter(system_id=system_id).order_by("pk")
        }
        stocks = {
            row["part_id"]: row["total"] or 0
            for row in Movement.objects.filter(system_id=system_id).values("part_id").annotate(
                total=Sum(Case(
                    When(direction="IN", then=F("quantity")),
                    default=-F("quantity"), output_field=IntegerField(),
                ))
            )
        }
        removed = set()
        for old_id, alert in list(alerts.items()):
            if old_id in removed:
                continue
            newer = descendants(old_id)
            if not newer:
                continue
            already_monitored = next(
                (pid for _, pid in newer if pid in alerts and pid not in removed), None
            )
            stocked_newer = next((pid for _, pid in newer if stocks.get(pid, 0) > 0), None)
            target = already_monitored or stocked_newer
            if target:
                if target not in alerts:
                    new_alert = Setting.objects.create(
                        system_id=system_id, part_id=target, threshold=alert.threshold
                    )
                    alerts[target] = new_alert
                removed.add(old_id)
            elif stocks.get(old_id, 0) <= 0:
                removed.add(old_id)
        if removed:
            Setting.objects.filter(
                system_id=system_id, part_id__in=removed
            ).delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0005_system_equipment")]
    operations = [
        migrations.RunPython(migrate_existing_alerts, migrations.RunPython.noop),
    ]
