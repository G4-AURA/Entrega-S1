import os
import re

file_path = 'creacion/services.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Modification 1: _construir_prompt_regeneracion_pois
content = content.replace(
'''        Responde ÚNICAMENTE JSON válido:
        [
            {"nombre": "Nombre del sitio", "coords": [lat, lon], "desc": "Breve descripción del lugar"}
        ]''',
'''        Responde ÚNICAMENTE JSON válido:
        [
            {"nombre": "Nombre del sitio", "ciudad": "Ciudad del sitio", "tipo_poi": "Categoría OSM del sitio", "desc": "Breve descripción del lugar"}
        ]'''
)

# Modification 2: _solicitar_pois_adicionales_para_ruta_ia
old_solicitar_adicional = '''    if isinstance(respuesta, list):
        return respuesta'''
new_solicitar_adicional = '''    if isinstance(respuesta, list):
        try:
            from allowList.services import resolver_poi
            candidatos = []
            ciudad = str(datos.get('ciudad') or '')
            for item in respuesta:
                if not isinstance(item, dict):
                    continue
                poi_resuelto = resolver_poi(
                    item.get("nombre", ""),
                    item.get("ciudad", ciudad),
                    item.get("tipo_poi", "")
                )
                if poi_resuelto is not None:
                    candidatos.append({
                        "nombre": poi_resuelto.nombre,
                        "coords": [float(poi_resuelto.lat), float(poi_resuelto.lon)],
                        "desc": item.get("desc", ""),
                        "categoria": str(getattr(poi_resuelto, "categoria", item.get("tipo_poi", ""))),
                    })
            if candidatos:
                return candidatos[:cantidad]
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning('Error al resolver POI: %s', e)
'''
content = content.replace(old_solicitar_adicional, new_solicitar_adicional)


# Modification 3: _construir_prompt_candidatos_paradas
content = content.replace(
'''        Responde únicamente JSON válido (sin texto adicional) como lista de objetos con esta estructura:
        [
          {
            "nombre": "Nombre de la parada",
            "coordenadas": [lat, lon],
            "categoria": "Categoría turística",
            "nivel_confianza": 0.0,
            "justificacion": "Motivo breve de por qué encaja en la ruta"
            "descripcion": "Breve descripción del lugar para el turista (máximo 60 palabras)"
          }
        ]''',
'''        Responde únicamente JSON válido (sin texto adicional) como lista de objetos con esta estructura:
        [
          {
            "nombre": "Nombre de la parada",
            "ciudad": "Ciudad sugerida",
            "tipo_poi": "Categoría turística / OSM",
            "nivel_confianza": 0.0,
            "justificacion": "Motivo breve de por qué encaja en la ruta",
            "descripcion": "Breve descripción del lugar para el turista (máximo 60 palabras)"
          }
        ]'''
)

# Modification 4: _solicitar_candidatos_paradas_ia
old_solicitar_candidatos = '''    candidatos_ia = _extraer_lista_desde_respuesta_ia(respuesta)
    if candidatos_ia:
        return candidatos_ia'''
new_solicitar_candidatos = '''    candidatos_ia = _extraer_lista_desde_respuesta_ia(respuesta)
    if candidatos_ia:
        try:
            from allowList.services import resolver_poi
            validados = []
            for item in candidatos_ia:
                if not isinstance(item, dict):
                    continue
                poi_resuelto = resolver_poi(
                    item.get("nombre", ""),
                    item.get("ciudad", ciudad_contexto),
                    item.get("tipo_poi", item.get("categoria", ""))
                )
                if poi_resuelto is not None:
                    item['coordenadas'] = [float(poi_resuelto.lat), float(poi_resuelto.lon)]
                    item['nombre'] = poi_resuelto.nombre
                    item['categoria'] = str(getattr(poi_resuelto, "categoria", item.get("tipo_poi", "")))
                    validados.append(item)
            if validados:
                return validados[:cantidad]
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning('Error al resolver candidatos IA: %s', e)
'''
content = content.replace(old_solicitar_candidatos, new_solicitar_candidatos)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("services.py patched!")

# NOW patch langgraph/nodes/generacion.py
file_path = 'creacion/langgraph/nodes/generacion.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
'''        Responde ÚNICAMENTE con un JSON válido (sin texto extra) con esta estructura:
        [
            {"nombre": "Nombre del sitio", "coords": [lat, lon], "desc": "Breve descripción del lugar", "categoria": "Categoría"}
        ]''',
'''        Responde ÚNICAMENTE con un JSON válido (sin texto extra) con esta estructura:
        [
            {"nombre": "Nombre del sitio", "ciudad": "Ciudad del sitio", "tipo_poi": "Categoría OSM del sitio", "desc": "Breve descripción del lugar"}
        ]'''
)

old_llamar_gemini = "pois_gemini = _llamar_gemini_para_complemento(datos, faltan, nombres_excluidos)"
new_llamar_gemini = '''pois_gemini_raw = _llamar_gemini_para_complemento(datos, faltan, nombres_excluidos)
            if isinstance(pois_gemini_raw, list):
                from allowList.services import resolver_poi
                pois_gemini = []
                for item in pois_gemini_raw:
                    if not isinstance(item, dict): continue
                    res_poi = resolver_poi(
                        item.get("nombre", ""),
                        item.get("ciudad", str(datos.get("ciudad") or "")),
                        item.get("tipo_poi", "")
                    )
                    if res_poi is not None:
                        pois_gemini.append({
                            "nombre": res_poi.nombre,
                            "coords": [float(res_poi.lat), float(res_poi.lon)],
                            "desc": item.get("desc", ""),
                            "categoria": str(getattr(res_poi, "categoria", item.get("tipo_poi", "")))
                        })
            else:
                pois_gemini = pois_gemini_raw'''
content = content.replace(old_llamar_gemini, new_llamar_gemini)

old_llamar_gemini_2 = '''    logger.info("AllowList vacía para ciudad='%s'; delegando generación completa a Gemini.", ciudad)
    pois_crudos = llamar_gemini(prompt)
    if not isinstance(pois_crudos, list):'''
new_llamar_gemini_2 = '''    logger.info("AllowList vacía para ciudad='%s'; delegando generación completa a Gemini.", ciudad)
    pois_gemini_raw = llamar_gemini(prompt)
    
    if isinstance(pois_gemini_raw, list):
        from allowList.services import resolver_poi
        pois_crudos = []
        for item in pois_gemini_raw:
            if not isinstance(item, dict): continue
            res_poi = resolver_poi(
                item.get("nombre", ""),
                item.get("ciudad", ciudad),
                item.get("tipo_poi", "")
            )
            if res_poi is not None:
                pois_crudos.append({
                    "nombre": res_poi.nombre,
                    "coords": [float(res_poi.lat), float(res_poi.lon)],
                    "desc": item.get("desc", ""),
                    "categoria": str(getattr(res_poi, "categoria", item.get("tipo_poi", "")))
                })
    else:
        pois_crudos = pois_gemini_raw

    if not isinstance(pois_crudos, list):'''
content = content.replace(old_llamar_gemini_2, new_llamar_gemini_2)


with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("generacion.py patched!")

