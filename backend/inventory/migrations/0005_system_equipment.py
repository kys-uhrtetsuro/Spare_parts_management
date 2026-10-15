"""Move machines under systems; migrate global part-machine links to per-system placements."""
from collections import defaultdict

from django.db import migrations, models
import django.db.models.deletion


def migrate_equipment_links(apps, schema_editor):
    System = apps.get_model("inventory", "SystemMaster")
    Equipment = apps.get_model("inventory", "EquipmentMaster")
    Section = apps.get_model("inventory", "EquipmentSection")
    Part = apps.get_model("inventory", "PartMaster")
    Movement = apps.get_model("inventory", "StockHistory")
    Alert = apps.get_model("inventory", "StockAlertSetting")
    Placement = apps.get_model("inventory", "SystemPartPlacement")

    all_system_ids = list(System.objects.order_by("id").values_list("id", flat=True))
    fallback = None

    def system_fallback():
        nonlocal fallback
        if len(all_system_ids) == 1:
            return all_system_ids[0]
        if fallback is None:
            fallback = System.objects.get_or_create(name="未割当（旧機器）")[0].pk
        return fallback

    for equipment in list(Equipment.objects.order_by("id")):
        parts = list(Part.objects.filter(equipment_id=equipment.id).order_by("id"))
        assigned = defaultdict(list)
        for part in parts:
            ids = set(Movement.objects.filter(part_id=part.pk).values_list("system_id", flat=True))
            ids.update(Alert.objects.filter(part_id=part.pk).values_list("system_id", flat=True))
            for sid in (sorted(ids) if ids else [system_fallback()]):
                assigned[sid].append(part)
        if not assigned:
            assigned[system_fallback()] = []

        old_sections = list(Section.objects.filter(equipment_id=equipment.id).order_by("id"))
        for index, (sid, linked_parts) in enumerate(sorted(assigned.items())):
            if index == 0:
                equipment.system_id = sid
                equipment.save(update_fields=["system"])
                eq = equipment
                section_map = {x.id: x.id for x in old_sections}
            else:
                eq = Equipment.objects.create(
                    system_id=sid, name=equipment.name, alias=equipment.alias,
                )
                section_map = {}
                for old_section in old_sections:
                    new_section = Section.objects.create(equipment=eq, name=old_section.name)
                    section_map[old_section.pk] = new_section.pk
            for part in linked_parts:
                Placement.objects.create(
                    system_id=sid, part_id=part.pk, equipment=eq,
                    section_id=section_map.get(part.section_id),
                )


class Migration(migrations.Migration):
    dependencies = [("inventory", "0004_stockimportbatch")]

    operations = [
        migrations.AddField(
            model_name="equipmentmaster", name="system",
            field=models.ForeignKey(
                null=True, to="inventory.systemmaster",
                on_delete=django.db.models.deletion.PROTECT, related_name="equipment",
            ),
        ),
        migrations.AlterField(
            model_name="equipmentmaster", name="name",
            field=models.CharField(max_length=160, verbose_name="機器名"),
        ),
        migrations.CreateModel(
            name="SystemPartPlacement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("equipment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="inventory.equipmentmaster")),
                ("part", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="placements", to="inventory.partmaster")),
                ("section", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="inventory.equipmentsection")),
                ("system", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="part_placements", to="inventory.systemmaster")),
            ],
        ),
        migrations.RunPython(migrate_equipment_links, migrations.RunPython.noop),
        migrations.RemoveField(model_name="partmaster", name="equipment"),
        migrations.RemoveField(model_name="partmaster", name="section"),
        migrations.AlterField(
            model_name="equipmentmaster", name="system",
            field=models.ForeignKey(
                to="inventory.systemmaster",
                on_delete=django.db.models.deletion.PROTECT, related_name="equipment",
            ),
        ),
        migrations.AddConstraint(
            model_name="equipmentmaster",
            constraint=models.UniqueConstraint(fields=("system", "name"), name="unique_equipment_per_system"),
        ),
        migrations.AddConstraint(
            model_name="systempartplacement",
            constraint=models.UniqueConstraint(fields=("system", "part"), name="unique_part_placement_per_system"),
        ),
        migrations.AlterModelOptions(
            name="equipmentmaster", options={"ordering": ["system_id", "name"]},
        ),
        migrations.AlterModelOptions(
            name="partversion", options={"ordering": ["id"]},
        ),
        migrations.AlterModelOptions(
            name="stockhistory", options={"ordering": ["id"]},
        ),
        migrations.AlterModelOptions(
            name="stockimportbatch", options={"ordering": ["id"]},
        ),
    ]
