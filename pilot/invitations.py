import hashlib

from django import forms
from django.contrib.auth import get_user_model, login
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import ParentSignupForm
from .models import ParentInvitation


class InvitationCodeForm(forms.Form):
    code = forms.CharField(label="Invitation code", max_length=64, widget=forms.TextInput(
        attrs={"autocomplete": "one-time-code", "autocapitalize": "none", "spellcheck": "false"}))


def code_digest(code):
    return hashlib.sha256(code.encode()).hexdigest()


def invite_gate(request, *, expired=False):
    form = InvitationCodeForm(request.POST if request.method == "POST" and not expired else None)
    if form.is_bound and form.is_valid():
        digest = code_digest(form.cleaned_data["code"])
        if ParentInvitation.available().filter(code_digest=digest).exists():
            request.session.cycle_key()
            request.session["parent_invitation"] = digest
            return redirect("signup")
        form.add_error("code", "That code is invalid or has expired. Check your latest invitation.")
    return render(request, "invite_gate.html", {"form": form, "expired": expired})


def invited_signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    digest = request.session.get("parent_invitation")
    if not digest:
        return invite_gate(request)
    invitation = ParentInvitation.available().filter(code_digest=digest).first()
    if invitation is None:
        request.session.pop("parent_invitation", None)
        return invite_gate(request, expired=True)

    form = ParentSignupForm(request.POST if request.method == "POST" else None, initial={"email": invitation.email})
    # Django's disabled field uses its server-side initial value even on a forged POST.
    form.fields["email"].disabled = True
    form.fields["email"].help_text = "Your invitation and password resets use this address."
    if form.is_bound and form.is_valid():
        try:
            with transaction.atomic():
                claimed = ParentInvitation.available().filter(code_digest=digest).update(used_at=timezone.now())
                if not claimed:
                    request.session.pop("parent_invitation", None)
                    return invite_gate(request, expired=True)
                if get_user_model().objects.filter(email__iexact=invitation.email).exists():
                    return redirect("login")
                parent = form.save()
        except IntegrityError:
            if not get_user_model().objects.filter(username=form.cleaned_data["username"]).exists():
                raise
            form.add_error("username", "This username is already taken.")
        else:
            request.session.flush()
            login(request, parent)
            return redirect("home")
    return render(request, "account.html", {"form": form, "heading": "Create a parent account"})
