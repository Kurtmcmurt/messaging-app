from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard_redirect, name="index"),
    path("profile/", views.profile, name="profile"),
    path("vetting/", views.vetting_list, name="vetting"),
    path("vetting/message/<int:pk>/inspect/", views.message_inspect, name="message_inspect"),
    path("messages/", views.thread_list, name="messages"),
    path("recipients/add/", views.add_recipient, name="add_recipient"),
    path("start/<int:user_pk>/", views.thread_start, name="thread_start"),
    path("threads/<int:pk>/", views.thread_detail, name="thread_detail"),
    path("threads/<int:pk>/messages/", views.thread_messages_partial, name="thread_messages"),
    path("threads/<int:pk>/send/", views.thread_send, name="thread_send"),
]
