# Generated manually for thread backfill

from django.db import migrations
from django.db.models import Max


def backfill_threads(apps, schema_editor):
    Message = apps.get_model("core", "Message")
    Thread = apps.get_model("core", "Thread")
    User = apps.get_model("core", "User")

    # Collect (customer_id, prisoner_id) from each message (sender/receiver)
    pairs = set()
    for msg in Message.objects.select_related("sender", "receiver").iterator():
        s, r = msg.sender_id, msg.receiver_id
        if not s or not r:
            continue
        sender = msg.sender
        receiver = msg.receiver
        if sender.role == "CUSTOMER" and receiver.role == "PRISONER":
            customer_id, prisoner_id = s, r
        elif sender.role == "PRISONER" and receiver.role == "CUSTOMER":
            customer_id, prisoner_id = r, s
        else:
            continue
        pairs.add((customer_id, prisoner_id))

    # Create threads and build mapping (customer_id, prisoner_id) -> thread_id
    thread_by_pair = {}
    for customer_id, prisoner_id in pairs:
        thread, _ = Thread.objects.get_or_create(
            customer_id=customer_id,
            prisoner_id=prisoner_id,
            defaults={},
        )
        thread_by_pair[(customer_id, prisoner_id)] = thread.id

    # Assign thread_id to each message
    for msg in Message.objects.select_related("sender", "receiver").iterator():
        s, r = msg.sender_id, msg.receiver_id
        if not s or not r:
            continue
        sender = msg.sender
        receiver = msg.receiver
        if sender.role == "CUSTOMER" and receiver.role == "PRISONER":
            customer_id, prisoner_id = s, r
        elif sender.role == "PRISONER" and receiver.role == "CUSTOMER":
            customer_id, prisoner_id = r, s
        else:
            continue
        thread_id = thread_by_pair.get((customer_id, prisoner_id))
        if thread_id:
            Message.objects.filter(pk=msg.pk).update(thread_id=thread_id)

    # Set each thread.updated_at to latest message created_at in that thread
    for thread_id in thread_by_pair.values():
        latest = Message.objects.filter(thread_id=thread_id).aggregate(Max("created_at"))["created_at__max"]
        if latest:
            Thread.objects.filter(pk=thread_id).update(updated_at=latest)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_add_thread_model"),
    ]

    operations = [
        migrations.RunPython(backfill_threads, noop),
    ]
