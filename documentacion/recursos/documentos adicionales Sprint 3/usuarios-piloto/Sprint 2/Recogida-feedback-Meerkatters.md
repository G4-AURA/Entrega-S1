# **Recogida de Feedback de Meerkatters**
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

## **Listado casos de uso** 

 

## Gestión de Usuarios 

### UC01 – Registrarse 

Permite a un usuario no autenticado crear una cuenta en la plataforma proporcionando sus datos básicos. Durante el registro se valida si el dominio del correo pertenece a una institución reconocida para aplicar posibles beneficios o restricciones. 

**Felipe:** 
- tanto la política de privacidad como términos de servicio no muestran nada, además no se puede registrar ni mediante google o LinkedIn, otra cosa a tener en cuenta es poder elegir si registrarte como profesor o alumno, y por último, deberían estar puestas las condiciones para que se considere valida la contraseña. 

**Alexis:** 
- Botones de registrarse con Google o LinkedIn no tienen utilidad al no estar implementada esa función. 

- Si no se aceptan los términos de servicio y Política de privacidad no te deja crear la cuenta, pero no aparece ningún mensaje indicando ese problema, vería bastante recomendado que se incluya un mensaje emergente para ese caso. 

- No están accesibles los términos de servicio y Política de privacidad al clicar el enlace. 

- Las demás restricciones de los diferentes apartados a rellenar son correctas, con sus correspondientes mensajes emergentes en caso de fallo, aunque bastante laxo el apartado para rellenar el mail en cuanto a restricciones. 

- Según está descrito hay dos tipos de roles y no aparece opción para elegir entre ellos al crear una cuenta, se crea una cuenta de estudiante de forma automática. 

**Javi:** 
- Ver tanto términos de servicio como política de privacidad no está implementado. Ofrece opción de registrarte con cuenta de Google o LinkedIn, pero dichos botones no están implementados.  

- No salta una advertencia por no marcar la casilla de aceptar términos de servicio y política de privacidad, siendo esta acción obligatoria para registrarte en el sistema. 

- He podido registrarme con un correo temporal, debería estar limitado a registrarse con correos con dominio de alguna universidad. 

- No realiza ninguna acción para comprobar que el correo con el que te estás registrando sea realmente el tuyo, no se envía un correo de confirmación. 

- Se asigna automáticamente rol de estudiante, ¿Cómo me registro como profesor? 

- Permite repetir mismo nombre de usuario. 

- La interfaz es sencilla, intuitiva y profesional. 

 

### UC02 – Iniciar Sesión 

Permite a un usuario autenticarse en la plataforma mediante sus credenciales registradas para acceder a funcionalidades personalizadas. 

 

**Felipe:** 
- No se puede recuperar contraseña, y los símbolos se superponen con el texto, por lo demás la interfaz es muy buena, aunque no se entiende que notas compartidas y grupos de estudio sean botones. 

**Alexis:** 
- Las imágenes de contraseña y correo se superponen, tanto al texto predefinido, como al que introduces. 

- No está implementada la funcionalidad para recuperar contraseña al clicar en el enlace. 

- No entiendo que “Notas compartidas” y “Grupos de estudio” aparezcan como botones clicables si no tienen ninguna función.  

**Javi:** 
- Botón de recuperar contraseña no implementado. 

- Los logos que aparecen en los campos de correo electrónico y contraseña aparecen superpuestos tanto del ejemplo que aparece en cada campo como cuando escribes en dicho campo aparece por encima de lo que has escrito. 

 

### UC03 – Cerrar Sesión 

Permite al usuario autenticado finalizar su sesión activa, garantizando la  

seguridad y evitando accesos no autorizados desde el mismo dispositivo. 

 

**Felipe:** 
- Funciona como se espera, quizá debería ser un poco más accesible apareciendo fuera de configuración 

**Alexis:** 
- Se podría poner quizá algo más accesible, y lo vería mejor fuera de la zona de peligro al no ser una acción tan de riesgo, pero funciona de forma correcta. 

