# S3.1-01 — Matriz de Tiers por Funcionalidad (Freemium/Premium)

## 1. Metadatos del Documento
- **Proyecto:** AURA
- **Sprint:** S3.1
- **ID de tarea:** S3.1-01
- **Versión del documento:** v0.1
- **Estado:** Borrador | En revisión | Aprobado
- **Autor(es):** Max Cameron Corti
- **Fecha:** 29/03/26
- **Aprobado por:**

---

## 2. Objetivo
Definir una política operativa de producto por endpoint para los planes `Freemium` y `Premium`, traduciendo las decisiones de negocio en:

- permisos por funcionalidad,
- límites cuantitativos aplicables,
- comportamiento cuando se supera un límite,
- y contrato de errores para frontend y backend.

Este documento será la fuente de verdad para implementar guardas de tier en servicios, vistas y tests.

---

## 3. Definiciones
- **Freemium:** plan base con límites estrictos en volumen, capacidad y funcionalidades avanzadas.
- **Premium:** plan ampliado con límites superiores y acceso a funciones avanzadas.
- **Límite duro:** al superar el límite, la operación se bloquea (`403` o `429`).
- **Límite blando:** la operación se permite, pero se devuelve advertencia para UI.
- **Ruta simultánea:** ruta activa disponible en catálogo para operar (crear sesión, editar o reutilizar).
- **Periodo de cómputo de límites:**
`por_mes` (reinicio mensual), `por_ruta`, `por_sesion` o `simultaneo`.

---

## 4. Reglas Globales de Tiers
- **R1 (Plan por defecto):** todo guía nuevo comienza como `Freemium`.
- **R2 (Denegación por defecto):** cualquier funcionalidad no marcada explícitamente para `Freemium` se considera bloqueada para ese plan.
- **R3 (Consumo atómico):** los contadores se consumen solo en operaciones exitosas.
- **R4 (Mensajería consistente):** todo bloqueo por tier debe devolver código interno (`TIER_*`) y mensaje orientado a upgrade.
- **R5 (Visibilidad):** frontend siempre debe mostrar plan actual y consumo del recurso limitado cuando aplique.
- **R6 (No bypass):** validación de tier se realiza en backend, nunca solo en frontend.

---

## 5. Matriz de Reglas por Endpoint

| ID Regla | Módulo | Endpoint | Método | Funcionalidad | Freemium | Premium | Límite Freemium | Límite Premium | Error al exceder | Observaciones |
|---|---|---|---|---|---|---|---|---|---|---|
| TR-001 | `creacion` | `/crear-ruta/api/guardar-manual/` | `POST` | Crear ruta manual | Permitido | Permitido | Máx. `1` ruta simultánea | Máx. `10` rutas simultáneas | `429 TIER_LIMIT_REACHED` | Freemium puede crear ilimitadas si elimina la anterior |
| TR-002 | `creacion` | `/crear-ruta/api/generar/` | `POST` | Generar propuesta de ruta IA | Permitido | Permitido | `3/mes` + máx. `1` ruta simultánea | `10/mes` + máx. `10` rutas simultáneas | `429 TIER_LIMIT_REACHED` | Contador mensual de generaciones IA |
| TR-003 | `creacion` | `/crear-ruta/api/generar/confirmar/` | `POST` | Guardar ruta IA confirmada | Permitido | Permitido | Sujeto a TR-002 (simultáneas) | Sujeto a TR-002 (simultáneas) | `429 TIER_LIMIT_REACHED` | No guarda si supera cupo de rutas simultáneas |
| TR-004 | `creacion` | `/crear-ruta/api/rutas/<ruta_id>/paradas-ia/` | `POST` | Sustituir/añadir parada con IA | Permitido | Permitido | `3` usos por ruta IA y `9/mes` | `30/mes` | `429 TIER_LIMIT_REACHED` | Solo en rutas IA |
| TR-005 | `rutas` | `/catalogo/<ruta_id>/` | `POST` | Añadir parada manual a ruta | Permitido | Permitido | Máx. `5` paradas por ruta | Máx. `15` paradas por ruta | `429 TIER_LIMIT_REACHED` | Incluye creación y edición de orden |
| TR-006 | `rutas` | `/catalogo/<ruta_id>/` | `POST` | Etiquetas (`mood`) de ruta | Permitido con restricción | Permitido | Solo: `Historia`, `Naturaleza`, `Religioso y Espiritual`, `Arquitectura y Diseño` | Todas las etiquetas disponibles | `403 TIER_FORBIDDEN` | En Freemium se filtran etiquetas no permitidas |
| TR-007 | `tours` | `/tours/sesiones/crear/?ruta_id=<id>` | `GET` | Crear sesión de tour | Permitido con restricción | Permitido | 1 sesión activa por ruta | Múltiples sesiones por ruta | `429 TIER_LIMIT_REACHED` | Premium puede reutilizar la misma ruta para distintas sesiones |
| TR-008 | `tours` | `/tours/sesiones/<sesion_id>/participantes/` | `GET` | Capacidad de turistas por sesión | Permitido | Permitido | Máx. `15` turistas | Máx. `50` turistas | `429 TIER_LIMIT_REACHED` en alta de turista | El control se aplica en unión de turistas |
| TR-009 | `tours` | `/tours/live/<token>/` | `POST` | Unión de turista a sesión | Permitido con restricción | Permitido con restricción | Bloquea unión al llegar a 15 | Bloquea unión al llegar a 50 | `429 TIER_LIMIT_REACHED` | Mensaje claro al turista cuando está completa |
| TR-010 | `tours` | `/tours/sesiones/<sesion_id>/mensajes/enviar/` | `POST` | Tipo de chat en sesión | Solo chat común | Chat común o separado | Modo fijo `común` | Selector de modo (`común`/`separado`) | `403 TIER_FORBIDDEN` | Requiere campo de configuración de chat en sesión |
| TR-011 | `tours` | `/tours/sesiones/<sesion_id>/quedada/` | `POST` | Quedada programada con notificación y POI | No permitido | Permitido | Bloqueado | Habilitado | `403 TIER_FORBIDDEN` | Endpoint nuevo a implementar |
| TR-012 | `tours` | `/tours/sesiones/<sesion_id>/paradas/<parada_id>/curiosidad/` | `GET` | Mostrar curiosidad en sesión | Permitido con cupo | Ilimitado | Solo para `3` rutas (manual+mostrar) | Sin límite | `429 TIER_LIMIT_REACHED` | Cupo ligado a uso de curiosidades manuales |
| TR-013 | `rutas` | `/api/paradas/<parada_id>/curiosidad/` | `GET/POST/PUT` | Crear/editar curiosidad manual por parada | Permitido con cupo | Ilimitado | Solo para `3` rutas | Sin límite | `429 TIER_LIMIT_REACHED` | Incluye creación y edición |
| TR-014 | `creacion` | `/crear-ruta/api/generar/` (campo `deseos`) | `POST` | Restricciones/deseos del usuario | No permitido | Permitido (mejorado) | Bloquedo | Mejor calidad esperada | `200` con `warning` | Requisito pendiente de mejora funcional |

