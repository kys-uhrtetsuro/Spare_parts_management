from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="SystemMaster",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120, unique=True, verbose_name="システム名")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="PartMaster",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("part_number", models.CharField(max_length=160, verbose_name="品番")),
                ("model_number", models.CharField(max_length=160, verbose_name="型式")),
                ("name", models.CharField(max_length=250, verbose_name="品名")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["part_number", "model_number"]},
        ),
        migrations.CreateModel(
            name="PartVersion",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("old_part_number", models.CharField(max_length=160)),
                ("old_model_number", models.CharField(max_length=160)),
                ("new_part_number", models.CharField(max_length=160)),
                ("new_model_number", models.CharField(max_length=160)),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                ("part", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="inventory.partmaster")),
            ],
            options={"ordering": ["-changed_at", "-id"]},
        ),
        migrations.CreateModel(
            name="StockHistory",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("direction", models.CharField(choices=[("IN", "補充"), ("OUT", "使用")], max_length=3)),
                ("quantity", models.PositiveIntegerField()),
                ("company", models.CharField(max_length=160)),
                ("operator", models.CharField(max_length=160)),
                ("note", models.CharField(blank=True, max_length=400)),
                ("part_number_snapshot", models.CharField(max_length=160)),
                ("model_number_snapshot", models.CharField(max_length=160)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("part", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="inventory.partmaster")),
                ("system", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="inventory.systemmaster")),
                ("reversal_of", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reversal", to="inventory.stockhistory")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="StockAlertSetting",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("threshold", models.PositiveIntegerField()),
                ("part", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="inventory.partmaster")),
                ("system", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="inventory.systemmaster")),
            ],
        ),
        migrations.AddConstraint("partmaster", models.UniqueConstraint(fields=("part_number", "model_number"), name="unique_part_identifier")),
        migrations.AddConstraint("stockhistory", models.CheckConstraint(condition=Q(quantity__gte=1), name="history_positive_quantity")),
        migrations.AddConstraint("stockalertsetting", models.UniqueConstraint(fields=("system", "part"), name="unique_alert_for_system_part")),
        migrations.AddConstraint("stockalertsetting", models.CheckConstraint(condition=Q(threshold__gte=1), name="alert_positive_threshold")),
    ]
