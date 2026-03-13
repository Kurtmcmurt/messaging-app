from django.contrib.auth import authenticate, login
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .decorators import customer_prison_required, messaging_dashboard_required, staff_dashboard_required
from .models import CustomerRecipient, Message, Prison, Role, Thread, User


def home(request):
    return render(request, "core/home.html")


def about(request):
    return render(request, "core/about.html")


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return _redirect_after_login(request.user)
    if request.method != "POST":
        return render(request, "registration/login.html")
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return render(
            request,
            "registration/login.html",
            {"error": "Invalid username or password."},
        )
    login(request, user)
    next_url = request.GET.get("next") or request.POST.get("next")
    if next_url:
        return redirect(next_url)
    return _redirect_after_login(user)


def _redirect_after_login(user):
    if user.role in (Role.OFFICER, Role.ADMIN, Role.SUPER_ADMIN):
        return redirect("dashboard:vetting")
    if user.role == Role.CUSTOMER and not user.prison_id:
        return redirect("dashboard:profile")
    if user.role in (Role.CUSTOMER, Role.PRISONER):
        return redirect("dashboard:messages")
    return redirect("dashboard:vetting")


def dashboard_redirect(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return _redirect_after_login(request.user)


@messaging_dashboard_required
@require_http_methods(["GET", "POST"])
def profile(request):
    """Profile page. Shows all user info; editable fields for non-prisoners (name, email, and prison for customers)."""
    user = request.user
    if request.method == "POST":
        if user.role == Role.PRISONER:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Prisoner profiles are not editable.")
        update_fields = []
        first_name = (request.POST.get("first_name") or "").strip()
        last_name = (request.POST.get("last_name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        if user.first_name != first_name:
            user.first_name = first_name
            update_fields.append("first_name")
        if user.last_name != last_name:
            user.last_name = last_name
            update_fields.append("last_name")
        if user.email != email:
            user.email = email
            update_fields.append("email")
        if user.role == Role.CUSTOMER:
            prison_id = request.POST.get("prison")
            if prison_id:
                new_id = int(prison_id)
                if user.prison_id != new_id:
                    prison = get_object_or_404(Prison, pk=prison_id)
                    user.prison = prison
                    update_fields.append("prison_id")
        if update_fields:
            user.save(update_fields=update_fields)
        if user.role == Role.CUSTOMER and "prison_id" in update_fields:
            return redirect("dashboard:messages")
        return redirect("dashboard:profile")
    prisons = Prison.objects.order_by("name") if user.role == Role.CUSTOMER else None
    return render(
        request,
        "dashboard/profile.html",
        {"prisons": prisons},
    )


@staff_dashboard_required
@require_GET
def vetting_list(request):
    qs = Message.objects.select_related(
        "thread", "thread__prison", "sender", "receiver", "inspected_by"
    ).order_by("-created_at")
    if request.user.role != Role.SUPER_ADMIN and request.user.prison_id:
        qs = qs.filter(thread__prison_id=request.user.prison_id)
    if request.GET.get("uninspected") == "1":
        qs = qs.filter(inspected_at__isnull=True)
    return render(request, "dashboard/vetting.html", {"message_list": qs})


@staff_dashboard_required
@require_POST
def message_inspect(request, pk):
    message = get_object_or_404(Message, pk=pk)
    if request.user.role != Role.SUPER_ADMIN and request.user.prison_id:
        if message.thread.prison_id != request.user.prison_id:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Access denied.")
    message.inspected_at = timezone.now()
    message.inspected_by = request.user
    message.save(update_fields=["inspected_at", "inspected_by"])
    return render(request, "dashboard/partials/message_row.html", {"message": message})


def _get_messages_sidebar_data(request):
    """Return (threads, start_with) for the messages sidebar. Threads include last_message_body, last_message_at, unread_count."""
    latest_message = Message.objects.filter(thread=OuterRef("pk")).order_by("-created_at")
    unread_filter = Q(messages__receiver=request.user, messages__read_at__isnull=True)
    threads_base = Thread.objects.annotate(
        unread_count=Count("messages", filter=unread_filter),
        last_message_body=Subquery(latest_message.values("body")[:1]),
        last_message_at=Subquery(latest_message.values("created_at")[:1]),
    )
    if request.user.role == Role.CUSTOMER:
        threads = (
            threads_base.filter(customer=request.user, prison=request.user.prison)
            .select_related("customer", "prisoner", "prison")
            .order_by("-updated_at")
        )
        allowed = CustomerRecipient.objects.filter(
            customer=request.user, prisoner__prison=request.user.prison
        ).select_related("prisoner")
        prisoner_ids_with_thread = set(threads.values_list("prisoner_id", flat=True))
        start_with = [r for r in allowed if r.prisoner_id not in prisoner_ids_with_thread]
    else:
        threads = (
            threads_base.filter(prisoner=request.user)
            .select_related("customer", "prisoner", "prison")
            .order_by("-updated_at")
        )
        allowed = CustomerRecipient.objects.filter(prisoner=request.user).select_related("customer")
        customer_ids_with_thread = set(threads.values_list("customer_id", flat=True))
        start_with = [r for r in allowed if r.customer_id not in customer_ids_with_thread]
    return threads, start_with


@messaging_dashboard_required
@customer_prison_required
@require_GET
def thread_list(request):
    threads, start_with = _get_messages_sidebar_data(request)
    return render(
        request,
        "dashboard/messages.html",
        {"threads": threads, "start_with": start_with, "current_thread": None},
    )


def _mark_thread_messages_read(thread, user):
    """Mark all messages in thread where user is the receiver as read."""
    Message.objects.filter(
        thread=thread, receiver=user, read_at__isnull=True
    ).update(read_at=timezone.now())


@messaging_dashboard_required
@customer_prison_required
@require_GET
def thread_detail(request, pk):
    thread = get_object_or_404(Thread, pk=pk)
    if request.user not in (thread.customer, thread.prisoner):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")
    if request.user.role == Role.CUSTOMER and thread.prison_id != request.user.prison_id:
        return redirect("dashboard:profile")
    _mark_thread_messages_read(thread, request.user)
    messages = thread.messages.select_related("sender", "receiver").order_by("created_at")
    threads, start_with = _get_messages_sidebar_data(request)
    return render(
        request,
        "dashboard/thread_detail.html",
        {
            "thread": thread,
            "messages": messages,
            "threads": threads,
            "start_with": start_with,
            "current_thread": thread,
        },
    )


@messaging_dashboard_required
@customer_prison_required
@require_POST
def thread_send(request, pk):
    thread = get_object_or_404(Thread, pk=pk)
    if request.user not in (thread.customer, thread.prisoner):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")
    if request.user.role == Role.CUSTOMER and thread.prison_id != request.user.prison_id:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("This conversation is for a different prison. Change your prison in profile to continue.")
    _mark_thread_messages_read(thread, request.user)
    receiver = thread.prisoner if request.user == thread.customer else thread.customer
    body = (request.POST.get("body") or "").strip()
    if body:
        Message.objects.create(
            thread=thread,
            sender=request.user,
            receiver=receiver,
            body=body,
        )
    messages = thread.messages.select_related("sender", "receiver").order_by("created_at")
    return render(request, "dashboard/partials/message_list.html", {"messages": messages})


@messaging_dashboard_required
@customer_prison_required
@require_GET
def thread_start(request, user_pk):
    """Start or open a thread with the given user (user_pk = prisoner for customer, customer for prisoner)."""
    other_user = get_object_or_404(User, pk=user_pk)
    if request.user.role == Role.CUSTOMER:
        if other_user.role != Role.PRISONER:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Invalid recipient.")
        if other_user.prison_id != request.user.prison_id:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("That prisoner is at a different prison.")
        if not CustomerRecipient.objects.filter(customer=request.user, prisoner=other_user).exists():
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Not allowed.")
        thread = Thread.get_or_create_thread(request.user, other_user)
    else:
        if other_user.role != Role.CUSTOMER:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Invalid recipient.")
        if not CustomerRecipient.objects.filter(customer=other_user, prisoner=request.user).exists():
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Not allowed.")
        thread = Thread.get_or_create_thread(other_user, request.user)
    return redirect("dashboard:thread_detail", pk=thread.pk)


@messaging_dashboard_required
@customer_prison_required
@require_http_methods(["GET", "POST"])
def add_recipient(request):
    """Customers can add a recipient by prisoner number (scoped to their prison)."""
    if request.user.role != Role.CUSTOMER:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Only customers can add recipients.")
    error = None
    if request.method == "POST":
        raw = (request.POST.get("prisoner_number") or "").strip().upper()
        if not raw:
            error = "Enter a prisoner number."
        else:
            prisoner = User.objects.filter(
                role=Role.PRISONER,
                prisoner_number=raw,
                prison=request.user.prison,
            ).first()
            if not prisoner:
                error = "No prisoner found with that number at your selected prison."
            elif CustomerRecipient.objects.filter(
                customer=request.user,
                prisoner=prisoner,
            ).exists():
                error = "That recipient is already in your list."
            else:
                CustomerRecipient.objects.create(customer=request.user, prisoner=prisoner)
                return redirect("dashboard:messages")
    return render(
        request,
        "dashboard/add_recipient.html",
        {"error": error},
    )


@messaging_dashboard_required
@customer_prison_required
@require_GET
def thread_messages_partial(request, pk):
    thread = get_object_or_404(Thread, pk=pk)
    if request.user not in (thread.customer, thread.prisoner):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")
    if request.user.role == Role.CUSTOMER and thread.prison_id != request.user.prison_id:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")
    _mark_thread_messages_read(thread, request.user)
    messages = thread.messages.select_related("sender", "receiver").order_by("created_at")
    return render(request, "dashboard/partials/message_list.html", {"messages": messages})
