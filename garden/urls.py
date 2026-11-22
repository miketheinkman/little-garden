from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth import views as auth
from django.urls import path
from django.views.generic import TemplateView
from pilot import coview, views
from pilot.dashboard import dashboard

urlpatterns = [
    path("", views.home, name="home"),
    path("welcome/", TemplateView.as_view(template_name="welcome.html"), name="welcome"),
    path("mission/", TemplateView.as_view(template_name="mission.html"), name="mission"),
    path("signup/", views.signup, name="signup"),
    path("login/", LoginView.as_view(template_name="account.html"), name="login"),
    path("co-view/", coview.room, name="coview"),
    path("co-view/watch/", coview.watch, name="coview_watch"),
    path("co-view/share/<int:pk>/", coview.broadcast, name="coview_broadcast"),
    path("dashboard/", dashboard, name="dashboard"),
    path("feedback/preferences/", views.feedback_preferences, name="feedback_preferences"),
    path("feedback/", views.feedback_history, name="feedback_history"),
    path("account/email/", views.recovery_email, name="recovery_email"),
    path("password/reset/", auth.PasswordResetView.as_view(
        template_name="recovery.html", email_template_name="recovery_email.txt",
        subject_template_name="recovery_subject.txt",
        extra_context={"heading": "Reset your password", "button": "Request reset link"},
    ), name="password_reset"),
    path("password/requested/", auth.PasswordResetDoneView.as_view(
        template_name="recovery.html", extra_context={
            "heading": "Request received", "note": "If a parent account matches that address, a reset message will be prepared. On a local pilot without mail delivery, ask the host for the message."},
    ), name="password_reset_done"),
    path("password/choose/<uidb64>/<token>/", auth.PasswordResetConfirmView.as_view(
        template_name="recovery.html", extra_context={"heading": "Choose a new password", "button": "Save password"},
    ), name="password_reset_confirm"),
    path("password/updated/", auth.PasswordResetCompleteView.as_view(
        template_name="recovery.html", extra_context={"heading": "Password updated", "note": "Sign in with your new password."},
    ), name="password_reset_complete"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("children/<int:pk>/library/<slug:key>/preview/<int:step>/", views.preview, name="preview"),
    path("children/<int:pk>/library/", views.library, name="library"),
    path("children/add/", views.add_child, name="add_child"),
    path("children/<int:pk>/", views.manage, name="manage"),
    path("suggestions/start/", views.start_suggestion, name="start_suggestion"),
    path("play/<int:pk>/", views.play, name="play"),
]
