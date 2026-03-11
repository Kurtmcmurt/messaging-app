from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone

from .models import CustomerRecipient, Message, Thread, User
from .models import Role


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")
    ordering = ("username",)
    fieldsets = BaseUserAdmin.fieldsets + (("Role", {"fields": ("role",)}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (("Role", {"fields": ("role",)}),)


@admin.register(CustomerRecipient)
class CustomerRecipientAdmin(admin.ModelAdmin):
    list_display = ("customer", "prisoner", "created_at")
    list_filter = ("customer",)
    search_fields = ("customer__username", "prisoner__username")
    ordering = ("-created_at",)
    autocomplete_fields = ("customer", "prisoner")


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender", "receiver", "body", "created_at", "inspected_at", "inspected_by")
    can_delete = True
    show_change_link = True


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "prisoner", "updated_at", "created_at")
    list_filter = ("customer", "prisoner")
    search_fields = ("customer__username", "prisoner__username")
    ordering = ("-updated_at",)
    autocomplete_fields = ("customer", "prisoner")
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "thread",
        "sender",
        "receiver",
        "body_preview",
        "created_at",
        "inspected_at",
        "inspected_by",
    )
    list_filter = ("thread", "inspected_at", "created_at")
    search_fields = ("body", "sender__username", "receiver__username")
    ordering = ("-created_at",)
    autocomplete_fields = ("thread", "sender", "receiver", "inspected_by")
    readonly_fields = ("created_at",)
    actions = ["mark_as_inspected"]

    @admin.display(description="Body")
    def body_preview(self, obj):
        if len(obj.body) <= 50:
            return obj.body
        return obj.body[:50] + "…"

    @admin.action(description="Mark selected messages as inspected")
    def mark_as_inspected(self, request, queryset):
        if request.user.role not in (Role.OFFICER, Role.ADMIN, Role.SUPER_ADMIN):
            return
        now = timezone.now()
        updated = queryset.update(inspected_at=now, inspected_by=request.user)
        self.message_user(request, f"{updated} message(s) marked as inspected.")
