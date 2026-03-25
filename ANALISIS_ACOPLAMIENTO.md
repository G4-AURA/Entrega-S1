# Análisis de acoplamiento y cohesión del estado actual del repositorio (incluyendo CSS)

## Alcance
Este análisis evalúa el estado actual del proyecto en dos ejes:

- **Acoplamiento**: grado de dependencia entre módulos/capas.
- **Cohesión**: qué tan enfocada está cada unidad (archivo/módulo) en una responsabilidad principal.

Se revisaron especialmente los módulos de backend (`tours`, `rutas`, `creacion`) y los estilos CSS globales y por feature.

---

## Resumen ejecutivo

**Veredicto breve:** el repositorio muestra **buenas señales de bajo acoplamiento y cohesión alta en varias áreas**, pero **no de forma homogénea en todo el código**.

- **Backend (`tours`, `rutas`)**: tendencia clara a **vistas delgadas + servicios**, lo cual favorece cohesión y reduce acoplamiento accidental.
- **Backend (`creacion`)**: existe una capa de servicios útil, pero el archivo `creacion/services.py` concentra demasiadas responsabilidades (validación, integración IA, optimización, persistencia), lo que baja su cohesión.
- **CSS**: hay separación por feature en `static/css/creacion/*`, pero persiste un CSS global grande (`static/css/style.css`) con responsabilidades mezcladas y colisiones potenciales de nombres (`.btn-back`), lo que sugiere acoplamiento visual medio.

Conclusión: **estado general “aceptable/bueno”, pero todavía no se puede afirmar de forma estricta que todo el repositorio tenga bajo acoplamiento y alta cohesión**.

---

## Evidencia: backend

### 1) Señales positivas (mejor cohesión y menor acoplamiento)

1. **Patrón explícito de “vistas delgadas”**
   - En `tours/views.py` y `rutas/views.py` se documenta y aplica la delegación de reglas de negocio a `services`.
   - Esto mejora cohesión de vistas (HTTP/entrada-salida) y de servicios (negocio).

2. **Centralización de reglas de autorización y utilidades de dominio**
   - En `tours/services.py` se centralizan funciones como `es_guia_de_sesion`, `tiene_acceso_a_sesion`, unión de turistas, serialización de paradas y gestión de sesión.
   - Evita duplicación de lógica en controladores y reduce acoplamiento entre vistas.

3. **Operaciones de edición de rutas delegadas a servicios**
   - `rutas/views.py` delega acciones de negocio (actualizar metadatos, paradas, recálculo) a `rutas/services.py`, manteniendo el controlador orientado a flujo HTTP.

### 2) Señales de riesgo (acoplamiento/carga de responsabilidad)

1. **`creacion/services.py` está sobredimensionado funcionalmente**
   - Conviven en un único módulo: normalización de payload, validaciones de permisos, invocación IA, optimización de rutas, creación de modelos y persistencia histórica.
   - Esto incrementa acoplamiento interno y reduce cohesión del módulo.

2. **Dependencia de infraestructura externa dentro del mismo servicio de dominio**
   - Uso directo de `requests`, `langgraph`, `ortools` y ORM en el mismo archivo.
   - Si cambia un proveedor o contrato externo, el impacto se concentra en un módulo crítico con múltiples responsabilidades.

3. **Acoplamiento a cadena de relaciones de modelos en autorizaciones**
   - Ejemplo típico: ruta de acceso tipo `sesion.ruta.guia.user.user`.
   - Está parcialmente mitigado al centralizarse en funciones de servicio, pero sigue siendo una dependencia frágil de estructura de datos.

---

## Evidencia: CSS

### 1) Señales positivas

1. **Existe separación por feature en creación de rutas**
   - Archivos como `static/css/creacion/creacion_manual.css` y `static/css/creacion/personalizacion.css` aíslan estilos de pantallas concretas.
   - Uso de prefijos de bloque (`.creacion-manual__*`) y diseño por componentes locales mejora cohesión visual.

2. **Uso de variables CSS**
   - Variables en `:root` ayudan a consistencia de diseño y reducen acoplamiento por “hardcodes” repetidos.

### 2) Señales de riesgo

1. **`static/css/style.css` concentra muchas responsabilidades globales**
   - Mezcla utilidades de mapa, panel inmersivo, tabs, chat y estilos generales.
   - Este enfoque tiende a aumentar acoplamiento entre vistas no relacionadas y hace más costoso el mantenimiento.

2. **Posible colisión de selectores genéricos entre CSS global y CSS de feature**
   - Clase `.btn-back` aparece en estilos globales y también en estilos de creación manual.
   - Si coinciden en una misma página o cambia el orden de carga, puede haber efectos laterales no deseados.

3. **Acoplamiento a estructura del DOM mediante selectores poco encapsulados**
   - Varias reglas dependen de nombres genéricos (`.header`, `.form-label`, etc.) que pueden reutilizarse en otras pantallas.

---

## Dictamen final

### ¿Tiene bajo acoplamiento y alta cohesión?

**Respuesta corta:** **parcialmente sí, pero no completamente**.

- **Sí** en áreas con separación clara “views/services” y responsabilidades bien distribuidas (sobre todo `tours` y parte de `rutas`).
- **No del todo** por dos focos principales:
  1. concentración excesiva de responsabilidades en `creacion/services.py`;
  2. mezcla de estilos globales extensos con naming genérico en CSS.

En términos prácticos, el proyecto está en un **nivel intermedio-bueno**: no está fuertemente acoplado, pero todavía tiene deuda estructural para alcanzar un nivel “alto” de cohesión y “bajo” de acoplamiento de forma consistente.

---

## Recomendaciones priorizadas

1. **Dividir `creacion/services.py` por dominios internos**
   - `payload_validation.py`, `ai_generation.py`, `route_persistence.py`, `route_optimization.py`.
2. **Introducir puertos/adaptadores para servicios externos**
   - Encapsular GraphHopper/LangGraph/requests detrás de interfaces para bajar acoplamiento a proveedores.
3. **Reducir `static/css/style.css` a un núcleo global mínimo**
   - Mover chat/panel/timeline a CSS por feature o por página.
4. **Estandarizar naming CSS (BEM o utilitario) y evitar clases genéricas duplicadas**
   - Renombrar `.btn-back` global vs `.creacion-manual__btn-back`.
5. **Mantener la política de vistas delgadas**
   - Es una fortaleza actual que conviene preservar en nuevas funcionalidades.
