from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("inventory", "0007_multi_part_placements")]

    operations = [
        migrations.AlterField(
            model_name="partmaster",
            name="model_number",
            field=models.CharField("型式", max_length=160, blank=True),
        ),
    ]
