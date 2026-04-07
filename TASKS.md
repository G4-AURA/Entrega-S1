# TASKS

## Sprint 2

- [x] s2.2-24: Implementar almacenamiento del estado de cada sesion de generacion de rutas con IA usando checkpoints.
- [x] s2.2-29: Implementar caché de rutas de tour con Redis para carga rápida en guía y turistas.

## Quick Task 260407-wh8

- [x] Issue 168: pruebas de integración del endpoint tours:obtener_curiosidad_parada completadas (retorna curiosidad existente, genera nueva cuando falta y valida contrato JSON) en tours/tests/test_live_curiosidades.py.
	Evidencia: .\\env\\Scripts\\python.exe manage.py test tours.tests.test_live_curiosidades -v 2
- [x] Issue 223: pruebas de integración de AllowList API completadas en allowList/tests_integration.py.
	Evidencia: .\\env\\Scripts\\python.exe manage.py test allowList.tests_integration -v 2
- [x] Issue 146: pruebas de integración de recalculo GraphHopper completadas (envío de coordenadas, recepción de geometría y persistencia de navegación) en rutas/tests/test_graphhopper_integration.py.
	Evidencia: .\\env\\Scripts\\python.exe manage.py test rutas.tests.test_graphhopper_integration -v 2
