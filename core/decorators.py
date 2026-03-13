from functools import wraps

from django.shortcuts import redirect

from .models import Role


def staff_dashboard_required(view_func):
    """Restrict view to OFFICER, ADMIN, SUPER_ADMIN."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if request.user.role not in (Role.OFFICER, Role.ADMIN, Role.SUPER_ADMIN):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Access denied.")
        return view_func(request, *args, **kwargs)

    return wrapper


def messaging_dashboard_required(view_func):
    """Restrict view to CUSTOMER and PRISONER."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if request.user.role not in (Role.CUSTOMER, Role.PRISONER):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Access denied.")
        return view_func(request, *args, **kwargs)

    return wrapper


def customer_prison_required(view_func):
    """Redirect CUSTOMER to profile if they have not selected a prison."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.role == Role.CUSTOMER and not request.user.prison_id:
            return redirect("dashboard:profile")
        return view_func(request, *args, **kwargs)

    return wrapper
