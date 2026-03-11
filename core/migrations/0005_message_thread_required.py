# Generated manually: make Message.thread non-null (after 0004 backfill)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_backfill_message_threads"),
    ]

    operations = [
        migrations.AlterField(
            model_name="message",
            name="thread",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="messages",
                to="core.thread",
            ),
        ),
    ]
