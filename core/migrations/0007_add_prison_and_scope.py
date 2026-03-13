# Generated manually: Prison model, User.prison, Thread.prison with backfill

from django.db import migrations, models
import django.db.models.deletion


def create_default_prison_and_backfill(apps, schema_editor):
    Prison = apps.get_model("core", "Prison")
    User = apps.get_model("core", "User")
    Thread = apps.get_model("core", "Thread")

    # Create a default prison for existing data
    prison, _ = Prison.objects.get_or_create(
        code="DEFAULT",
        defaults={"name": "Default Prison"},
    )
    # Set prison on all prisoners, officers, admins that don't have one
    User.objects.filter(prison__isnull=True).filter(
        role__in=("PRISONER", "OFFICER", "ADMIN")
    ).update(prison_id=prison.id)
    # Set thread.prison from prisoner's prison (prisoners now have prison)
    for thread in Thread.objects.select_related("prisoner").filter(prison__isnull=True):
        if thread.prisoner.prison_id:
            thread.prison_id = thread.prisoner.prison_id
            thread.save(update_fields=["prison_id"])

    # Any threads still null (prisoner had no prison) get default
    Thread.objects.filter(prison__isnull=True).update(prison_id=prison.id)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_add_prisoner_number"),
    ]

    operations = [
        migrations.CreateModel(
            name="Prison",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("code", models.CharField(help_text="Short code (e.g. BXI, WDI)", max_length=20, unique=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="user",
            name="prison",
            field=models.ForeignKey(
                blank=True,
                help_text="Prison for staff/prisoners; for customers, the prison they have joined to message.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="core.prison",
            ),
        ),
        migrations.AddField(
            model_name="thread",
            name="prison",
            field=models.ForeignKey(
                help_text="Prison of the prisoner; used to scope threads when customer changes prison.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="threads",
                to="core.prison",
            ),
        ),
        migrations.RunPython(create_default_prison_and_backfill, noop_reverse),
        migrations.AlterField(
            model_name="thread",
            name="prison",
            field=models.ForeignKey(
                help_text="Prison of the prisoner; used to scope threads when customer changes prison.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="threads",
                to="core.prison",
            ),
        ),
        migrations.AddIndex(
            model_name="thread",
            index=models.Index(fields=["prison", "-updated_at"], name="core_thread_prison__a1b2c3_idx"),
        ),
    ]
