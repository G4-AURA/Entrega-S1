## **Informe de Análisis de Feedback y Calidad** 
<div align="center">  
    <p align="center">
        <img src="../../../logo.png" alt="AURA Logo" width="230"/>
    </p>
</div>

---

## Información General

<div style="border:1px solid #ddd; border-radius:12px; padding:16px;">

**Proyecto:** AURA  
**Grupo (EV):** 4  
**Nombre del grupo:** AURA  

**Tipo de documento:** Análisis de Feedback y Calidad  
**Entrega:** S3  
**Versión:** v1.0  
**Fecha:** 15/04/26
</div>

---
## 1. Contenido
Tras la recogida de feedback, se ha llevado a cabo un proceso de análisis y síntesis del mismo con el objetivo de extraer conclusiones útiles y accionables. Para facilitar su gestión, el feedback se ha organizado en diferentes secciones y se ha clasificado en tres categorías principales: resuelto, descartado y aprobado.

Se considera descartado aquel feedback, generalmente de tipo sugerencia, que no se implementa por motivos de alcance u otras razones debidamente justificadas. Por otro lado, se clasifica como resuelto aquel feedback relacionado con errores, bugs, validaciones o problemas ya conocidos que han sido corregidos. Finalmente, se marca como aprobado el feedback nuevo, ya sea en forma de mejora o sugerencia, que ha sido aceptado y cuya implementación está prevista en futuras iteraciones.

Además, el feedback recopilado ha resultado fundamental para orientar la evolución de la aplicación, permitiéndonos ajustar y redefinir distintos aspectos del desarrollo en función de las necesidades y percepciones de los usuarios. Gracias a este proceso, no solo hemos podido identificar errores o áreas de mejora, sino también detectar oportunidades de valor que inicialmente no se habían contemplado. Esto nos ha llevado a tomar decisiones más informadas, priorizar funcionalidades relevantes y adaptar el enfoque del proyecto, pivotando cuando ha sido necesario para alinear mejor la aplicación con las expectativas reales de uso. 

Dos de nuestros **principales casos de uso**, como la incorporación de un **chat** y el **lanzamiento de curiosidades** en tiempo real durante los tours, surgieron directamente a partir del feedback recibido. Estas sugerencias han aportado un valor añadido significativo a la aplicación, reforzando su utilidad y mejorando la experiencia del usuario.


## 2. Análisis de Bugs y Fallos Encontrados

Se han detectado diversas incidencias críticas y errores de funcionamiento en los flujos principales de la aplicación:

### 2.1. Creación y Edición de Rutas
* **Fallo en el Cálculo de Geometría:** El botón para calcular la ruta o distancia no funciona correctamente después de editar una ruta manual.
* **Persistencia de Advertencias:** Al entrar en los detalles de una ruta sin duración, aparece un mensaje de aviso que persiste incluso después de haber actualizado la duración mediante el botón correspondiente.
* **Inconsistencia en Incrementos de Tiempo:** En las rutas manuales, las flechas incrementan la duración en 1 hora a pesar de que el subtítulo indica incrementos de 0.5h; sin embargo, en rutas IA el incremento sí es de 0.5h.

### 2.2. Inteligencia Artificial (IA)
* **Ignora Deseos Personalizados:** Al crear una ruta con IA, los "deseos" o paradas específicas introducidas por el usuario no se añaden al itinerario final.
* **Falta de Validación Geográfica:** Si se introducen deseos de una ciudad distinta a la seleccionada, el sistema crea la ruta sin avisar que los deseos no corresponden a la ubicación.
* **Error en Creación Consecutiva:** El sistema muestra un error de parseo de JSON (**Error 500**) al intentar generar una segunda ruta con IA inmediatamente después de haber creado una. El backend devuelve HTML en lugar de JSON, rompiendo la interfaz.
* **Validación de Etiquetas:** Si no se seleccionan etiquetas o "moods", el sistema lanza un error de desarrollo poco amigable en lugar de un mensaje de validación claro.
* **Detección de Ubicación:** A pesar de tener los permisos habilitados en el navegador, el sistema falla al detectar la ubicación automática del usuario.

### 2.3. Chat y Sesiones en Vivo
* **Falta de Validación en Chat:** El chat permite enviar mensajes vacíos y no muestra mensajes de error controlados al intentar subir imágenes demasiado grandes o en formatos no permitidos.
* **Sincronización de Estado:** Al iniciar un recorrido desde la vista de mapa, el estado de la sesión no se actualiza a "en curso" automáticamente, apareciendo como "pendiente" hasta que se refresca la página.
* **Finalización de Sesión Defectuosa:** Al terminar un tour, el temporizador no se detiene. El turista empieza a recibir errores 403 sin ninguna indicación visual de que el recorrido ha finalizado.

---

## 3. Mejoras Visuales (UI)

Se sugieren los siguientes cambios para optimizar la interfaz de usuario:

* **Menú de Turista:** Eliminar el botón de "hamburguesa" (tres líneas) en la vista de turista, ya que actualmente no tiene ninguna utilidad y confunde al usuario.
* **Diferenciación en Mapas:** Marcar de forma distintiva la parada de origen y la de destino para que el sentido del trayecto sea identificable visualmente.
* **Iconografía Confusa:** El icono de los puntos de parada sugiere una funcionalidad de "arrastrar y soltar" (*drag & drop*), pero actúa únicamente como un botón clicable.
* **Optimización Móvil:** Reducir el exceso de espacio (*padding*/márgenes) entre campos y mensajes en la versión móvil para maximizar el área de información.
* **Visibilidad del Menú Principal:** Reubicar o destacar más los botones de "Mis rutas" y "Crear Ruta" en el menú principal del guía para facilitar su acceso.

---

## 4. Ideas de Mejora y Sugerencias Funcionales (UX)

Propuestas para enriquecer la experiencia del usuario y añadir valor a la aplicación:

* **Indicadores de Rangos:** Mostrar los valores permitidos en los campos de entrada y bloquear la posibilidad de reducir una ruta a una sola parada si el mínimo requerido es de dos.
* **Enriquecimiento Manual de Paradas:** Permitir añadir una descripción a las paradas creadas manualmente, funcionalidad actualmente limitada a las rutas generadas por IA.
* **Claridad en Instrucciones IA:** Mejorar el campo de instrucciones personalizadas para que pulsar "Enter" no envíe el formulario completo de forma prematura.
* **Gestión de Perfil:** Añadir una sección de perfil para que el guía pueda visualizar y editar sus datos personales, como el correo electrónico.
* **Control del Guía:** Permitir que el guía pueda detener o pausar el cronómetro durante el tour si es necesario.
* **Mensajes de Error Amigables:** Mejorar el feedback de errores de validación (como el de "contraseña común") para que sean más descriptivos y menos genéricos.

---

## 5. Conclusión

> **Prioridad Crítica:** La resolución de los errores de cálculo y la mejora de la respuesta del sistema ante fallos de backend (errores 500) son prioridades críticas para asegurar una experiencia de usuario fluida.

Mientras que las funciones básicas de navegación, registro y seguridad funcionan correctamente, la aplicación presenta debilidades significativas en el módulo de generación por IA y en la edición de rutas.
