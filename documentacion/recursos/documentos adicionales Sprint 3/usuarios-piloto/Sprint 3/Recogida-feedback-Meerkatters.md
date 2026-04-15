# **Recogida de Feedback Meerkatters**
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

**Tipo de documento:** Documento adicional de análisis  
**Entrega:** S3  
**Versión:** v1.0 
**Fecha:** 14/04/2026  
</div>

---

**Horas Trabajadas por Miembro:**
* **Javier Ramnu:** 00:58:02
* **Felipe:** 00:56:27
* **Alexis:** 00:59:14

---

## **Listado casos de uso** 

## Gestión de usuarios

### UC-01 Registrar usuario
**Alexis:** 
- Me parece innecesario que en la contraseña te ponga la restricción de que tenga máximo 128 caracteres ya que te lo limita directamente. Cuando accedo a términos de servicio y política de privacidad, al volver el formulario se reinicia, haciendo así que, si clicas después de rellenar los datos, se pierde lo escrito.
**Felipe:** 
- He comprobado que no hay un aviso previo sobre la pérdida de datos al salir del formulario para leer los términos. Además, la restricción de caracteres mencionada por Alexis no se indica claramente antes de escribir, lo que genera una mala experiencia si el usuario ya tiene una contraseña pensada.

### UC-02 Iniciar sesión
**Alexis:** 
- Funciona correctamente cuando se realiza de forma manual, no le veo sentido a requerir vincular la cuenta posteriormente para iniciar desde Google salta el error: "Existe una cuenta con este email. Inicia sesión y vincula la cuenta desde ajustes." Vería interesante que si te registras con un mail de Google automáticamente se vinculase al crear la cuenta.
**Felipe:** - Coincido en que el flujo de autenticación con Google es confuso. Si el correo coincide, el sistema debería facilitar la unificación de cuentas en ese mismo momento en lugar de bloquear el acceso y obligar al usuario a realizar pasos extra en la configuración manual.

### UC-03 Cerrar sesión
**Alexis:** 
- Funciona correctamente.
**Felipe:** 
- El proceso es rápido y redirige correctamente a la pantalla principal, cerrando la sesión de forma efectiva en el navegador.

### UC-04 Editar perfil
**Alexis:** 
- Funciona todo correctamente, excepto la casilla rellenable de ubicación, que te permite añadir cualquier cosa, considero que debería o bien solo permitir introducir coordenadas correctas, o bien un lugar existente.
**Felipe:** 
- He detectado que la falta de validación en el campo de ubicación permite guardar carácteres aleatorios o espacios en blanco. Sería recomendable que el campo tuviera una máscara de entrada o una lista de selección para asegurar que los datos sean útiles para la plataforma.

### UC-05 Ver perfil
**Alexis:** 
- Funciona correctamente, sugeriría añadir a qué comunidad pertenece cada perfil ya que aparece apartado mis comunidades, pero sin corresponderse al perfil.
**Felipe:** 
- Al visualizar perfiles ajenos, la información parece incompleta. Como dice Alexis, el apartado de comunidades no está vinculado al perfil que se está consultando, lo que puede inducir a error sobre la pertenencia del usuario a ciertos grupos.

### UC-06 Cambiar contraseña
**Alexis:** 
- Si te pasas del largo sale: "password cannot be more than 72 bytes", y algunas restricciones como mínimo 1 mayúscula no se aplica ahora, y si se exige al crear la cuenta.
**Felipe:** 
- Existe una falta de coherencia entre las reglas de validación del registro y las del cambio de contraseña. Además, el mensaje de error técnico que menciona Alexis no es comprensible para un usuario común; debería traducirse a un lenguaje más sencillo y funcional.

### UC-07 Eliminar cuenta
**Alexis:** 
- Funciona correctamente y bien advertido al ser un paso permanente.
**Felipe:** 
- La confirmación de seguridad es adecuada para evitar borrados accidentales. El sistema procesa la solicitud de baja sin dejar rastro de la sesión anterior, cumpliendo con lo esperado.

---

## Comunidades

### UC-08 Crear comunidad
**Alexis:** 
- Me permitió añadir como foto un archivo de video, dando después un error interno del servidor. Cuando falla la creación te cuenta como intento para el plan gratis, quitándote opciones para crear comunidades si la web falla. Si pones una imagen que supere los MB máximos, no te indica concretamente el error que está en la imagen, te da uno genérico, además de que no incluyen información de cómo debe ser el formato de la imagen.
**Javier:** 
- Muy buena decisión no permitir que el botón de crear comunidad pueda ser pulsado hasta que no completes los campos necesarios. Y luego cuando te falte algo. La acción de transferir administrador funciona correctamente, pero hay que recargar la página para que aparezca actualizada. Te permite poner cualquier tipo de archivo como imagen, se debería corregir.

