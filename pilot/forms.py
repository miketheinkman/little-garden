from django import forms
from django.contrib.auth.forms import UserCreationForm


class ParentSignupForm(UserCreationForm):
    email = forms.EmailField(label="Parent recovery email", max_length=254)

    class Meta(UserCreationForm.Meta):
        fields = ("username", "email")


class RecoveryEmailForm(forms.Form):
    email = forms.EmailField(label="Parent recovery email", max_length=254)
    password = forms.CharField(label="Current password", widget=forms.PasswordInput)
