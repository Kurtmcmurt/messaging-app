from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class Role(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
    ADMIN = "ADMIN", "Admin"
    OFFICER = "OFFICER", "Officer"
    PRISONER = "PRISONER", "Prisoner"
    CUSTOMER = "CUSTOMER", "Customer"


class User(AbstractUser):
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
    )


class CustomerRecipient(models.Model):
    """Links a customer to a prisoner they are allowed to message."""

    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="allowed_prisoners",
        limit_choices_to={"role": Role.CUSTOMER},
    )
    prisoner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="allowed_customers",
        limit_choices_to={"role": Role.PRISONER},
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("customer", "prisoner")]
        indexes = [
            models.Index(fields=["customer", "prisoner"]),
        ]


class Thread(models.Model):
    """One conversation between a customer and a prisoner (WhatsApp-style thread)."""

    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="threads_as_customer",
        limit_choices_to={"role": Role.CUSTOMER},
    )
    prisoner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="threads_as_prisoner",
        limit_choices_to={"role": Role.PRISONER},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "prisoner"],
                name="core_thread_customer_prisoner_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["customer", "prisoner"]),
            models.Index(fields=["-updated_at"]),
        ]
        ordering = ["-updated_at"]

    @classmethod
    def get_or_create_thread(cls, customer, prisoner):
        """Return the thread for this (customer, prisoner), creating it only if allowed."""
        if not CustomerRecipient.objects.filter(
            customer=customer, prisoner=prisoner
        ).exists():
            raise ValidationError(
                "This customer is not allowed to message this prisoner."
            )
        thread, _ = cls.objects.get_or_create(
            customer=customer,
            prisoner=prisoner,
            defaults={},
        )
        return thread


class Message(models.Model):
    thread = models.ForeignKey(
        "Thread",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    receiver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_messages",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    inspected_at = models.DateTimeField(null=True, blank=True)
    inspected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inspected_messages",
        limit_choices_to={"role": Role.OFFICER},
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["sender", "receiver"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["thread"]),
        ]

    def clean(self):
        super().clean()
        if not self.sender_id or not self.receiver_id:
            return
        if self.sender_id == self.receiver_id:
            raise ValidationError({"receiver": "Sender and receiver must be different."})
        roles = {self.sender.role, self.receiver.role}
        if roles != {Role.PRISONER, Role.CUSTOMER}:
            raise ValidationError(
                "Message must be between a prisoner and a customer."
            )
        customer = self.sender if self.sender.role == Role.CUSTOMER else self.receiver
        prisoner = self.sender if self.sender.role == Role.PRISONER else self.receiver
        if not CustomerRecipient.objects.filter(
            customer=customer, prisoner=prisoner
        ).exists():
            raise ValidationError(
                "This customer is not allowed to message this prisoner."
            )
        if self.thread_id:
            if (self.thread.customer_id, self.thread.prisoner_id) != (
                customer.id,
                prisoner.id,
            ):
                raise ValidationError(
                    {"thread": "Thread customer/prisoner must match sender/receiver."}
                )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.thread_id and self.created_at:
            Thread.objects.filter(pk=self.thread_id).update(
                updated_at=self.created_at
            )
