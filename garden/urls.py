from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth import views as auth
from django.urls import path
from django.views.generic import TemplateView
from pilot import views

urlpatterns = [
    path("", views.home, name="home"),
    path("mission/", TemplateView.as_view(template_name="mission.html"), name="mission"),
    path("signup/", views.signup, name="signup"),
    path("login/", LoginView.as_view(template_name="account.html"), name="login"),
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
    path("play/<int:pk>/", views.play, name="play"),
]