**Javi:** 
- Funciona correctamente. 

 

### UC04 – Personalizar Perfil 

Permite al usuario editar su información personal como nombre, foto,  

descripción o preferencias visibles dentro de la plataforma. 

**Felipe:** 
- Funciona correctamente, a tener en cuenta la posibilidad de limitar las opciones de Universidad y Grado para que no se pueda poner información incorrecta y solo poder seleccionar universidades y grados reales. 

- El icono de perfil antes de editarlo y añadir una imagen aparece como que no carga en ninguna de las páginas, y por último si se vuelve a editar el perfil no deja eliminar la imagen. 

 

**Alexis:** 
- Funciona en general de forma correcta todas las ediciones. 

- Al eliminar tu foto de perfil, se produce un error que lleva a una imagen que falla, la cual debería ser la imagen por defecto que obtienes al crear la cuenta. 

- Una vez modificas la imagen, si la eliminas, no se guarda como cambio en el perfil. Esto solo cambia si recargas la página y aun así no sale esa imagen, si no tu nombre de usuario en la zona donde debería aparecer. 

- Vería interesante que la ubicación se busque de forma inteligente, solo pudiendo introducir ubicaciones reales. Y seguiría la misma lógica con la universidad, solo permitiendo las instituciones existentes. 

- El mensaje de fallo al introducir una imagen no válida sería interesante que apareciese cerca de la imagen, ya que, al aparecer al final de la ventana emergente, no es visible a no ser que bajes hasta el final de esta. 

- Quizá vería mejor mayor cantidad de etiquetas de preferencia a elegir. 

**Javi:** 
- Debería aparecer una foto por defecto al crearte la cuenta, actualmente aparece un icono de que una imagen no pudo ser cargada. 

- Se puede subir una foto para ponerla de perfil correctamente, pero cuando eliminas esa foto para volver a la de por defecto, lo que aparece es un texto con el nombre de perfil que te has creado. 

- Cambiar los campos de texto en “Universidad”, “Grado” y “Ubicación” por desplegables o que al escribir te aparezca la opción a seleccionar porque actualmente puedes poner cualquier texto en esos datos. 

- Muy acertada la opción de seleccionar tus preferencias mediante etiquetas. 

 

### UC05 – Ver Perfil 

Permite visualizar el perfil propio o el de otros usuarios, mostrando información pública relevante. 

 

**Felipe:** 
- ¿Dónde se puede ver el perfil de otros usuarios? 

- La interfaz por lo demás muy buena, se actualiza conforme a los datos editados, he probado a unirme a una comunidad y también se ve reflejado en el perfil. 

**Alexis:** 
- Se ve muy bien la vista del perfil propio, con todas las estadísticas actualizadas al momento. 

- No he podido acceder a ver otros perfiles, ni al buscar profesores puesto que no funciona esa lista ni puedo acceder a otros alumnos que estén en chat o en comunidades. 

- La imagen que debe aparecer en el símbolo para acceder a tu perfil no está. 

**Javi:** 
- No hay forma de buscar otros usuarios. 

- Cuando dentro de un evento te aparecen las personas que han confirmado asistencia no se puede acceder a su perfil. 

- El perfil propio es muy completo, pudiendo ver tu información, tus estadísticas y tus comunidades. 

 

### UC06 – Cambiar Contraseña 

Permite al usuario modificar su contraseña actual para reforzar la seguridad de su cuenta. 

 

**Felipe:** 
- Considero que se deberían especificar las condiciones de una contraseña valida antes de rellenar el formulario, además al iniciar sesión pide contraseñade mínimo 8 caracteres y sin embargo a la hora de cambiarla pone mínimo 6 caracteres, y da error interno del servidor al intentarlo. 

- ¿Notificaciones Push y factor doble autenticación funcionan realmente? No aparece nada al volver a iniciar sesión habiendo activado dichas opciones. 

