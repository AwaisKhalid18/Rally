"""Platform routes.

`register`, `sign_in` and `verify_email` are the only names in
`rally.core.pipeline.middleware.PUBLIC_URL_NAMES`. Every other route needs a session.
`verify_email` arrives with slice S2.
"""
from django.urls import path

from rally.core.web import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("sign-in/", views.sign_in, name="sign_in"),
    path("sign-out/", views.sign_out, name="sign_out"),
]
