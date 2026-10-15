from collections import defaultdict

from django.db import migrations, models
import django.db.models.deletion


def restore_prior_identifiers(apps, schema_editor):
    """Repair data created before predecessor records were introduced.

    Earlier releases overwrote PartMaster.part_number/model_number in place.
    The ledger already stored the identifiers used when each movement was
    entered. Recreate missing predecessor masters and reconnect ledger rows to
    the actual version the user originally registered.
    """
    Part = apps.get_model("inventory", "PartMaster")
    Version = apps.get_model("inventory", "PartVersion")
    History = apps.get_model("inventory", "StockHistory")
    by_part = defaultdict(list)
    for event in Version.objects.order_by("changed_at", "pk"):
        by_part[event.part_id].append(event)

    for current_id, events in by_part.items():
        current = Part.objects.get(pk=current_id)
        mapping = {(current.part_number, current.model_number): current}
        for event in events:
            for identifier in (
                (event.old_part_number, event.old_model_number),
                (event.new_part_number, event.new_model_number),
            ):
                if identifier not in mapping:
                    part, _ = Part.objects.get_or_create(
                        part_number=identifier[0], model_number=identifier[1],
                        defaults={"name": current.name},
                    )
                    mapping[identifier] = part

        for event in events:
            old = mapping[(event.old_part_number, event.old_model_number)]
            new = mapping[(event.new_part_number, event.new_model_number)]
            if new.pk != old.pk and new.previous_part_id is None:
                new.previous_part_id = old.pk
                new.save(update_fields=["previous_part"])
            # Track the predecessor that actually existed at the time.
            event.part_id = old.pk
            event.save(update_fields=["part"])

        for movement in History.objects.filter(part_id=current_id).iterator():
            old_part = mapping.get(
                (movement.part_number_snapshot, movement.model_number_snapshot)
            )
            if old_part is not None and old_part.pk != current_id:
                History.objects.filter(pk=movement.pk).update(part_id=old_part.pk)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0002_remove_stockhistory_company")]

    operations = [
        migrations.CreateModel(
            name="EquipmentMaster",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160, unique=True, verbose_name="機器名")),
                ("alias", models.CharField(blank=True, max_length=160, verbose_name="機器通称")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="PartCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160, unique=True, verbose_name="分類名")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="EquipmentSection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160, verbose_name="部位名")),
                ("equipment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sections", to="inventory.equipmentmaster")),
            ],
            options={"ordering": ["equipment_id", "name"]},
        ),
        migrations.AddField(
            model_name="partmaster", name="previous_part",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="successors", to="inventory.partmaster"),
        ),
        migrations.AddField(
            model_name="partmaster", name="equipment",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="parts", to="inventory.equipmentmaster"),
        ),
        migrations.AddField(
            model_name="partmaster", name="section",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="parts", to="inventory.equipmentsection"),
        ),
        migrations.AddField(
            model_name="partmaster", name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="parts", to="inventory.partcategory"),
        ),
        migrations.AddConstraint(
            model_name="equipmentsection",
            constraint=models.UniqueConstraint(fields=("equipment", "name"), name="unique_equipment_section"),
        ),
        migrations.RunPython(restore_prior_identifiers, migrations.RunPython.noop),
    ]
