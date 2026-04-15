from django import forms
from django.contrib.auth.models import User


class EditarPerfilForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellidos',
            'email': 'Correo electrónico',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 150}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 150}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'maxlength': 254}),
        }

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if not email:
            raise forms.ValidationError('El correo electrónico es obligatorio.')

        qs = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('Ya existe una cuenta con este correo electrónico.')

        return email
