from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ExplainableCommonPasswordValidator(CommonPasswordValidator):
    """
    Reutiliza la detección estándar de Django para contraseñas comunes,
    pero devuelve un mensaje más explicativo para el usuario final.
    """

    def validate(self, password, user=None):
        try:
            super().validate(password, user=user)
        except ValidationError as exc:
            raise ValidationError(
                _(
                    "Esta contraseña es demasiado común. Se basa en compararla con "
                    "listados de contraseñas usadas frecuentemente y contraseñas "
                    "filtradas/comprometidas, por lo que resulta más fácil de adivinar "
                    "en ataques automáticos."
                ),
                code="password_too_common",
            ) from exc

    def get_help_text(self):
        return _(
            "Tu contraseña no debe ser una clave común. Evita palabras frecuentes, "
            "patrones simples y combinaciones predecibles."
        )
