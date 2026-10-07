from django.urls import path
from . import views

urlpatterns = [
    path("auth/team/login", views.team_login, name="team-login"),
    path("auth/admin/login", views.admin_login, name="admin-login"),
    path("auth/volunteer/login", views.volunteer_login, name="volunteer-login"),
    path("admin/volunteers", views.create_volunteer, name="create-volunteer"),
    path("auth/logout", views.logout, name="logout"),
    path("auth/me", views.current_user, name="current-user"),
]