### UC-09 Editar comunidad
**Alexis:** 
- Funciona correctamente. Vería mejorable el hecho de que en la edición se pudieran modificar más atributos de la comunidad.
**Javier:** 
- Se puede editar el titulo y la descripción, pero vería necesario que se pudiese editar también el aforo, las categorías, etc.

### UC-10 Eliminar comunidad
**Alexis:** 
- Funciona correctamente.
**Javier:** 
- Funciona correctamente, estaría bien que el mensaje de confirmación apareciera con la estética de la aplicación. En una de las comunidades me ha aparecido este mensaje de error "Conflicto de datos al guardar. Revisa que la franja no se solape con otra existente." y no he entendido a que se refería.

### UC-11 Unirse a comunidad
**Alexis:** 
- Funciona correctamente.
**Javier:** 
- Funciona correctamente.

### UC-12 Solicitar acceso a comunidad privada
**Alexis:** 
- Se realiza correctamente tanto la solicitud como la aceptación, lo único que solo me notificó la aceptación, al usuario dueño de la comunidad no le salta notificación alguna al no estar activada, no le veo sentido que sea opcional esa notificación.
**Javier:** 
- Las solicitudes estaría bien que apareciese en el apartado de notificaciones. Me ha aparecido por consola un error 500 al querer aceptar o rechazar la solicitud.

### UC-13 Gestionar miembros de comunidad
**Alexis:** 
- Solicitudes funcionan. Exceptuando las opciones de expulsar o transferir administración, que funcionan correctamente, no encuentro ningún otro tipo de gestión de roles.
**Javier:** 
- La gestion de roles funciona muy bien.

### UC-14 Publicar contenido en comunidad
**Alexis:** 
- Funciona correctamente. Los eventos y chats se crean de forma correcta.
**Javier:** 
- La creacion de eventos, cuestionarios y anuncios funcionan correctamente y de forma muy sencilla e intuitiva.

### UC-15 Moderar contenido de comunidad
**Alexis:** 
- Chats, cuestionarios y respuestas, no se permite modificar, solo eventos. Al eliminar comunidad en un caso concreto me da el error: "Conflicto de datos al guardar. Revisa que la franja no se solape con otra existente."
**Javier:** 
- Ni los cuestionarios ni los anuncios se pueden moderar, los eventos si se pueden moderar correctamente. Vería importante habilitar la edición en particular en los cuestionarios, ya que podrían contener errores en los preguntas o respuestas que se crearon originalmente.

---

## Eventos

### UC-16 Crear evento
**Alexis:** 
- Funciona de forma correcta con sus distintas validaciones.
**Felipe:** 
- El proceso de creación es intuitivo y las validaciones de los campos obligatorios responden bien. Se asocia correctamente a la comunidad seleccionada sin errores de carga.

### UC-17 Configurar privacidad de evento
**Alexis:** 
- Funciona correctamente. La funcionalidad de privado o público no le veo mucho sentido al público, ya que lo que lo diferencia del privado es que se muestre a todo el mundo, pero a efectos prácticos, solo lo verán los miembros de la comunidad, al no publicitarlo al resto de personas. En el mapa, si es privado, no aparece aunque pertenezcas a su comunidad.
**Felipe:** 
- Coincido con la observación sobre la visibilidad. Si un evento es privado, los miembros de la propia comunidad deberían poder localizarlo en el mapa. Actualmente, la distinción entre "público" y "privado" resulta confusa si el alcance de difusión es el mismo para ambos.

### UC-18 Especificar información del evento
**Alexis:** 
- Funciona correctamente.
**Felipe:** 
- Los campos permiten detallar bien el evento. La carga de la información es fluida y no se detectan errores al procesar textos largos o descripciones.

### UC-19 Seleccionar ubicación (mapa interactivo)
**Alexis:** 
- Funciona correctamente, así como el buscar ubicación por la dirección.
**Felipe:** 
- El buscador por dirección es preciso y el marcador se posiciona correctamente en el mapa interactivo. La integración entre la búsqueda de texto y la respuesta del mapa es estable.

