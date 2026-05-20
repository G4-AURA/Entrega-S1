# Informe de Toma de Decisiones y Hoja de Ruta: Aplicación AURA

Tras la revisión del informe de análisis de feedback y la evaluación de las incidencias reportadas en la interfaz de la aplicación, se presentan las decisiones de producto adoptadas con respecto a la viabilidad técnica, el alcance y los plazos temporales del proyecto.

## 1. Resoluciones sobre Bugs y Fallos Críticos

Se ha evaluado el impacto técnico de los elementos disfuncionales y de la falta de información detectados en la plataforma.

* **Elementos de Interfaz Inactivos (Descartado):** No se corregirá ni se eliminará el botón inactivo de tres rayas ubicado en la esquina superior derecha de la pantalla "Únete al Tour". Aunque se reconoce que no realiza ninguna acción, su subsanación se descarta debido a que el alcance actual está cerrado exclusivamente para corregir errores de bloqueo del sistema. Modificar este componente visual alteraría los tiempos de entrega planificados para esta fase.
* **Falta de Información sobre Características Premium (Descartado):** Se descarta la adición de textos explicativos o aclaraciones dentro de la interfaz para especificar que el apartado de recordatorios pertenece al plan premium. Introducir estas etiquetas informativas requiere modificaciones en los recursos de texto globales, lo cual queda fuera del alcance y del tiempo disponible para el sprint actual.

---

## 2. Resoluciones sobre Mejoras Visuales (UI)

Se han analizado las propuestas destinadas a homogeneizar la experiencia visual de navegación del usuario.

* **Inclusión de Botón de Navegación "Hacia Atrás" (Descartado):** No se implementará el botón de retroceso ("←") en la pantalla de "Alertas". A pesar de ser una mejora que aportaría coherencia visual, rediseñar esta vista específica para incrustar el control de navegación e integrarlo con el historial de la aplicación requiere un tiempo de desarrollo y pruebas de maquetación que excede los límites temporales fijados para el cierre del proyecto.

---

## 3. Resoluciones sobre Sugerencias Funcionales (UX)

Se han evaluado las propuestas de reestructuración de pantallas, flujos de arrastre y automatización de avisos.

* **Optimización en la Gestión y Reordenación de Itinerarios (Descartado):** Se rechaza la propuesta de crear una pantalla independiente para la edición de las paradas en una ruta. El desarrollo de una nueva interfaz con su respectivo enrutamiento y lógica de datos excede drásticamente el alcance funcional aprobado, comprometiendo los plazos de entrega globales. El sistema mantendrá el espacio de edición actual.
* **Simplificación del Sistema de Arrastre (Drag & Drop) (Descartado):** Se descarta la modificación del flujo intermedio que obliga a mover las paradas posición por posición (por ejemplo, de la 1 a la 2 y luego a la 3). Habilitar un desplazamiento directo y fluido en el sistema de arrastre exige una reestructuración profunda de la librería de ordenación y de los algoritmos de persistencia en la base de datos, lo cual es inviable por limitations de tiempo.
* **Automatización y Notificaciones de Inicio de Sesión (Descartado):** No se programará el sistema de alertas automáticas o ventanas emergentes (*pop-ups*) para avisar al turista cuando comience la sesión. La creación de este flujo de mensajería en tiempo real no está contemplada en el alcance del desarrollo actual y requiere pruebas de concurrencia para las que no se dispone de margen temporal.
* **Flujo de Navegación de Retorno para el Guía (Descartado):** Se descarta la implementación de accesos directos de regreso a la lista de tours desde las pantallas activas de itinerario o chat. Aunque evitaría tener que cerrar de forma manual las pestañas abiertas, modificar el árbol de navegación del perfil de guía requiere un tiempo de rediseño técnico que obligaría a posponer el lanzamiento de la plataforma.

---

## Conclusión

El enfoque estratégico para esta fase de desarrollo se ha limitado de manera estricta al cumplimiento de los objetivos iniciales dentro de los límites de tiempo y alcance establecidos. Por ello, todas las propuestas de mejora e incidencias secundarias analizadas han sido descartadas para evitar retrasos en el despliegue de la versión actual. No obstante, se determina que todas estas decisiones y cambios no realizados quedan sujetos a una fase de reconsideración posterior, siendo totalmente revisables en caso de que se apruebe y se lleve a cabo un mantenimiento futuro en la página web.