**Alexis:** 
- En el formato correcto, la contraseña se cambia de manera exitosa. 

- Me permite sin mostrar ningún mensaje cambiar mi contraseña a la misma que tenía, lo cual pienso que no debería permitirlo. 

- Si cambio la contraseña a 6 o 7 caracteres da un error interno del servidor. 

- Si introduces de 1 a 5 caracteres, pone el mensaje “La nueva contraseña debe tener al menos 6 caracteres”, lo cual no es coherente con la restricción al crear la cuenta que era “La contraseña debe tener al menos 8 caracteres” 

**Javi:** 
- Error 500 al cambiar la contraseña por una nueva con longitud inferior a 8 caracteres (exigido en el formulario de registro). 

 

### UC07 – Eliminar Cuenta 

Permite al usuario eliminar permanentemente su cuenta y todos los datos asociados según la política de privacidad. 

 

**Felipe:** 
- Todo funciona como debería. 

**Alexis:** 
- Funciona correctamente eliminando la cuenta. Me parece buena transición el mensaje de confirmación y la redirección a la página de inicio. 

- (La cuenta a la cual le cambié erróneamente la contraseña no me permite borrarla por error interno del servidor). 

**Javi:** 
- La cuenta se elimina correctamente, apareciendo mensaje de confirmación y redirigiendo a la página de inicio. Tras probar iniciar de nuevo sesión con la cuenta borrada aparece correctamente el mensaje de que esas credenciales no son válidas. 

 

 

## Gestión de Comunidades 

### UC8 – Crear Comunidad 

Permite a un usuario crear una nueva comunidad con un nombre, descripción y configuración inicial. 

 

**Felipe:** 
- Debería existir la opción de crear comunidades desde la ventana de comunidades. 

**Javi:** 
- Cuando le das a crear comunidad sin rellenar los datos la página no responde de ninguna manera debiendo indicar los campos que son obligatorios para poder crearla. 

- Al darle a añadir imagen te filtra automáticamente a ficheros de imagen, pero si cambias a “todos los archivos”, te permite subir cualquier archivo. 

- Si intentas crear la comunidad con una imagen subida desde tu ordenador no deja crear la comunidad y aparece un error 500. 

- Funcionalidad guardar borrador aún no implementada. 

**Alexis:** 
- Al introducir la imagen no tiene restricciones sobre el tipo de archivo, pudiendo subir cualquier archivo. Al darle a crear no salta error, pero se queda en “creando...” 

- Añadir categorías funciona bien, aunque añadiría algunas por defecto a modo de etiqueta como en la edición del perfil del usuario. 

- Si dejas el nombre vacío, no deja crear la comunidad, pero tampoco lanza un mensaje del tipo “El nombre debe tener mínimo 3 caracteres”, que si salta al introducir 1 o 2. 

- Me gusta el estilo que se usa en este formulario. 

 

### UC9 – Configurar Privacidad Comunidad 

Permite al administrador definir si la comunidad es pública o privada y establecer reglas de acceso. 

**Javi:** 
- Aparece un botón editar en la sección de comunidades creadas, pero no está implementado, te redirige a una pantalla en blanco. 

- La forma de definir si es pública o privada es desde la creación, pero no puedes establecer ninguna regla de acceso. 

- No aparece ningún distintivo en las comunidades creadas que me indique si es pública o privada. 

**Alexis:** 
- No se puede acceder a editar una comunidad, por lo que lo realicé desde la creación y funciona correctamente.  

- No sé cómo puede acceder un usuario a una comunidad privada, no se indica en ningún sitio de la pestaña explorar comunidades. 

### UC10 – Buscar Comunidades 

Permite a los usuarios buscar comunidades mediante filtros o palabras clave. 

**Javi:** 
- Permite buscar por nombre de comunidad, añadiría más opciones de filtro, como por categorías.  

