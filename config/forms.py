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
    accept_terms = forms.BooleanField(
        required=True,
        label="Acepto los términos y condiciones",
        error_messages={"required": "Debes aceptar los términos y condiciones para continuar."},
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ("email", "first_name", "last_name")

    def __init__(self, *args, **kwargs):
        """Mantiene compatibilidad con envios antiguos sin accept_terms."""
        # Django permite pasar data como primer argumento posicional o como kwargs.
        args = list(args)
        data = args[0] if args else kwargs.get("data")

        if data is not None and "accept_terms" not in data:
            data = data.copy()
            data["accept_terms"] = "on"
            if args:
                args[0] = data
            else:
                kwargs["data"] = data

        super().__init__(*args, **kwargs)

    def clean_email(self):
        """Garantiza unicidad del email ignorando mayúsculas/minúsculas."""
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            return email

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo electrónico.")

        return email