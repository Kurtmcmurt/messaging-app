from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

# UK MoJ / NOMIS-style: 2 letters + 4 digits (e.g. AB1234) or 1 letter + 4 digits + 2 letters (e.g. A1417AE)
prisoner_number_validator = RegexValidator(
    r"^([A-Z]{2}[0-9]{4}|[A-Z][0-9]{4}[A-Z]{2})$",
    message="Enter a valid UK prisoner number (e.g. AB1234 or A1417AE).",
    code="invalid_prisoner_number",
)


class Prison(models.Model):
    """A prison establishment. Users and content are scoped by prison."""

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, unique=True, help_text="Short code (e.g. BXI, WDI)")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


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
    prison = models.ForeignKey(
        Prison,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
        help_text="Prison for staff/prisoners; for customers, the prison they have joined to message.",
    )
    prisoner_number = models.CharField(
        max_length=10,
        unique=True,
        null=True,
        blank=True,
        validators=[prisoner_number_validator],
        help_text="UK MoJ-style prisoner number (e.g. AB1234 or A1417AE). Only for prisoners.",
    )

    def clean(self):
        super().clean()
        if self.prisoner_number:
            self.prisoner_number = self.prisoner_number.strip().upper()
            if self.role != Role.PRISONER:
                raise ValidationError(
                    {"prisoner_number": "Prisoner number is only for users with role Prisoner."}
                )
        if self.role in (Role.PRISONER, Role.OFFICER, Role.ADMIN) and not self.prison_id:
            raise ValidationError(
                {"prison": "Prison is required for prisoners, officers, and admins."}
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

    prison = models.ForeignKey(
        Prison,
        on_delete=models.PROTECT,
        related_name="threads",
        help_text="Prison of the prisoner; used to scope threads when customer changes prison.",
    )
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
            models.Index(fields=["prison", "-updated_at"]),
            models.Index(fields=["customer", "prisoner"]),
            models.Index(fields=["-updated_at"]),
        ]
        ordering = ["-updated_at"]

    @classmethod
    def get_or_create_thread(cls, customer, prisoner):
        """Return the thread for this (customer, prisoner), creating it only if allowed."""
        if not prisoner.prison_id:
            raise ValidationError("Prisoner has no prison set.")
        if customer.prison_id != prisoner.prison_id:
            raise ValidationError(
                "You can only message prisoners at the prison you have joined."
            )
        if not CustomerRecipient.objects.filter(
            customer=customer, prisoner=prisoner
        ).exists():
            raise ValidationError(
                "This customer is not allowed to message this prisoner."
            )
        thread, _ = cls.objects.get_or_create(
            customer=customer,
            prisoner=prisoner,
            defaults={"prison_id": prisoner.prison_id},
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
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the receiver viewed the thread (read receipt).",
    )
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