---

## 6. Catálogo de Códigos de Error de Tier
| Código interno | HTTP | Mensaje | Cuándo se devuelve | Acción esperada en frontend |
|---|---|---|---|---|
| `TIER_FORBIDDEN` | `403` | Esta funcionalidad está disponible solo en Premium | Freemium intenta una función exclusiva Premium | Mostrar CTA de upgrade |
| `TIER_LIMIT_REACHED` | `429` | Has alcanzado el límite de tu plan | Se supera cuota mensual/simultánea/por ruta | Mostrar consumo y fecha de reset |
| `TIER_CAPACITY_REACHED` | `429` | La sesión alcanzó su capacidad máxima | Se supera límite de turistas por sesión | Mostrar sesión completa |
| `TIER_PLAN_REQUIRED` | `403` | Necesitas un plan superior para continuar | Operación requiere Premium | Mostrar plan recomendado |
| `TIER_MISCONFIGURED` | `500` | Error de configuración de reglas de plan | Falta o inconsistencia de matriz en backend | Mostrar error genérico y registrar incidente |

---

## 7. Reglas de UX asociadas (Frontend)
- Mostrar badge visible del plan actual (`Freemium`/`Premium`) en header.
- Mostrar contadores de consumo: generaciones IA del mes, sustituciones IA del mes y rutas simultáneas. En vista nueva accesible desde el perfil o desde la alerta que salta con excepcion correspondiente.
- Deshabilitar acciones bloqueadas en UI, pero siempre validando en backend.
- Al recibir `TIER_FORBIDDEN` o `TIER_PLAN_REQUIRED`, abrir modal de upgrade con beneficio concreto.
- Al recibir `TIER_LIMIT_REACHED`, mostrar recurso agotado y cuándo se reinicia.
- En unión de turistas, mostrar mensaje específico para sesión llena (`TIER_CAPACITY_REACHED`).
- Para etiquetas restringidas en Freemium, ocultar o marcar como “Premium”.

---

