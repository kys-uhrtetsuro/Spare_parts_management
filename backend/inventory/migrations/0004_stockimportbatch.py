from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_equipment_and_lineage")]

    operations = [
        migrations.CreateModel(
            name="StockImportBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("checksum", models.CharField(max_length=64, unique=True)),
                ("system_count", models.PositiveIntegerField()),
                ("opening_rows", models.PositiveIntegerField()),
                ("imported_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-imported_at"]},
        ),
    ]
