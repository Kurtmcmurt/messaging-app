from django.contrib.auth import authenticate, login
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .decorators import messaging_dashboard_required, staff_dashboard_required
from .models import CustomerRecipient, Message, Role, Thread, User


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
    if user.role in (Role.CUSTOMER, Role.PRISONER):
        return redirect("dashboard:messages")
    return redirect("dashboard:vetting")


def dashboard_redirect(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return _redirect_after_login(request.user)


@staff_dashboard_required
@require_GET
def vetting_list(request):
    qs = Message.objects.select_related(
        "thread", "sender", "receiver", "inspected_by"
    ).order_by("-created_at")
    if request.GET.get("uninspected") == "1":
        qs = qs.filter(inspected_at__isnull=True)
    return render(request, "dashboard/vetting.html", {"message_list": qs})


@staff_dashboard_required
@require_POST
def message_inspect(request, pk):
    message = get_object_or_404(Message, pk=pk)
    message.inspected_at = timezone.now()
    message.inspected_by = request.user
    message.save(update_fields=["inspected_at", "inspected_by"])
    return render(request, "dashboard/partials/message_row.html", {"message": message})


@messaging_dashboard_required
@require_GET
def thread_list(request):
    if request.user.role == Role.CUSTOMER:
        threads = Thread.objects.filter(customer=request.user).order_by("-updated_at")
        allowed = CustomerRecipient.objects.filter(customer=request.user).select_related("prisoner")
        prisoner_ids_with_thread = set(threads.values_list("prisoner_id", flat=True))
        start_with = [r for r in allowed if r.prisoner_id not in prisoner_ids_with_thread]
    else:
        threads = Thread.objects.filter(prisoner=request.user).order_by("-updated_at")
        allowed = CustomerRecipient.objects.filter(prisoner=request.user).select_related("customer")
        customer_ids_with_thread = set(threads.values_list("customer_id", flat=True))
        start_with = [r for r in allowed if r.customer_id not in customer_ids_with_thread]
    return render(
        request,
        "dashboard/messages.html",
        {"threads": threads, "start_with": start_with},
    )


@messaging_dashboard_required
@require_GET
def thread_detail(request, pk):
    thread = get_object_or_404(Thread, pk=pk)
    if request.user not in (thread.customer, thread.prisoner):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")
    messages = thread.messages.select_related("sender", "receiver").order_by("created_at")
    return render(
        request,
        "dashboard/thread_detail.html",
        {"thread": thread, "messages": messages},
    )


@messaging_dashboard_required
@require_POST
def thread_send(request, pk):
    thread = get_object_or_404(Thread, pk=pk)
    if request.user not in (thread.customer, thread.prisoner):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")
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
@require_GET
def thread_start(request, user_pk):
    """Start or open a thread with the given user (user_pk = prisoner for customer, customer for prisoner)."""
    other_user = get_object_or_404(User, pk=user_pk)
    if request.user.role == Role.CUSTOMER:
        if other_user.role != Role.PRISONER:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Invalid recipient.")
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


@require_http_methods(["GET", "POST"])
def add_recipient(request):
    """Customers can add a recipient by prisoner number."""
    if not request.user.is_authenticated:
        return redirect("login")
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
            ).first()
            if not prisoner:
                error = "No prisoner found with that number."
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
@require_GET
def thread_messages_partial(request, pk):
    thread = get_object_or_404(Thread, pk=pk)
    if request.user not in (thread.customer, thread.prisoner):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Access denied.")
    messages = thread.messages.select_related("sender", "receiver").order_by("created_at")
    return render(request, "dashboard/partials/message_list.html", {"messages": messages})
