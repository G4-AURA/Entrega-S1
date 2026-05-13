# Informe de Análisis de Feedback y Calidad: Aplicación AURA 

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
**Versión:** v1.0  
**Fecha:** 13/05/26
</div>

---

## 1. Fallos Detectados (Bugs) 

Se han detectado incidencias técnicas y errores de visualización que afectan la experiencia del usuario:

### Experiencia en el Mapa y Paradas
**Sincronización de Curiosidades:** Se ha detectado que las curiosidades de las paradas no se reflejan en el mapa del turista en ningún momento.Este fallo es especialmente notable en las curiosidades creadas de forma manual, las cuales no aparecen al usuario turista. 
**Interfaz de Ubicación Manual:** Durante la creación manual de una ruta, al seleccionar una ubicación, la interfaz no muestra el punto escogido, ni siquiera al reintentar la acción. Aunque el dato parece guardarse en el sistema, la falta de confirmación visual resulta confusa. 
**Validación de Nombres en Paradas:** El sistema permite la creación de rutas sin asignar nombres a las paradas, autocompletándolas como "Parada X". Se considera que el nombre debería ser un campo obligatorio para evitar ambigüedades.

### Rendimiento y Edición Técnica
**Precisión en la Edición de Duración:** Al editar la duración de una ruta, el incremento se realiza de 1 en 1, en lugar de permitir pasos de 0.5 como se esperaría para una mayor precisión.
**Errores de Backend (409):** Al intentar acceder al mapa de una ruta sin haber iniciado el tour, el backend devuelve periódicamente errores 409 aproximadamente cada 4-5 segundos.
**Elementos de Depuración en Interfaz:** Se han identificado textos que no aportan valor y parecen restos de pruebas técnicas, como el sufijo "-h" en subtítulos o mensajes de "Checkpoint IA".

---

## 2. Opciones de Mejora

### Mejora Funcional
**Optimización del Cálculo de Rutas:** Se sugiere que el cálculo automático incluya un tiempo extra estimado para la visita de cada parada, ya que actualmente parece calcularse únicamente el desplazamiento entre ellas.
**Automatización de Entrada al Tour:** Mejorar el flujo de inicio para que el turista pase directamente al mapa del tour cuando el guía lo inicie, eliminando la necesidad de pulsar un botón de entrada adicional.

### Mejora Visual (UI/UX)
**Limpieza del Catálogo de Rutas:** En el listado de rutas, se recomienda eliminar el campo que indica el guía creador.Dado que el usuario solo visualiza sus propias rutas en esa sección, mostrar su nombre carece de utilidad.
**Indicadores de Comunicación:** En el chat de sesión, se propone añadir un símbolo o notificación visual que indique claramente cuándo hay un mensaje nuevo pendiente de leer.
**Refinamiento de Textos IA:** Eliminar mensajes técnicos como "paradas_adicionales_generadas" para ofrecer una experiencia más limpia y profesional.