import os
import django
import sys
import requests
import json

# Setup Django
sys.path.append('/Users/marioreyesapresa/Desktop/Entrega-S1')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings

api_key = settings.GEMINI_API_KEY
model_name = "gemini-2.5-flash"
# USAMOS v1beta y snake_case para compatibilidad total con REST
url = f'https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}'
headers = {'Content-Type': 'application/json'}
payload = {
    'contents': [{'parts': [{'text': 'Dame el nombre de 1 parque en Sevilla en JSON: {"nombre": "..."}'}]}],
    'generation_config': {'response_mime_type': 'application/json'},
}

print(f"Testing Gemini 2.5 at {url}...")
try:
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"Response Body: {response.text}")
    else:
        print(f"SUCCESS: {response.json()}")
except Exception as e:
    print(f"FAILED: {e}")
