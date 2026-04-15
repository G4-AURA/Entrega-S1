import os
import django
import sys

# Setup Django
sys.path.append('/Users/marioreyesapresa/Desktop/Entrega-S1')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from creacion.langgraph.utils import llamar_gemini

print("Testing Gemini 2.5 connectivity...")
try:
    res = llamar_gemini("Dime el nombre de un restaurante famoso en Sevilla. Responde solo el nombre.")
    print(f"SUCCESS: {res}")
except Exception as e:
    print(f"FAILED: {e}")
