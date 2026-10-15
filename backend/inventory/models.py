from django.db import models
from django.db.models import Q


class SystemMaster(models.Model):
    name = models.CharField("システム名", max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class EquipmentMaster(models.Model):
    system = models.ForeignKey(SystemMaster, on_delete=models.PROTECT, related_name="equipment")
    name = models.CharField("機器名", max_length=160)
    alias = models.CharField("機器通称", max_length=160, blank=True)

    class Meta:
        ordering = ["system_id", "name"]
        constraints = [
            models.UniqueConstraint(fields=["system", "name"], name="unique_equipment_per_system"),
        ]


class EquipmentSection(models.Model):
    equipment = models.ForeignKey(EquipmentMaster, on_delete=models.PROTECT, related_name="sections")
    name = models.CharField("部位名", max_length=160)

    class Meta:
        ordering = ["equipment_id", "name"]
        constraints = [
            models.UniqueConstraint(fields=["equipment", "name"], name="unique_equipment_section")
        ]


class PartCategory(models.Model):
    name = models.CharField("分類名", max_length=160, unique=True)

    class Meta:
        ordering = ["name"]


class PartMaster(models.Model):
    part_number = models.CharField("品番", max_length=160)
    model_number = models.CharField("型式", max_length=160)
    name = models.CharField("品名", max_length=250)
    previous_part = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="successors"
    )
    category = models.ForeignKey(
        PartCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="parts"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["part_number", "model_number"]
        constraints = [
            models.UniqueConstraint(fields=["part_number", "model_number"], name="unique_part_identifier")
        ]

    def __str__(self):
        return f"{self.part_number} / {self.model_number}"


class SystemPartPlacement(models.Model):
    """Attach a shared part to equipment separately for each system."""
    system = models.ForeignKey(SystemMaster, on_delete=models.PROTECT, related_name="part_placements")
    part = models.ForeignKey(PartMaster, on_delete=models.PROTECT, related_name="placements")
    equipment = models.ForeignKey(EquipmentMaster, on_delete=models.PROTECT)
    section = models.ForeignKey(EquipmentSection, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["system", "part"], name="unique_part_placement_per_system"),
        ]


class PartVersion(models.Model):
    part = models.ForeignKey(PartMaster, on_delete=models.PROTECT, related_name="versions")
    old_part_number = models.CharField(max_length=160)
    old_model_number = models.CharField(max_length=160)
    new_part_number = models.CharField(max_length=160)
    new_model_number = models.CharField(max_length=160)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class StockHistory(models.Model):
    IN = "IN"
    OUT = "OUT"
    DIRECTION_CHOICES = [(IN, "補充"), (OUT, "使用")]
    system = models.ForeignKey(SystemMaster, on_delete=models.PROTECT)
    part = models.ForeignKey(PartMaster, on_delete=models.PROTECT)
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    quantity = models.PositiveIntegerField()
    operator = models.CharField(max_length=160)
    note = models.CharField(max_length=400, blank=True)
    part_number_snapshot = models.CharField(max_length=160)
    model_number_snapshot = models.CharField(max_length=160)
    reversal_of = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversal"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="history_positive_quantity"),
        ]

    def signed_quantity(self):
        return self.quantity if self.direction == self.IN else -self.quantity


class StockAlertSetting(models.Model):
    system = models.ForeignKey(SystemMaster, on_delete=models.CASCADE)
    part = models.ForeignKey(PartMaster, on_delete=models.CASCADE)
    threshold = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["system", "part"], name="unique_alert_for_system_part"),
            models.CheckConstraint(condition=Q(threshold__gte=1), name="alert_positive_threshold"),
        ]


class StockImportBatch(models.Model):
    """Tracks imported workbook bytes so a fork cannot silently double stock."""
    checksum = models.CharField(max_length=64, unique=True)
    system_count = models.PositiveIntegerField()
    opening_rows = models.PositiveIntegerField()
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
