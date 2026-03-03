from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class RegistroUsuarioForm(UserCreationForm):
    '''
    FORMULARIO PARA REGISTRAR USUARIOS
    '''
    # Definimos las opciones para el tipo de cuenta
    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name') # OPCIONALES