## 8. Casos de Prueba de Verificación
| ID Test | Endpoint | Escenario | Tier | Resultado esperado |
|---|---|---|---|---|
| TT-001 | `/crear-ruta/api/guardar-manual/` | Freemium con 0 rutas simultáneas | Freemium | `200 OK` |
| TT-002 | `/crear-ruta/api/guardar-manual/` | Freemium con 1 ruta simultánea | Freemium | `429 TIER_LIMIT_REACHED` |
| TT-003 | `/crear-ruta/api/generar/` | 4ª generación IA mensual | Freemium | `429 TIER_LIMIT_REACHED` |
| TT-004 | `/crear-ruta/api/generar/` | 10ª generación IA mensual | Premium | `200 OK` |
| TT-005 | `/crear-ruta/api/rutas/<ruta_id>/paradas-ia/` | 4ª sustitución IA en la misma ruta | Freemium | `429 TIER_LIMIT_REACHED` |
| TT-006 | `/catalogo/<ruta_id>/` | Añadir 6ª parada | Freemium | `429 TIER_LIMIT_REACHED` |
| TT-007 | `/catalogo/<ruta_id>/` | Usar etiqueta no permitida | Freemium | `403 TIER_FORBIDDEN` |
| TT-008 | `/tours/live/<token>/` | Turista nº16 intenta unirse | Freemium | `429 TIER_CAPACITY_REACHED` |
| TT-009 | `/tours/sesiones/<id>/quedada/` | Crear quedada programada | Freemium | `403 TIER_FORBIDDEN` |
| TT-010 | `/tours/sesiones/<id>/quedada/` | Crear quedada programada | Premium | `200 OK` |
| TT-011 | `/api/paradas/<id>/curiosidad/` | 4ª ruta con curiosidad manual | Freemium | `429 TIER_LIMIT_REACHED` |
| TT-012 | `/tours/sesiones/<id>/mensajes/enviar/` | Configurar chat separado | Premium | `200 OK` |

---

## 9. Trazabilidad (Funcionalidad ↔ Regla ↔ Test)
| Funcionalidad | Regla(s) | Test(s) |
|---|---|---|
| Rutas manuales simultáneas | TR-001 | TT-001, TT-002 |
| Generación de rutas IA | TR-002, TR-003 | TT-003, TT-004 |
| Sustitución de parada con IA | TR-004 | TT-005 |
| Límite de paradas por ruta | TR-005 | TT-006 |
| Etiquetas permitidas por plan | TR-006 | TT-007 |
| Gestión de sesiones por ruta | TR-007 | TT-008 |
| Capacidad de turistas por sesión | TR-008, TR-009 | TT-008 |
| Tipo de chat (común/separado) | TR-010 | TT-012 |
| Quedada programada | TR-011 | TT-009, TT-010 |
| Curiosidades manuales/mostradas | TR-012, TR-013 | TT-011 |
| Campo deseos IA | TR-014 | TT-003, TT-004 |

---

## 10. Decisiones Abiertas
- [ ] Confirmar si el límite de sustitución IA en Freemium es `3/ruta` y además `9/mes` (doble condición).
- [ ] Confirmar definición exacta de “ruta simultánea” (activa, visible o no archivada).
- [ ] Cerrar el comportamiento de `deseos` para Premium (mejora real de calidad y medición).
- [ ] Definir política de downgrade Premium -> Freemium cuando supera límites actuales.
- [ ] Definir si la “sesión por tour” en Freemium bloquea también sesiones históricas cerradas.
- [ ] Definir si el cupo de curiosidades Freemium se resetea por mes o por vida de cuenta.

---

## 11. Historial de Cambios
| Versión | Fecha | Autor | Cambios |
|---|---|---|---|
| v0.1 | 29/03/26 | Max Cameron Corti | Plantilla inicial |
| v0.2 | 30/03/26 | Max Cameron Corti | Apartados 2-10 completados según AYUDA PARA MI |

## AYUDA PARA MI
| Func | TIER | Qué hacer con ello |
|---|---|---|
|   creacion manual   | Freemium  | 1 ruta simultanea, creacion ilimitada pero se tiene que eliminar la anterior    |
|   creacion manual   | Premium  | 10 ruta simultanea, creacion ilimitada    |
|   creacion con ia     |    Freemium      |   3 generaciones, 1 ruta simultanea     |
|   creacion con ia     |    Premium      |   10/mes generaciones, 10 ruta simultanea     |
|sesion|  Freemium|  Limite 15 turistas  |
|sesion|  Premium|  Limite 50 turistas  |
|sesion|  Freemium|  Una sesion por tour?  |
|sesion|  Premium|  Se podria guardar las tours para realizar varias sesiones?  |
|Sustituir parada con ia | Freemium | Se podria hacer 3 veces por cada ruta generada con ia (total 9)|
|Sustituir parada con ia | Premium | 30/mes|
|Paradas| Freemium |5 paradas maximo |
|Paraddas | Premium | 15 paradas maximo|
|Etiquetas | Freemium | Limitar las etiquetas (solo historia, naturaleza, religioso y espirtual, Arquitectura/Diseño)|
|Deseos |TOTAL| No sé quitarlo o incluirlo para Premium pero habra que mejorarlo mucho|
|Tipo de chat | Freemium | En comun el chat |
|Tipo de chat | Premium | Opcion de decidir de ante mano si el chat va a ser de tipo en comun o por separado|
| Quedada programada | Freemium | NO |
| Quedada programada | Premium | Boton para mandar notifacion y poder especificar lugar de quedada. Al turista le va a aparacer un  poi nuevo en el mapa |
| Curiosidad | Freemium | Para tres rutas se puede usar las curiosidades manuales (tanto crearlas tanto mostrarlas)|
| Curiosidad | Premium | Uso ilimitado de curiosidades |
