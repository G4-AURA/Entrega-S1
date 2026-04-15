## **Informe de Toma de Decisiones y Hoja de Ruta** 

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

**Tipo de documento:** Toma de Decisiones y Hoja de Ruta  
**Entrega:** S3  
**Versión:** v1.0  
**Fecha:** 15/04/26
</div>

---

## 1. Resoluciones sobre Bugs y Fallos Críticos

Tras la revisión del informe de calidad, se ha determinado priorizar la estabilidad técnica en las áreas de edición de rutas, inteligencia artificial y gestión de sesiones.

### 1.1. Creación y Edición de Rutas
* **Cálculo de Geometría (Aprobado):** Se procederá a reparar el fallo del botón para calcular rutas o distancias que surge tras ediciones manuales.
* **Persistencia de Advertencias (Aprobado):** Se corregirá la lógica de visualización para que los mensajes de aviso de duración desaparezcan tras la actualización.
* **Inconsistencia en Tiempos (Aprobado):** Se estandarizarán los incrementos a **0.5h** tanto en rutas manuales como de IA para eliminar la discrepancia actual de 1 hora.

### 1.2. Inteligencia Artificial (IA)
* **Errores de Backend (Aprobado):** Es prioridad crítica resolver el error de parseo de JSON (**Error 500**) y la devolución de HTML en creaciones consecutivas.
* **Deseos y Validación Geográfica (Reasignado):** Se ha decidido no intervenir en el flujo de usuario actual; se ha creado una tarea específica en la vista de administrador para gestionar la activación de estas funcionalidades.

### 1.3. Chat y Sesiones en Vivo
* **Validación de Chat (Aprobado):** Se implementarán controles para evitar mensajes vacíos y gestionar adecuadamente los errores de subida de archivos.
* **Sincronización de Estados (Aprobado):** Se corregirá el flujo para que la sesión pase a "en curso" automáticamente sin requerir el refresco de la página.
* **Finalización Defectuosa (Aprobado):** Se reparará el temporizador y se añadirán indicadores visuales de fin de recorrido para evitar que el usuario reciba errores 403 inesperados.

---

## 2. Resoluciones sobre Mejoras Visuales (UI)

Se optimizará la interfaz para mejorar la claridad visual, descartando elementos que no aportan valor inmediato.

* **Diferenciación en Mapas (Aprobado):** Se introducirán marcas distintivas para la parada de origen y destino, facilitando la identificación del trayecto.
* **Optimización Móvil (Aprobado):** Se reducirán los *paddings* y márgenes excesivos para optimizar el espacio en pantallas pequeñas.
* **Menú de Turista (Resuelto):** El botón de "hamburguesa" ya ha sido eliminado por falta de utilidad.
* **Iconografía e Interfaz (Descartado):** No se realizarán cambios en la iconografía de puntos de parada (Drag & Drop) ni se reubicarán los botones de "Mis rutas" o "Crear Ruta" al considerarse innecesario actualmente.

---

## 3. Resoluciones sobre Sugerencias Funcionales (UX)

Se incorporarán funcionalidades que otorguen mayor control al usuario y profesionalicen el feedback del sistema.

* **Indicadores de Rango (Aprobado):** Se mostrarán valores permitidos y se bloquearán acciones que reduzcan la ruta por debajo del mínimo de dos paradas.
* **Enriquecimiento de Paradas (Aprobado):** Se habilitará la edición de descripciones en paradas creadas manualmente.
* **Control de Guía (Aprobado):** Se añadirá la funcionalidad de pausa y parada del cronómetro durante el tour.
* **Mensajes Amigables (Aprobado):** Se sustituirán los errores de desarrollo por mensajes de validación descriptivos y orientados al usuario.
* **Gestión de Perfil (Resuelto):** La sección para visualizar y editar datos personales del guía ya se encuentra operativa.
* **Instrucciones IA (Descartado):** Se mantiene el comportamiento actual del campo de instrucciones sin cambios adicionales.

---

## 4. Conclusión

> **Foco Estratégico:** El enfoque de desarrollo se centrará en la **estabilidad del backend** y la **coherencia de la sesión en vivo**. Se descartan las modificaciones estéticas o de flujo que no han sido validadas como críticas en esta fase, permitiendo al equipo concentrarse en la resolución de los errores 500 y de cálculo que actualmente rompen la experiencia de usuario.