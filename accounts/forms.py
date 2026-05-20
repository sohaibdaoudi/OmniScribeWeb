from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "class": "auth-input",
                "placeholder": "Choose a username",
                "autocomplete": "username",
                "autofocus": "autofocus",
                "aria-describedby": "username-rules",
            }
        )
        self.fields["email"].widget.attrs.update(
            {
                "class": "auth-input",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        )
        self.fields["password1"].widget.attrs.update(
            {
                "class": "auth-input",
                "placeholder": "Create a password",
                "autocomplete": "new-password",
                "aria-describedby": "password-rules",
            }
        )
        self.fields["password2"].widget.attrs.update(
            {
                "class": "auth-input",
                "placeholder": "Re-enter your password",
                "autocomplete": "new-password",
                "aria-describedby": "confirm-rules",
            }
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={"autofocus": True}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "class": "auth-input",
                "placeholder": "Your username",
                "autocomplete": "username",
                "autofocus": "autofocus",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": "auth-input",
                "placeholder": "Your password",
                "autocomplete": "current-password",
            }
        )
