from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegistroUsuarioForm(UserCreationForm):
    """
    FORMULARIO PARA REGISTRAR USUARIOS
    """

    email = forms.EmailField(
        required=True,
        label="Correo electrónico",
        error_messages={
            "required": "El correo electrónico es obligatorio.",
            "invalid": "Introduce un correo electrónico válido.",
        },
    )
    first_name = forms.CharField(
        required=True,
        label="Nombre",
        max_length=150,
        error_messages={"required": "El nombre es obligatorio."},
    )
    last_name = forms.CharField(
        required=True,
        label="Apellidos",
        max_length=150,
        error_messages={"required": "Los apellidos son obligatorios."},
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ("email", "first_name", "last_name")

    def clean_email(self):
        """Garantiza unicidad del email ignorando mayúsculas/minúsculas."""
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            return email

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo electrónico.")

        return email