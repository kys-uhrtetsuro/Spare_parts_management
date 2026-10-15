from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]

    operations = [
        migrations.RemoveField(
            model_name="stockhistory",
            name="company",
        ),
    ]
