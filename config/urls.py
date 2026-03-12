from django.contrib.admin import site as admin_site
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("", core_views.home, name="home"),
    path("about/", core_views.about, name="about"),
    path("accounts/login/", core_views.login_view, name="login"),
    path("accounts/logout/", LogoutView.as_view(next_page="/"), name="logout"),
    path("dashboard/", include("core.urls")),
    path("admin/", admin_site.urls),
]