**Alexis:** 
- Sí funciona la búsqueda por texto correctamente, al buscar los títulos únicamente. 

- No tiene funcionalidad el filtro, ni hay palabras claves. Se vería bien implementar a modo de etiquetas las categorías predefinidas. 


### UC11 – Explorar Comunidades 

Permite navegar por comunidades. 

**Javi:** 
- Aparecen todas las comunidades públicas a las que te puedes unir, con una interfaz muy intuitiva. 

**Alexis:** 
- Se ve de forma correcta esta pantalla y el estilo visual que usa es muy acertado. 

- Vería interesante en esta pantalla alguna referencia a comunidades privadas. 


### UC12 – Unirse a Comunidad Pública 

Permite al usuario acceder directamente a una comunidad pública sin necesidad de aprobación. 


**Alexis:** 
- Permite unirte sin problemas a la comunidad, pero una vez unido, en algún caso concreto, sigue apareciendo la opción de unirse. 

- En general, esta funcionalidad está correcta. 

**Javi:** 
- Permite unirse correctamente a cualquier comunidad pública, cambiando el estado del botón a “Unido”. 


### UC13 – Abandonar Comunidad 

Permite al usuario dejar voluntariamente una comunidad a la que pertenece. 

**Javi:** 
- Es prácticamente instantáneo, podría estar bien que se te redirija a otra pantalla en el momento que abandonas la comunidad. 

**Alexis:** 
- Te permite sin problema abandonar la comunidad de forma exitosa, lo veo correcto. 

 

### UC14 – Chat de Comunidad 

Permite a los miembros comunicarse en tiempo real dentro de la comunidad mediante mensajes y archivos. 


**Javi:** 
- Muy buena opción poder editar los mensajes una vez están enviados. 

- Funciona correctamente, apareciendo los mensajes de forma inmediata en el resto de los usuarios que están en el chat, pero al eliminarlo el que lo elimina lo ve correctamente pero el resto tienen que recargar la página. 

**Alexis:** 
- Funciona a tiempo real tanto el envío de mensajes de texto como archivos varios. 

- Al eliminar un mensaje es necesario recargar la página para que se actualice desde otro usuario, no se produce de forma automática. 

- Al mandar textos demasiado largos, el formato se deforma, haciendo que el recuadro del mensaje se expanda en horizontal a lo largo de la página. Esto produce que no se puedan ver los dos extremos del chat de forma simultánea. 

 

Gestión de Eventos (Felipe y Alexis) 

### UC15 – Crear Evento 

Permite crear un evento asociado a una comunidad o independiente, definiendo sus características principales. 

 

**Felipe:** 
- ¿Dónde está la forma de crear evento de forma independiente? Solo se puede hacer en comunidades ya existentes. 

- ¿No hay ningún límite para la cantidad de eventos que puedes crear? ¿Puedes entrar en cualquier comunidad en la que no eres administrador y crear infinitos eventos? ¿Es una función para profesores o alumnos? 

- Las opciones de creación son buenas y la interfaz es muy clara, ademas de que funciona correctamente. 

**Alexis:** 
- No encuentro la opción de crear un evento independiente fuera de una comunidad. 

- Vería interesante una forma de añadir la fecha más interactiva con un calendario, no solo de forma escrita 

- Permite añadir más del máximo de personas posibles. 


### UC16 – Configurar Privacidad Evento 

Permite establecer si un evento es público o privado. 

 

**Felipe:** 
- Desconozco como se ve para otros usuarios, pero dentro del evento una vez creado aparece con la etiqueta de público independientemente de lo que elijas. 

**Alexis:** 
- Funciona la opción al crear y editar, pero siempre se crean eventos públicos, independientemente de lo que hayas seleccionado. 

 

### UC17 – Especificar Información Evento 

Permite definir fecha, hora, descripción y otros detalles relevantes. 

 

**Felipe:** 
- En general esta pantalla tiene muy buena interfaz y se ven correctamente todas las opciones disponibles. 

