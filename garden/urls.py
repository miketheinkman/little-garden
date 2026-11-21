from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from pilot import views

urlpatterns = [
    path("", views.home, name="home"),
    path("signup/", views.signup, name="signup"),
    path("login/", LoginView.as_view(template_name="account.html"), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("children/add/", views.add_child, name="add_child"),
    path("children/<int:pk>/", views.manage, name="manage"),
    path("play/<int:pk>/", views.play, name="play"),
]
