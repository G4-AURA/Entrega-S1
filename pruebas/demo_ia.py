#!/usr/bin/env python3
"""
Tarea 6.1 — demo_ia.py
- Llama a Gemini (API key en .env)
- Pide EXCLUSIVAMENTE JSON con estructura: RUTA + PARADAS
- Valida estructura mínima y lo guarda opcionalmente
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

from dotenv import load_dotenv
from google import genai


REQUIRED_RUTA_FIELDS = [
    "titulo",
    "descripcion",
    "duracion_horas",
    "num_personas",
    "nivel_exigencia",
    "mood",
    "es_generada_ia",
    "paradas",
]

REQUIRED_PARADA_FIELDS = ["orden", "nombre", "coordenadas"]

REQUIRED_COORD_FIELDS = ["lat", "lon"]


def build_prompt(ciudad: str, duracion_horas: float, num_personas: int, nivel_exigencia: str, mood: str) -> str:
    # Nota: GeoDjango PointField suele representarse como (lon, lat) internamente,
    # pero aquí devolvemos coordenadas como {lat, lon} para que sea claro y luego lo adaptáis al PointField.
    return f"""
Eres un generador de rutas turísticas para guías.
Genera una RUTA en {ciudad} con:
- duracion_horas: {duracion_horas}
- num_personas: {num_personas}
- nivel_exigencia: {nivel_exigencia}  (solo: bajo|medio|alto)
- mood: {mood}

Devuelve EXCLUSIVAMENTE un JSON válido (sin texto extra) con esta estructura EXACTA:

{{
  "titulo": "string",
  "descripcion": "string",
  "duracion_horas": number,
  "num_personas": integer,
  "nivel_exigencia": "bajo|medio|alto",
  "mood": "string",
  "es_generada_ia": true,
  "paradas": [
    {{
      "orden": integer,
      "nombre": "string",
      "coordenadas": {{ "lat": number, "lon": number }}
    }}
  ]
}}

Reglas:
- Incluye 3 a 6 paradas.
- Coordenadas reales aproximadas dentro de {ciudad}.
- No inventes campos fuera de los especificados.
""".strip()


def extract_json(text: str) -> Dict[str, Any]:
    """
    Gemini puede devolver JSON puro, o a veces envolverlo en ```json ... ```
    Esta función intenta extraerlo de forma robusta.
    """
    t = text.strip()

    if t.startswith("```"):
        # elimina fences
        t = t.strip("`")
        # si venía como "json\n{...}"
        if "\n" in t:
            first_line, rest = t.split("\n", 1)
            if first_line.strip().lower() == "json":
                t = rest.strip()

    return json.loads(t)


def validate_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if not isinstance(payload, dict):
        return ["La respuesta no es un objeto JSON (dict)."]

    for f in REQUIRED_RUTA_FIELDS:
        if f not in payload:
            errors.append(f"Falta campo en RUTA: '{f}'")

    # tipos básicos
    if "duracion_horas" in payload and not isinstance(payload["duracion_horas"], (int, float)):
        errors.append("RUTA.duracion_horas debe ser number.")
    if "num_personas" in payload and not isinstance(payload["num_personas"], int):
        errors.append("RUTA.num_personas debe ser integer.")
    if "es_generada_ia" in payload and payload["es_generada_ia"] is not True:
        errors.append("RUTA.es_generada_ia debe ser true.")

    # paradas
    paradas = payload.get("paradas")
    if paradas is None:
        return errors
    if not isinstance(paradas, list):
        errors.append("RUTA.paradas debe ser una lista.")
        return errors

    for i, p in enumerate(paradas):
        if not isinstance(p, dict):
            errors.append(f"PARADA[{i}] no es un objeto.")
            continue
        for f in REQUIRED_PARADA_FIELDS:
            if f not in p:
                errors.append(f"Falta campo en PARADA[{i}]: '{f}'")

        coords = p.get("coordenadas")
        if not isinstance(coords, dict):
            errors.append(f"PARADA[{i}].coordenadas debe ser objeto {{lat, lon}}.")
            continue
        for cf in REQUIRED_COORD_FIELDS:
            if cf not in coords:
                errors.append(f"Falta campo en PARADA[{i}].coordenadas: '{cf}'")
        if "lat" in coords and not isinstance(coords["lat"], (int, float)):
            errors.append(f"PARADA[{i}].coordenadas.lat debe ser number.")
        if "lon" in coords and not isinstance(coords["lon"], (int, float)):
            errors.append(f"PARADA[{i}].coordenadas.lon debe ser number.")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemini-2.5-flash", help="Modelo Gemini (ej: gemini-2.5-flash)")
    parser.add_argument("--ciudad", default="Sevilla")
    parser.add_argument("--duracion_horas", type=float, default=3.0)
    parser.add_argument("--num_personas", type=int, default=5)
    parser.add_argument("--nivel_exigencia", default="medio", choices=["bajo", "medio", "alto"])
    parser.add_argument("--mood", default="historia")
    parser.add_argument("--save", default="", help="Ruta del archivo donde guardar el JSON (opcional)")
    args = parser.parse_args()

    load_dotenv()

    client = genai.Client()

    prompt = build_prompt(
        ciudad=args.ciudad,
        duracion_horas=args.duracion_horas,
        num_personas=args.num_personas,
        nivel_exigencia=args.nivel_exigencia,
        mood=args.mood,
    )

    response = client.models.generate_content(
        model=args.model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    if not getattr(response, "text", None):
        print("ERROR: respuesta vacía del modelo", file=sys.stderr)
        return 2

    raw = response.text
    try:
        payload = extract_json(raw)
    except Exception as e:
        print("❌ No pude parsear JSON. Texto recibido:", file=sys.stderr)
        print(raw, file=sys.stderr)
        print(f"\nError: {e}", file=sys.stderr)
        return 3

    errors = validate_payload(payload)
    if errors:
        print("❌ JSON inválido. Errores:")
        for err in errors:
            print(f" - {err}")
        print("\nJSON recibido:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 4

    print("✅ JSON válido. Resultado:\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    # ✅ Guardado automático en el mismo directorio que este script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    auto_path = os.path.join(script_dir, "demo_ia_resultado.json")
    with open(auto_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Guardado automático en: {auto_path}")

    # (Opcional) Guardado adicional donde indique el usuario
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"💾 Guardado adicional en: {args.save}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())