### UC-20 Ver ubicaciones recomendadas
**Alexis:** 
- Funciona correctamente en algunos casos, pero en un caso al aumentar el radio daba el fallo: "Error buscando ubicaciones", o en otro buscando formación daba fallo también. Me parece una muy interesante funcionalidad extra.
**Felipe:** 
- Es una herramienta con mucho potencial, pero la estabilidad es inconsistente. He notado que al modificar los parámetros de búsqueda (como el radio o la categoría), el sistema lanza errores aleatorios, lo que sugiere que la consulta a la base de datos de ubicaciones falla bajo ciertas condiciones.

### UC-21 Unirse a evento
**Alexis:** 
- Funciona correctamente.
**Felipe:** 
- El registro de asistencia es inmediato.

### UC-22 Cancelar asistencia
**Alexis:** 
- Funciona correctamente.
**Felipe:** 
- El proceso para desapuntarse es sencillo y funciona.

### UC-23 Ver asistentes
**Alexis:** 
- Funciona correctamente.
**Felipe:** 
- La lista se despliega de forma clara. Permite verificar correctamente quiénes están inscritos al evento.

### UC-24 Editar evento
**Alexis:** 
- Funciona correctamente, menos la ubicación que al cambiarla no se actualiza. Al darle a actualizar te redirige a la página anterior que hayas abierto, en mi caso al editar la ubicación me llevó de vuelta a esa, lo cual no le veo sentido.
**Felipe:** 
- La ubicación da problemas.

### UC-25 Cancelar evento
**Alexis:** 
- Se cancela correctamente. No se notifica a los asistentes si no marcan la opción previamente en ajustes, no le veo mucho sentido a que por defecto esté desmarcada la opción.
**Felipe:** 
- El borrado o marcado de cancelación es funcional, pero el sistema de notificaciones es poco preventivo. Al ser la opción de notificar opcional por defecto, existe un riesgo alto de que los asistentes no se enteren de la cancelación, lo que resta utilidad a la función de aviso.

---

## Contenido

### UC-26 Subir archivo
**Javier:** 
- En el chat se permite compartir todo tipo de archivos correctamente, dentro de la comunidad no se si debería poder subir archivos a algún lado más.
**Felipe:** 
- La subida en chats es fluida, pero coincido con Javier: la gestión de archivos dentro de las comunidades se siente limitada. Sería útil contar con un repositorio o pestaña de "Documentos compartidos" en la comunidad para no depender exclusivamente del flujo del chat.

### UC-27 Visualizar archivo
**Javier:** 
- Funciona correctamente.
**Felipe:** 
- La previsualización de archivos comunes (imágenes, PDFs) es correcta y rápida. No se detectan errores de carga al abrir elementos multimedia.

### UC-28 Descargar archivo
**Javier:** 
- Funciona correctamente.
**Felipe:** 
- La descarga se inicia sin problemas y el archivo resultante mantiene la integridad y el nombre original. Proceso limpio en diferentes navegadores.

### UC-29 Eliminar archivo
**Javier:** 
- Funciona correctamente.
**Felipe:** 
- El sistema permite el borrado por parte del propietario de forma efectiva. El archivo desaparece de la vista del chat o comunidad inmediatamente tras la confirmación.

---

## Mapas y ubicación

### UC-30 Búsqueda por ubicación
**Alexis:** 
- Funciona correctamente
**Javier:** 
- Funciona correctamente

### UC-31 Visualizar mapa de meetings
**Alexis:** 
- Funciona correcto excepto que no aparecen eventos privados de la comunidad a la que pertenezco. Salen eventos, aunque estén fuera de los parámetros como el radio.
**Javier:** 
- No entiendo la funcionalidad de especificar el radio de búsqueda. Aparecen correctamente los eventos que hay creados.

---

## Profesores

### UC-32 Crear / editar perfil de profesor
**Alexis:** 
- Funciona correctamente.
**Javier:** 
- Como foto de perfil se pone automáticamente el nombre del usuario, cuando la cambias en el perfil si se actualiza correctamente. Funciona correctamente.

### UC-33 Solicitar verificación de profesor
**Alexis:** 
- Funciona correctamente
**Javier:** 
- Funciona correctamente

### UC-34 Listar profesores
**Alexis:** 
- Funciona correctamente
**Javier:** 
- Funciona correctamente

### UC-35 Listar profesores verificados
**Alexis:** 
- Salen los verificados en la parte superior, pero no los filtra ya que no hay opción para que solo muestre a los verificados.
**Javier:** 
- No hay opción de filtrar por profesores verificados.

