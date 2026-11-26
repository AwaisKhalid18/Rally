"""Platform routes.

`register`, `sign_in` and `verify_email` are the only names in
`rally.core.pipeline.middleware.PUBLIC_URL_NAMES`. Every other route needs a session.
"""
from django.urls import path

from rally.core.web import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("sign-in/", views.sign_in, name="sign_in"),
    path("sign-out/", views.sign_out, name="sign_out"),
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("profile/", views.profile, name="profile"),
    path("players/<int:account_id>/", views.player_profile, name="player_profile"),
    path("availability/", views.availability, name="availability"),
    path("availability/<int:slot_id>/", views.availability_edit, name="availability_edit"),
    path("availability/<int:slot_id>/delete/", views.availability_delete, name="availability_delete"),
    path("search/", views.search, name="search"),
]
