# Informe de Toma de Decisiones y Hoja de Ruta
<div align="center">  
    <p align="center">
        <img src="../../logo.png" alt="AURA Logo" width="230"/>
    </p>
</div>

---

## Información General

<div style="border:1px solid #ddd; border-radius:12px; padding:16px;">

**Proyecto:** AURA 
**Grupo (EV):** 4  
**Nombre del grupo:** AURA  

**Tipo de documento:** Documento adicional de análisis
**Entrega:** PPL  
**Versión:** v1.1  
**Fecha:** 13/05/26
</div>

---

## 1. Resoluciones sobre Bugs y Fallos Críticos

Tras la revisión del informe de calidad y feedback, se priorizará la corrección de errores de sincronización y validación de datos para estabilizar la experiencia del usuario.

### 1.1. Sincronización y Mapas
**Sincronización de Curiosidades (Aprobado):** Se ha corregido el fallo que impedía mostrar curiosidades en el mapa del turista, mejorando además el cierre de las mismas e implementando la activación por proximidad.

**Confirmación de Ubicación Manual (Aprobado):** Se implementará un cambio de estado visual al confirmar un punto en la interfaz para eliminar la incertidumbre del usuario tras seleccionar una ubicación.

**Errores de Backend 409 (Aprobado):** Se investigarán y resolverán las llamadas recurrentes que generan errores 409 en la consola al acceder al mapa sin haber iniciado el tour.

### 1.2. Validación y Precisión
**Validación de Nombres (Aprobado):** Se hará obligatorio el campo de nombre en las paradas para evitar la asignación automática de "Parada X" y reducir ambigüedades.

**Precisión en la Edición de Duración (Aprobado):** Se resolverá el bug que impedía realizar incrementos de 0.5h en la duración de la ruta, estandarizando la precisión del sistema.

**Elementos de Depuración (Aprobado):** Se realizará una limpieza global de textos técnicos y sufijos de prueba (como "-h" o "Checkpoint IA") en toda la plataforma.

---

## 2. Resoluciones sobre Mejoras Visuales (UI)

Se optimizarán los elementos de la interfaz para ofrecer una experiencia más limpia y profesional, eliminando redundancias.

**Catálogo de Rutas (Aprobado):** Se eliminará el campo que indica el guía creador en las tarjetas de ruta, ya que el usuario solo visualiza sus propios contenidos en esa sección.

**Indicadores de Comunicación (Aprobado):** Se reincorporará la notificación visual (símbolo de mensaje pendiente) en el chat de sesión para mejorar la fluidez comunicativa.

**Refinamiento de Textos IA (Aprobado):** Se eliminarán mensajes internos del sistema como "paradas_adicionales_generadas" para profesionalizar la comunicación con el usuario.

---

## 3. Resoluciones sobre Sugerencias Funcionales (UX)

Se han evaluado propuestas de automatización, decidiendo mantener ciertos controles manuales para preservar la libertad del guía y la claridad del flujo.

**Cálculo de Tiempo en Paradas (Descartado):** No se incluirá un tiempo extra automático para visitas; el sistema mantendrá el cálculo basado únicamente en el desplazamiento para no restringir la libertad del guía en cada parada.

**Automatización de Entrada al Tour (Descartado):** Se mantiene el flujo actual de inicio mediante botón manual, ya que actúa como un delimitador necesario para asegurar que los turistas están listos para comenzar la sesión.

---

## 4. Conclusión

**Foco Estratégico:** El desarrollo se centrará en la **limpieza de la interfaz de usuario** y la **garantía de sincronización de datos críticos** (curiosidades y ubicaciones). Al descartar automatizaciones que restan flexibilidad al guía, el equipo concentrará sus esfuerzos en eliminar errores de depuración y asegurar que la información visual sea coherente en todo momento.