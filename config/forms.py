from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class RegistroUsuarioForm(UserCreationForm):
    '''
    FORMULARIO PARA REGISTRAR USUARIOS
    '''
    # Definimos las opciones para el tipo de cuenta
    OPCIONES_CUENTA = [
        ('guia', 'Guía Turístico'),
        ('turista', 'Turista'),
    ]
    
    tipo_cuenta = forms.ChoiceField(
        choices=OPCIONES_CUENTA, 
        widget=forms.RadioSelect,
        label="¿Qué tipo de cuenta quieres crear?"
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name') # OPCIONALES