### UC-36 Pago para verificación / promoción
**Alexis:** 
- Funciona correctamente
**Javier:** 
- Funciona correctamente.

### UC-37 Valorar profesor
**Alexis:** 
- Funciona la contratación (no puedo valorar porque imagino que tendrá que pasar la fecha acordada y no me deja el día de hoy)
**Javier:** 
- La contratación funciona correctamente, no he podido valorarlo.

### UC-38 Chat con profesor
**Alexis:** 
- Funciona de forma correcta
**Javier:** 
- Funciona correctamente.

---

## Finanzas y sistema de Pagos

### UC-39 Ver planes
**Javier:** 
- Funciona correctamente.
**Felipe:** 
- La tabla comparativa de los planes es clara y permite diferenciar bien las características de cada nivel antes de proceder a la compra.

### UC-40 Suscribirse a un plan
**Javier:** 
- Funciona correctamente. En el apartado de planes me aparece que estoy pertenezco a un plan pero en el apartado de "mis suscripciones", aparece que no tengo suscripción activa. Esto ocurrió al suscribirme primero en el plan premium y posteriormente en el plan pro.
**Felipe:** 
- He detectado una inconsistencia grave en la actualización del estado del usuario. Al realizar un cambio de plan, la base de datos parece no sincronizar correctamente entre la vista de "Planes" y el perfil de "Mis suscripciones", dejando al usuario en un estado de incertidumbre sobre qué servicio está pagando realmente.

### UC-41 Procesar pago
**Javier:** 
- Funciona correctamente.
**Felipe:** 
- El pago se procesa de forma segura y el sistema recibe la confirmación del pago sin retrasos notables.

### UC-42 Cancelar suscripción
**Javier:** 
- No encuentro forma de cancelar el plan o la renovación del plan.
**Felipe:** 
- Al igual que Javier, no he localizado un botón o sección de gestión de suscripción que permita interrumpir la renovación automática. Esto obliga al usuario a mantener un plan activo sin su consentimiento explícito para el futuro, lo cual debería ser una opción accesible desde los ajustes de cuenta.

---

## Notificaciones

### UC-43 Enviar notificación
**Alexis:** 
- Funciona de forma correcta, algunos tipos de notificaciones vería mejor que de inicio estuviesen marcadas para que se manden, y ya si el usuario quiere las desactive.
**Felipe:** 
- Coincido en que la configuración por defecto es demasiado restrictiva. El sistema envía las alertas correctamente cuando están activas, pero el hecho de que muchas categorías importantes vengan desactivadas de fábrica puede hacer que el usuario se pierda información crítica antes de configurar su perfil.

### UC-44 Recibir notificación
**Alexis:** 
- Funciona correctamente.
**Felipe:** 
- La entrega en tiempo real es estable.

### UC-45 Ver historial de notificaciones
**Alexis:** 
- Funciona correctamente.
**Felipe:** 
- Funciona correctamented.

### UC-46 Marcar notificación como leída
**Alexis:** 
- Funciona correctamente.
**Felipe:** 
- Funciona correctamente.

---

## Videollamadas

### UC-47 Crear sala de videollamada
**Javier:** 
- Funciona correctamente. El cronometro que aparece está mal, he puesto duracion 60 min y aparece "Restante: 00:00" y el tiempo activo aparece directamente con 2 horas.
**Felipe:** 
- La creación de la sala es estable, pero hay un fallo evidente en la lógica del contador. El sistema parece no procesar correctamente el parámetro de duración introducido, mostrando valores incoherentes desde el inicio de la sesión. Es necesario revisar si el error es del frontend o de la asignación de tiempo en el servidor.

### UC-48 Unirse a videollamada
**Javier:** 
- Funciona correctamente.
**Felipe:** 
- El acceso de los participantes es fluido. El enlace de invitación redirige correctamente y permite la entrada a la sala sin retardos significativos.

### UC-49 Compartir audio y vídeo
**Javier:** 
- Funciona correctamente.
**Felipe:** 
- La gestión de periféricos es adecuada. El sistema reconoce correctamente los cambios de entrada de audio y video durante la llamada.

### UC-50 Compartir pantalla
**Javier:** 
- Funciona correctamente.
**Felipe:** 
- Funciona correctamente.

### UC-51 Finalizar videollamada
**Javier:** 
- Funciona correctamente.
**Felipe:** 
- Funciona correctamente.