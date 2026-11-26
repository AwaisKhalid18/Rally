"""Input shape only.

The credential policy — what makes an email address valid, how long a password must be,
whether an address is already taken — belongs to M1 and is applied by its facade
(rule 14). These forms collect fields and re-display them; they decide nothing.
"""
from __future__ import annotations

from django import forms


class RegisterForm(forms.Form):
    # Deliberately a CharField, not an EmailField: the address format is M1's rule and
    # would otherwise be enforced in two places.
    email = forms.CharField(required=False, label="Email address", widget=forms.TextInput(attrs={"autocomplete": "email"}))
    password = forms.CharField(required=False, label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}, render_value=False))

    def apply_errors(self, errors: dict[str, str]) -> None:
        """Attach the messages M1 returned to their fields."""
        for field_name, message in errors.items():
            if field_name in self.fields:
                self.add_error(field_name, message)
            else:
                self.add_error(None, message)


class SignInForm(forms.Form):
    email = forms.CharField(required=False, label="Email address", widget=forms.TextInput(attrs={"autocomplete": "email"}))
    password = forms.CharField(required=False, label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}, render_value=False))
