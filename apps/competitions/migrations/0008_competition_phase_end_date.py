from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("competitions", "0007_competition_google_credentials")]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="phase_end_date",
            field=models.DateField(
                blank=True, null=True, verbose_name="Current phase end date"
            ),
        ),
        migrations.AlterField(
            model_name="competition",
            name="date",
            field=models.DateField(verbose_name="Competition start date"),
        ),
    ]