**Alexis:** 
- Al poner un dato erróneo en la fecha da error interno del servidor, en vez de saltar un mensaje de error normal, después de eso ya no puedo modificar nada por el error. 

- Te permite crear eventos en el pasado, lo cual no le veo sentido. 

 

 

### UC18 – Seleccionar Ubicación (Google Maps) 

Permite establecer una ubicación física utilizando servicios de mapas Integrados. 

**Felipe:** 
- El mapa funciona bien, pero ¿Hay alguna razón de que aparezcan tantos conventos/cementerios al hacer zoom? 

- Se puede elegir ubicación correctamente, pero convendría añadir más filtros para buscar una dirección en concreto, calle, numero, provincia. Digo esto porque al poner mi calle aparece otra con el mismo nombre en otro sito de las Islas Canarias. 

**Alexis:** 
- Funciona correctamente, lo veo bastante interactivo y visual.  

 

### UC19 – Ver Ubicaciones Recomendadas 

Permite consultar sugerencias automáticas de lugares para celebrar el evento. 

 

**Felipe:** 
- Sino me equivoco esta función hace referencia a la función de buscar ubicaciones en el mapa, dando una ubicación de referencia, funciona bastante bien y puedes ser muy útil, pero tiene que ser más accesible o tiene que estar claramente representada. 

**Alexis:** 
- No encuentro esa opción por ningún lado, o no se especifica 

 

### UC20 – Unirse a Evento 

Permite a un usuario confirmar su asistencia. 

 

**Felipe:** 
- funciona sin problemas. 

**Alexis:** 
- Funciona de forma correcta. 
- No puedo probar unirme a uno privado puesto que no se pueden crear de ese tipo. 

 

### UC21 – Cancelar Asistencia 

Permite retirar la participación confirmada en un evento. 

**Felipe:** 
- Funciona sin problemas 

**Alexis:** 
- Funciona correctamente, se refleja de forma automática en el usuario que cancela, y al recargar la página lo pueden observar el resto de usuarios 

 

### UC22 – Ver Asistentes 

Permite visualizar la lista de usuarios que asistirán al evento. 

**Felipe:** 
- Sería interesante ver el tipo de usuario, si profesor o alumno. 

**Alexis:** 
- Funciona correctamente mostrando el nombre completo del usuario. 

 

### UC23 – Editar Evento 

Permite modificar la información de un evento existente. 

 

**Felipe:** 
- Actualmente no es posible realizar esta función, da siempre error interno del servidor, aunque me gusta que no aparezca una pantalla de error y simplemente muestre el mensaje (aplica a todos los casos anteriores, es menos intrusivo). 

**Alexis:** 
- Aparece la página correctamente, y permite en el formulario modificar, pero a la hora de guardar cambios siempre da un error interno del servidor. 

 

### UC24 – Cancelar Evento 

Permite al creador cancelar el evento, añadiendo un motivo sobre la cancelación. 

**Felipe:** 
- Funciona, pero debería especificarse si cancelar evento sígnifica eliminar también dicho evento, ya que sería buena idea mantener los datos para modificar la fecha en caso de que el evento se quiera postponer, no perdiendo los usuarios que haya dentro del evento. 

**Alexis:** 
- Funciona correctamente, lo único que vería a implementar es que no desaparezcan los eventos cancelados, o por lo menos que los pueda visualizar el creador. 


Gestión de Contenido (Felipe y Javier Ramu) 

### UC25 – Subir Archivos 

Permite cargar archivos a la plataforma para compartirlos con una comunidad. 

 

**Felipe:** 
- Funciona con las imágenes, pero debería esta mejor especificado, esto solo puede realizarse en el chat de comunidades. 

- He tratado de subir un pdf y me da un error pero no me dice el motivo. 

**Javi:** 
- No encuentro ninguna forma de subir archivos a la aplicación, la única forma de hacerlo es en un chat de una comunidad. 

