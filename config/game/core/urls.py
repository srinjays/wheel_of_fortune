from django.urls import path
from . import views

urlpatterns = [
    path("health", views.health, name="api-health"),
    path("csrf", views.csrf_token, name="api-csrf"),
]