- Cuando le doy a “subir apuntes” en una comunidad me redirige a una página en blanco. No está implementado. 

 

### UC26 – Visualizar Archivos 

Permite consultar archivos disponibles antes de descargarlos. 

 

**Javi:** 
- Al darle al botón de abrir desde el chat de la comunidad, se puede ver dicho archivo sin necesidad de descargarlo. 

**Felipe:** 
- Funciona, pero desconozco como sería con un pdf puesto que no puedo subirlo, deberían indicarse formatos disponibles o tamaños máximos. 

 

### UC27 – Descargar Archivos 

Permite descargar archivos disponibles. 

**Felipe:** 
- Funciona correctamente. 

**Javi:** 
- Al darle al botón de descargar desde el chat de la comunidad, se descarga el archivo correctamente. 

 

### UC28 – Eliminar Archivos 

Permite borrar archivos previamente subidos. 

 

**Felipe:** 
- Funciona correctamente. 

**Javi:** 
- Al darle al botón de eliminar desde el chat de la comunidad, el mensaje del archivo se elimina correctamente. 

- Los otros usuarios deben recargar la página para que se les elimine dicho mensaje con el archivo. Esto debería ser automático. 

 

Suscripciones y Pagos (Felipe y Javi) 

### UC29 – Ver Planes 

Permite consultar los planes de suscripción disponibles y sus beneficios. 

 

**Felipe:** 
- Se pueden ver los planes perfectamente, sería interesante tener un usuario de pruebas que tenga suscripción a esos planes ya implementados. 

**Javi:** 
- Se puede ver los planes de suscripción de los que dispone en una pantalla muy correcta, siendo llamativo el color empleado para la suscripción premium. 

 

### UC30 – Suscribirse a Plan Premium 

Permite contratar un plan premium con ventajas adicionales. 

 

**Felipe:** 
- Funciona correctamente, se pueden acceder a los distintos planes y añadir los datos 

**Javi:** 
- Funciona bien 

 

### UC31 – Procesar Pago 

Gestiona la transacción económica mediante la pasarela de pago integrada. 

**Felipe:** 
- Funciona correctamente, además de que avisa de datos erróneos como fecha expirada de la tarjeta de crédito, sin embargo, en mis pagos no aparece nada sobre el pago de la suscripción. 

**Javi:** 
- Aparece la información de la tarjeta a rellenar para poder cumplimentar el pago y si le das a pagar sin rellenar ningún campo te aparece cuales son los obligatorios, teniendo en cuenta también la longitud de números de la tarjeta y si está caducada o no. Todo esto de forma muy correcta. 

- Al darle a pagar, efectivamente cambias al plan premium y se te redirige a mis pagos. En esta página no aparece que hayas hecho ninguna transacción y aparece un error 500 por consola. 

 

### UC32 – Cancelar Suscripción 

Permite finalizar una suscripción activa. 

**Felipe:** 
- Se cancela correctamente, pero si he pagado un mes y cancelo, el resto del mes debería tener mi plan de suscripción activo. ¿Abuso del consumidor? 

**Javi:** 
- La suscripción se cancela exitosamente, pero automáticamente se vuelve al plan gratuito. 

- Lo correcto sería poder darte de baja, pero mantener tu plan premium hasta el periodo que hayas pagado, ya sea lo que reste de mes o lo que reste de año. 

 
Publicidad y Ajustes (Javi y Felipe) 

### UC33 – Panel de Ajustes 

Permite modificar preferencias generales de la cuenta. 

 

**Felipe:** 
- Ya lo comenté en el apartado de inicio de sesión, hay botones para funciones que en realidad no están implementadas. 

**Javi:** 
- Las opciones que permiten son muy adecuadas sobre todo en el apartado de seguridad. 

- Al activar la autenticación en dos factores no hay ningún tipo de respuesta del sistema, cambia de true a false y viceversa. Entiendo que no está implementada. 