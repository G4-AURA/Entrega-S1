# AURA - Funcionalidades y casos de uso

## 1. Resumen de la aplicación

AURA es una aplicación web pensada para guías turísticos. Su objetivo es ayudar a preparar rutas, gestionarlas, ejecutarlas en directo con turistas y apoyarse en inteligencia artificial para reducir la improvisación durante el trabajo diario.

La aplicación permite:

- Registrar guías y permitirles iniciar sesión.
- Crear rutas turísticas manualmente.
- Generar rutas con inteligencia artificial.
- Guardar y consultar un catálogo de rutas propias.
- Editar rutas, paradas, etiquetas, duración, exigencia y descripción.
- Calcular el trazado real de una ruta en mapa.
- Añadir curiosidades a las paradas, manualmente o con IA.
- Crear sesiones de tour en vivo a partir de una ruta.
- Permitir que turistas anónimos se unan a una sesión mediante código o enlace.
- Mostrar mapas en vivo para guía y turistas.
- Compartir ubicación entre guía y turistas.
- Usar chat común y, en Premium, chat privado.
- Crear recordatorios o quedadas programadas en tours Premium.
- Gestionar planes Freemium/Premium y pagos mediante Stripe.
- Permitir a administradores mantener una lista autorizada de puntos de interés.

A nivel de uso, AURA tiene cuatro perfiles principales:

- Visitante no registrado: persona que llega a la landing o a un enlace de tour.
- Guía: usuario registrado que crea y gestiona rutas y sesiones.
- Turista: participante anónimo de una sesión de tour.
- Administrador: superusuario que gestiona datos internos, allowlist y acceso a funciones.

## 2. Conceptos básicos

### Ruta

Una ruta es el plan turístico que prepara el guía. Incluye título, descripción, duración, número de personas, nivel de exigencia, etiquetas temáticas y una lista ordenada de paradas.

Las rutas pueden ser:

- Manuales: creadas por el guía introduciendo los datos.
- Generadas con IA: propuestas por el sistema a partir de preferencias del guía.

### Parada

Una parada es un lugar concreto dentro de una ruta. Cada parada tiene nombre, descripción opcional, posición en el mapa y orden dentro del recorrido.

### Curiosidad

Una curiosidad es un contenido asociado a una parada. Puede incluir título, texto, tipo e imagen. Sirve para que el guía tenga material narrativo durante el tour y para que el turista pueda descubrir información contextual.

### Sesión de tour

Una sesión es la ejecución en directo de una ruta. Por ejemplo, una misma ruta "Sevilla histórica" puede usarse para una sesión concreta del martes por la mañana.

Una sesión puede estar en tres estados:

- Pendiente: creada, pero todavía no iniciada.
- En curso: el tour está activo.
- Finalizada: el acceso queda cerrado y ya no se puede participar.

### Código de acceso

Cada sesión tiene un código legible para que los turistas se unan. También existe un enlace interno con token seguro. El código se puede regenerar si el guía necesita invalidar el anterior.

### Plan

Cada guía tiene un plan:

- Freemium: plan inicial con límites.
- Premium: plan ampliado con más capacidad y funciones avanzadas.

## 3. Roles de usuario

## 3.1 Visitante no registrado

Es una persona que aún no ha iniciado sesión. Puede:

- Ver la página inicial.
- Acceder al formulario de registro de guía.
- Acceder al formulario de inicio de sesión.
- Abrir un enlace de tour si tiene código o enlace compartido por un guía.

No puede:

- Crear rutas.
- Ver catálogos privados.
- Crear sesiones.
- Gestionar planes.
- Acceder al panel de administración.

### Casos de uso del visitante

#### Caso 1: Entrar en la web por primera vez

1. El visitante abre la página principal.
2. La aplicación muestra la landing.
3. Desde ahí puede iniciar sesión o registrarse.

Resultado esperado: el visitante entiende que AURA es una herramienta para guías turísticos.

#### Caso 2: Registrarse como guía

1. El visitante entra en el formulario de registro.
2. Introduce sus datos de usuario.
3. Acepta las condiciones si el formulario lo requiere.
4. La aplicación crea un usuario y un perfil de guía.
5. El nuevo guía queda autenticado.
6. La aplicación lo redirige al catálogo de rutas.

Resultado esperado: el nuevo usuario empieza como guía Freemium.

#### Caso 3: Intentar acceder a una zona privada

1. El visitante abre una URL privada, como el catálogo.
2. La aplicación detecta que no ha iniciado sesión.
3. Se redirige al login o se bloquea la acción.

Resultado esperado: la información del guía queda protegida.

## 3.2 Guía

Es el usuario principal de la aplicación. Puede preparar rutas, lanzar tours, controlar la sesión en vivo y gestionar su plan.

### Funcionalidades del guía

- Iniciar sesión.
- Editar su perfil.
- Consultar su catálogo de rutas.
- Crear rutas manuales.
- Crear rutas con IA.
- Seleccionar paradas propuestas por IA.
- Pedir paradas adicionales durante una generación IA.
- Guardar rutas generadas.
- Editar rutas existentes.
- Añadir, editar, eliminar y reordenar paradas.
- Cambiar título, descripción, duración, número de personas, exigencia y etiquetas.
- Recalcular geometría y métricas de mapa.
- Consultar auditoría de cambios en rutas generadas por IA.
- Crear, editar o eliminar curiosidades por parada.
- Crear sesiones de tour a partir de rutas.
- Iniciar, pausar, reanudar y cerrar una sesión.
- Regenerar el código de acceso.
- Ver participantes.
- Ver mapa en vivo.
- Compartir ubicación.
- Ver ubicación de turistas.
- Usar chat común.
- Usar chat privado si el plan lo permite.
- Crear recordatorios o quedadas programadas si el plan lo permite.
- Consultar su plan, límites y consumo.
- Pasar a Premium o programar baja según configuración de Stripe.

## 4. Flujo de acceso y navegación

### Inicio de sesión

Cuando un usuario inicia sesión:

- Si es administrador, se redirige al panel de allowlist.
- Si es guía, se redirige al catálogo de rutas.
- Si no encaja en ningún caso especial, se usa el catálogo como destino seguro.

### Registro de guía

El registro crea:

- Un usuario de Django.
- Un perfil interno de autenticación.
- Un perfil de guía asociado.
- Una suscripción inicial Freemium.

## 5. Catálogo de rutas

El catálogo es la zona donde el guía ve sus rutas.

Permite:

- Listar rutas propias.
- Filtrar por tipo: manual o IA.
- Paginarlas.
- Ver datos principales de cada ruta.
- Identificar si una ruta tiene una sesión activa.
- Entrar al detalle de una ruta.
- Eliminar rutas.
- Crear una sesión de tour desde una ruta.

### Caso de uso: consultar rutas

1. El guía inicia sesión.
2. Entra en el catálogo.
3. La aplicación carga las rutas del guía.
4. El guía puede cambiar de página o filtrar por tipo.

Resultado esperado: solo se muestran rutas del guía, salvo en casos especiales de superusuario.

### Caso de uso: eliminar una ruta

1. El guía selecciona una ruta propia.
2. Pulsa eliminar.
3. La aplicación confirma la acción desde el backend.
4. La ruta desaparece del catálogo.

Resultado esperado: la ruta y sus datos asociados se eliminan.

## 6. Creación manual de rutas

La creación manual permite al guía definir una ruta desde cero.

Datos habituales:

- Título.
- Descripción.
- Duración.
- Número de personas.
- Nivel de exigencia.
- Etiquetas temáticas.
- Lista de paradas.
- Coordenadas de cada parada.
- Descripción de cada parada.

### Caso de uso: crear ruta manual

1. El guía entra en "crear ruta".
2. Selecciona creación manual.
3. Introduce los datos generales.
4. Añade las paradas con sus coordenadas.
5. Guarda la ruta.
6. La aplicación valida límites del plan.
7. Si todo es correcto, la ruta queda guardada en el catálogo.

Resultado esperado: el guía obtiene una ruta lista para consultar, editar o usar en una sesión.

### Validaciones principales

- El usuario debe estar autenticado.
- Solo un guía puede crear rutas.
- El número de paradas no puede superar el límite del plan.
- El número de personas no puede superar la capacidad del plan.
- Las etiquetas deben estar permitidas por el plan.
- En Freemium hay límite de rutas manuales simultáneas.

## 7. Creación de rutas con IA

La creación con IA permite que el guía introduzca preferencias y reciba una propuesta de ruta generada automáticamente.

La IA usa datos como:

- Ciudad.
- Duración deseada.
- Número de personas.
- Nivel de exigencia.
- Temáticas.
- Restricciones.
- Deseos adicionales, si el plan lo permite.

El sistema genera una ruta con paradas propuestas y datos descriptivos.

### Caso de uso: generar y guardar ruta IA directamente

1. El guía entra en creación con IA.
2. Rellena la personalización.
3. Solicita generar ruta.
4. La aplicación valida plan y límites.
5. Se consulta el motor de IA.
6. Se recibe una propuesta.
7. La aplicación ajusta la propuesta si supera límites del plan.
8. Se guarda la ruta.
9. Se registra el uso mensual de generación IA.
10. La ruta aparece en el catálogo.

Resultado esperado: el guía obtiene una ruta generada, optimizada y persistida.

### Caso de uso: generar propuesta y seleccionar paradas

1. El guía activa el modo de selección.
2. La IA genera una lista de paradas propuestas.
3. El guía selecciona qué paradas quiere conservar.
4. Puede rechazar otras paradas.
5. La aplicación guarda solo la selección.
6. El sistema conserva el contexto de la generación.

Resultado esperado: el guía tiene control sobre la ruta final sin perder la ayuda de la IA.

### Caso de uso: pedir paradas adicionales

1. Durante una generación IA, el guía solicita más paradas.
2. Puede añadir sugerencias textuales.
3. La IA propone nuevos candidatos.
4. El sistema actualiza la sesión de generación.
5. El guía puede seleccionar entre las nuevas opciones.

Resultado esperado: el guía puede enriquecer la propuesta antes de guardarla.

### Sesiones de generación y checkpoints

La aplicación guarda el estado de una generación IA en una sesión interna. Esto permite:

- Recordar restricciones del usuario.
- Recordar paradas propuestas.
- Recordar paradas rechazadas.
- Saber en qué punto del proceso está la generación.
- Reanudar o consultar el estado mediante identificador de sesión.

Los checkpoints principales son:

- Generación iniciada.
- Ruta generada.
- Validación de paradas.
- Selección de paradas por el guía.
- Paradas adicionales generadas.
- Ruta guardada.

## 8. Edición de rutas

Desde el detalle de una ruta, el guía puede ajustar el contenido.

### Acciones disponibles

- Cambiar título.
- Cambiar descripción.
- Cambiar duración.
- Cambiar número de personas.
- Cambiar nivel de exigencia.
- Cambiar etiquetas temáticas.
- Añadir paradas.
- Editar paradas.
- Eliminar paradas.
- Reordenar paradas.
- Recalcular trazado en el mapa.
- Gestionar curiosidades.

### Caso de uso: editar datos generales

1. El guía entra en el detalle de una ruta.
2. Modifica título o descripción.
3. Guarda.
4. La aplicación valida formato y permisos.
5. Los cambios quedan guardados.

Resultado esperado: la ruta mantiene sus paradas, pero actualiza sus datos descriptivos.

### Caso de uso: editar duración, personas o exigencia

1. El guía modifica duración, número de personas o exigencia.
2. La aplicación valida valores permitidos.
3. También comprueba el límite de personas del plan.
4. Si cumple, guarda.

Resultado esperado: los metadatos de la ruta quedan actualizados sin romper los límites del plan.

### Caso de uso: añadir parada

1. El guía introduce nombre, coordenadas y descripción opcional.
2. La aplicación comprueba el límite de paradas del plan.
3. Se añade la parada al final o en el lugar correspondiente.
4. Se recalcula el orden.
5. En rutas IA se registra auditoría del cambio.

Resultado esperado: la ruta incluye una nueva parada y mantiene un orden coherente.

### Caso de uso: eliminar parada

1. El guía selecciona una parada.
2. La elimina.
3. La aplicación comprueba que la ruta no queda por debajo del mínimo.
4. Se reordenan las paradas restantes.
5. En rutas IA se registra auditoría.

Resultado esperado: la parada desaparece y la ruta sigue siendo válida.

### Caso de uso: reordenar paradas

1. El guía cambia el orden de las paradas.
2. La aplicación valida que los identificadores pertenecen a la ruta.
3. Se actualizan los órdenes.
4. En rutas IA se registra auditoría.

Resultado esperado: el recorrido cambia de secuencia sin perder paradas.

### Auditoría en rutas generadas por IA

Cuando una ruta fue generada con IA, la aplicación registra eventos de cambio:

- Parada añadida.
- Parada modificada.
- Parada eliminada.
- Paradas reordenadas.

Esto ayuda a reconstruir cómo se ha modificado una propuesta original.

## 9. Mapas, geometría y métricas

AURA usa mapas interactivos para visualizar rutas y sesiones.

En las rutas se almacenan:

- Geometría del recorrido.
- Distancia total.
- Duración total estimada.
- Distancia entre paradas.
- Tiempo estimado entre paradas.

El trazado se calcula con GraphHopper cuando hay suficientes paradas con coordenadas.

### Caso de uso: recalcular ruta

1. El guía edita paradas o necesita actualizar el recorrido.
2. Solicita recalcular.
3. La aplicación llama al servicio de rutas.
4. Se actualiza la geometría.
5. Se devuelven nuevas métricas al frontend.

Resultado esperado: el mapa muestra un recorrido actualizado y métricas renovadas.

## 10. Curiosidades

Las curiosidades son contenidos asociados a paradas. Sirven para enriquecer la experiencia turística.

Tipos disponibles:

- Historia.
- Arquitectura.
- Personaje.
- Evento.
- Dato curioso.

Una parada puede tener una curiosidad.

### Caso de uso: generar curiosidad con IA

1. El guía entra en una parada.
2. Solicita una curiosidad.
3. Si ya existe, la aplicación la devuelve.
4. Si no existe, la aplicación la genera con IA.
5. Se guarda y queda asociada a la parada.

Resultado esperado: el guía obtiene contenido narrativo listo para usar.

### Caso de uso: previsualizar curiosidad

1. El guía solicita una curiosidad en modo previsualización.
2. Si no existe, se genera una versión sin guardarla.
3. El guía puede decidir si la usa o no.

Resultado esperado: el guía puede probar contenido sin modificar la ruta.

### Caso de uso: crear o editar curiosidad manual

1. El guía abre la gestión de curiosidad de una parada.
2. Introduce título, texto, tipo e imagen opcional.
3. La aplicación valida campos obligatorios.
4. Si hay imagen, valida formato y tamaño.
5. La curiosidad se crea o actualiza.

Resultado esperado: la parada tiene una curiosidad personalizada.

### Caso de uso: eliminar curiosidad

1. El guía selecciona una curiosidad existente.
2. Solicita eliminarla.
3. La aplicación valida permisos.
4. La curiosidad se elimina.

Resultado esperado: la parada vuelve a estar sin curiosidad asociada.

### Imágenes de curiosidades

Una curiosidad puede usar:

- Imagen generada o referenciada por URL.
- Imagen subida manualmente.

Si hay imagen manual, tiene prioridad como imagen pública.

Formatos permitidos para subida manual:

- JPEG.
- PNG.
- WebP.

Tamaño máximo:

- 5 MB.

## 11. Sesiones de tour en vivo

Una sesión convierte una ruta guardada en una experiencia en directo.

### Funciones para el guía

- Crear sesión desde una ruta.
- Ver panel de control de sesión.
- Iniciar tour.
- Pausar cronómetro.
- Reanudar cronómetro.
- Seleccionar parada actual.
- Regenerar código de acceso.
- Cerrar acceso y finalizar sesión.
- Ver participantes activos.
- Abrir mapa del guía.
- Compartir ubicación.
- Ver ubicaciones de turistas.
- Gestionar curiosidades visibles.
- Usar chat.
- Crear recordatorios Premium.

### Caso de uso: crear sesión

1. El guía abre una ruta del catálogo.
2. Solicita crear sesión.
3. La aplicación comprueba que la ruta le pertenece.
4. Si ya hay una sesión pendiente o en curso, se reutiliza esa sesión.
5. Si no hay sesión activa, se crea una nueva.
6. Se genera código de acceso.
7. Se prepara una copia cacheada de la ruta para acelerar mapas.

Resultado esperado: el guía llega al panel de sesión.

### Caso de uso: iniciar tour

1. El guía está en el panel de sesión.
2. Pulsa iniciar.
3. La sesión cambia de pendiente a en curso.
4. El cronómetro empieza a contar.
5. Los turistas pueden pasar de sala de espera a mapa.

Resultado esperado: el tour queda activo.

### Caso de uso: pausar y reanudar cronómetro

1. El tour está en curso.
2. El guía pausa el cronómetro.
3. La aplicación registra desde cuándo está pausado.
4. Al reanudar, acumula el tiempo de pausa.
5. El tiempo restante se calcula descontando pausas.

Resultado esperado: el cronómetro refleja el tiempo real de actividad del tour.

### Caso de uso: seleccionar parada actual

1. El guía selecciona una parada de la ruta.
2. La aplicación valida que pertenece a la sesión.
3. La sesión guarda esa parada como actual.
4. El estado se actualiza para mapas y participantes.

Resultado esperado: guía y turistas pueden saber en qué punto del recorrido están.

### Caso de uso: cerrar sesión

1. El guía decide finalizar el tour.
2. Pulsa cerrar acceso.
3. La sesión pasa a finalizada.
4. Los participantes activos se desactivan.
5. Ya no se aceptan nuevas ubicaciones ni mensajes.

Resultado esperado: el tour queda cerrado y protegido.

## 12. Flujo del turista

El turista no necesita cuenta. Entra con código o enlace y se identifica con un alias.

### Funcionalidades del turista

- Entrar mediante código de sesión.
- Introducir alias.
- Esperar a que el guía inicie el tour.
- Abrir mapa de la sesión.
- Ver paradas y recorrido.
- Ver ubicación del guía.
- Compartir su propia ubicación.
- Usar chat común.
- Usar chat privado si está disponible.
- Recibir alertas de recordatorios Premium.
- Ver curiosidades cuando estén disponibles o cerca.

### Caso de uso: unirse con código

1. El turista recibe un código del guía.
2. Entra en la URL de acceso por código.
3. La aplicación busca la sesión.
4. Si el código es válido, redirige al formulario de alias.
5. El turista introduce alias.
6. La aplicación comprueba capacidad.
7. El turista queda unido a la sesión.

Resultado esperado: el turista llega a la sala de espera.

### Caso de uso: sala de espera

1. El turista ya está unido.
2. Si la sesión está pendiente, espera.
3. Si la sesión está en curso, puede entrar al mapa.
4. Si la sesión finalizó, se muestra error.

Resultado esperado: el turista no entra al mapa hasta que el guía inicia el tour.

### Caso de uso: ver mapa del turista

1. La sesión está en curso.
2. El turista abre el mapa.
3. Ve paradas, geometría de ruta y estado de sesión.
4. Puede ver ubicación del guía si está disponible.
5. Puede enviar ubicación propia si concede permisos del navegador.

Resultado esperado: el turista acompaña el recorrido desde su móvil.

### Caso de uso: sesión no válida

Puede ocurrir que:

- El código no exista.
- El token sea inválido.
- La sesión haya finalizado.
- El turista no esté registrado en esa sesión.
- La sesión aún no esté activa.

Resultado esperado: la aplicación muestra un mensaje claro y no permite acceso indebido.

## 13. Ubicación en vivo

La aplicación registra ubicaciones de guía y turistas durante una sesión activa.

### Ubicación del guía

El guía comparte su posición. Los turistas pueden consultarla desde el mapa.

Reglas:

- Solo el guía propietario puede registrar su ubicación.
- La sesión debe estar en curso.
- Las coordenadas deben ser válidas.
- Se evitan registros duplicados si el guía no se ha movido suficiente o ha pasado muy poco tiempo.

### Ubicación de turistas

Cada turista puede compartir su posición.

Reglas:

- Debe estar unido a la sesión.
- La sesión debe estar en curso.
- Las coordenadas deben ser válidas.
- Se evitan duplicados por intervalo y distancia.
- La aplicación puede detectar curiosidad cercana si el turista se aproxima a una parada con contenido.

### Caso de uso: guía ve turistas en mapa

1. Los turistas comparten ubicación.
2. El guía consulta ubicaciones de turistas.
3. La aplicación devuelve la última ubicación de cada turista activo.

Resultado esperado: el guía puede ver el grupo y reaccionar si alguien se aleja.

## 14. Chat

AURA incluye chat dentro de cada sesión.

### Chat común

Disponible para todos los planes.

Permite:

- Enviar texto.
- Adjuntar imágenes.
- Consultar mensajes recientes.
- Descargar imágenes adjuntas si se pertenece a la sesión.

Validaciones:

- La sesión debe estar en curso.
- No se puede enviar mensaje vacío.
- Texto máximo: 5000 caracteres.
- Imágenes permitidas: JPEG, PNG, WebP.
- Tamaño máximo de imagen: 5 MB.

### Chat privado

Funcionalidad de plan Premium o habilitada explícitamente desde administración.

Permite:

- Mensajes privados entre guía y turista individual.
- Bandeja del guía con conversaciones privadas.
- Hilo privado por turista.

Reglas:

- El chat común sigue existiendo.
- En Freemium se bloquea el modo separado si no está habilitado.
- El guía debe indicar destinatario cuando manda un privado.
- El turista puede responder al guía en su hilo.

### Caso de uso: enviar mensaje común

1. Guía o turista escribe texto o adjunta imagen.
2. La aplicación identifica al remitente.
3. Valida sesión activa y contenido.
4. Guarda el mensaje.
5. Otros participantes lo reciben al consultar mensajes.

Resultado esperado: la comunicación grupal queda disponible durante el tour.

### Caso de uso: enviar mensaje privado

1. El guía selecciona un turista.
2. Escribe el mensaje.
3. La aplicación comprueba que el plan permite chat separado.
4. Valida que el turista pertenece a la sesión.
5. Guarda el mensaje como privado.

Resultado esperado: solo el guía y ese turista ven el mensaje en el hilo privado.

## 15. Recordatorios y quedadas programadas

Esta funcionalidad está pensada para sesiones Premium.

Permite al guía crear un recordatorio dentro de una sesión en curso. Puede incluir:

- Mensaje.
- Hora objetivo.
- Minutos de antelación para avisar.
- Ubicación de quedada.
- Etiqueta de la quedada.

### Caso de uso: crear quedada programada

1. El tour está en curso.
2. El guía crea un recordatorio.
3. Introduce mensaje y hora futura.
4. Opcionalmente marca un punto de quedada.
5. La aplicación valida que el plan permite la función.
6. La aplicación guarda el recordatorio.

Resultado esperado: los turistas recibirán una alerta cuando llegue el momento.

### Caso de uso: turista recibe alerta

1. El turista consulta alertas desde el mapa.
2. La aplicación busca recordatorios activos que ya deben notificarse.
3. Evita entregar dos veces el mismo recordatorio al mismo turista.
4. Devuelve la alerta.

Resultado esperado: cada turista recibe la notificación una sola vez.

## 16. Curiosidades durante el tour

Durante una sesión, guía y turistas pueden consultar curiosidades de paradas.

### Caso de uso: guía muestra curiosidad

1. El guía selecciona una parada.
2. Solicita mostrar su curiosidad.
3. La aplicación actualiza la visibilidad.
4. Los turistas sincronizan el estado.

Resultado esperado: una curiosidad concreta queda marcada como visible para la sesión.

### Caso de uso: turista se acerca a una parada

1. El turista comparte ubicación.
2. La aplicación calcula la parada más cercana.
3. Si está dentro del radio permitido y tiene curiosidad, la devuelve.

Resultado esperado: el turista recibe contenido contextual según su posición.

## 17. Planes Freemium y Premium

El plan controla límites y acceso a funciones.

### Freemium

Incluye:

- 1 ruta manual simultánea.
- 1 ruta IA simultánea.
- 3 generaciones IA al mes.
- 9 sustituciones IA al mes.
- Máximo 3 sustituciones IA por ruta.
- Máximo 5 paradas por ruta.
- Máximo 15 turistas por sesión.
- 1 sesión activa por ruta.
- Chat común.
- Curiosidades limitadas a 3 rutas.
- Etiquetas limitadas a Historia, Naturaleza, Religioso y Espiritual, Arquitectura y Diseño.

No incluye por defecto:

- Chat privado.
- Quedada programada.
- Uso del campo deseos en IA.

### Premium

Incluye:

- Hasta 10 rutas manuales simultáneas.
- Hasta 10 rutas IA simultáneas.
- 10 generaciones IA al mes.
- 30 sustituciones IA al mes.
- Sin límite por ruta para sustituciones IA.
- Máximo 15 paradas por ruta.
- Máximo 50 turistas por sesión.
- Varias sesiones por ruta.
- Todas las etiquetas disponibles.
- Chat común y privado.
- Quedadas programadas.
- Campo deseos en IA.
- Curiosidades sin límite de rutas.

### Gestión de límites

Cuando se supera un límite:

- La aplicación bloquea la acción.
- Devuelve un mensaje claro.
- Usa códigos internos como `TIER_LIMIT_REACHED`, `TIER_FORBIDDEN` o `TIER_CAPACITY_REACHED`.
- El frontend puede mostrar avisos o llamadas a mejorar plan.

### Caso de uso: consultar plan

1. El guía entra en su página de plan.
2. La aplicación muestra estado actual.
3. Muestra límites del plan.
4. Muestra consumo actual: rutas, generaciones IA, sustituciones, capacidad, paradas y curiosidades.
5. Si Stripe está configurado, puede mostrar acciones de upgrade o downgrade.

Resultado esperado: el guía entiende qué puede hacer y cuánto le queda.

## 18. Facturación y Stripe

AURA integra Stripe para el plan Premium.

### Funciones principales

- Crear sesión de checkout.
- Sincronizar checkout completado.
- Recibir webhooks de Stripe.
- Guardar eventos de webhook.
- Actualizar suscripción del guía.
- Programar baja al final del periodo.
- Refrescar datos de suscripción.

### Caso de uso: pasar a Premium

1. El guía pulsa mejorar plan.
2. La aplicación crea una sesión de checkout en Stripe.
3. El guía paga en Stripe.
4. Stripe redirige a la aplicación.
5. La aplicación sincroniza la sesión o recibe webhook.
6. El guía pasa a Premium si la suscripción queda activa.

Resultado esperado: los límites y funciones Premium se activan para el guía.

### Caso de uso: programar baja

1. Un guía Premium solicita cancelar renovación.
2. La aplicación pide a Stripe cancelar al final del periodo.
3. La suscripción queda marcada como baja programada.
4. El guía conserva Premium hasta fin de periodo.

Resultado esperado: no se corta el servicio antes de tiempo.

## 19. Administración

El administrador es un superusuario. Tiene acceso a zonas restringidas.

### Funcionalidades del administrador

- Entrar directamente al panel de allowlist tras iniciar sesión.
- Usar el panel de Django Admin.
- Gestionar puntos de interés autorizados.
- Buscar lugares en OpenStreetMap.
- Importar POIs desde OSM.
- Crear POIs manualmente.
- Eliminar POIs.
- Ver estadísticas básicas del panel.
- Gestionar acceso a funciones por plan desde el panel de billing.

## 20. Allowlist de puntos de interés

La allowlist es una base de datos curada de lugares autorizados. Sirve como fuente fiable para el motor de rutas.

Cada POI contiene:

- Nombre.
- Categoría.
- Coordenadas.
- Ciudad.
- Dirección.
- Fuente: manual u OpenStreetMap.
- Identificador OSM si aplica.
- Tipo OSM si aplica.

### Categorías disponibles

Incluyen museo, monumento, restaurante, café, bar, lugar de culto, parque, teatro, biblioteca, galería de arte, hotel, mirador, castillo, ruinas, mercado, plaza, cine, estadio y otro.

### Caso de uso: consultar panel

1. El administrador entra en `allowList/`.
2. Ve total de POIs.
3. Ve cuántos vienen de OSM y cuántos son manuales.
4. Puede filtrar y paginar.

Resultado esperado: el administrador tiene una visión del contenido curado.

### Caso de uso: buscar POIs en OpenStreetMap

1. El administrador abre búsqueda OSM.
2. Introduce ciudad, país y categorías.
3. La aplicación consulta Overpass/OpenStreetMap.
4. Devuelve candidatos.

Resultado esperado: el administrador puede seleccionar lugares reales para importar.

### Caso de uso: importar POIs desde OSM

1. El administrador selecciona resultados.
2. Solicita importar.
3. La aplicación evita duplicados por identificador OSM.
4. Guarda los nuevos POIs.
5. Informa cuántos se crearon, cuántos existían y cuántos fallaron.

Resultado esperado: la allowlist crece con lugares verificados.

### Caso de uso: crear POI manual

1. El administrador abre alta manual.
2. Introduce nombre, coordenadas, categoría, ciudad y dirección.
3. La aplicación valida los datos.
4. Guarda el POI con fuente manual.

Resultado esperado: se puede añadir un lugar aunque no venga de OSM.

### Caso de uso: eliminar POI

1. El administrador selecciona un POI.
2. Solicita eliminar.
3. La aplicación valida que existe.
4. Lo elimina.

Resultado esperado: el POI deja de estar disponible para la allowlist.

## 21. Panel de acceso a funcionalidades

El administrador puede activar o desactivar funcionalidades por plan.

Funciones controlables:

- Generación de rutas con IA.
- Sustitución de paradas con IA.
- Chat por separado.
- Quedada programada con notificación.
- Campo deseos con IA.

### Caso de uso: desactivar una función para Freemium

1. El administrador entra al panel de acceso.
2. Cambia el estado de una función para Freemium.
3. La aplicación guarda la configuración.
4. Desde ese momento, los guías Freemium no pueden usarla.

Resultado esperado: el producto puede cambiar reglas sin tocar el código.

## 22. Seguridad y permisos

### Reglas principales

- Las rutas pertenecen a un guía.
- Un guía solo puede editar sus propias rutas.
- Un turista no puede crear ni guardar rutas.
- Un turista solo accede a la sesión donde se ha unido.
- El administrador tiene acceso a paneles especiales.
- Las funciones sensibles se validan en backend.
- Los límites de plan no dependen solo de la interfaz.
- Las URLs de sesión usan token UUID para no exponer solo IDs internos.

### Casos bloqueados

La aplicación bloquea:

- Acceso a ruta ajena.
- Unión a sesión inexistente.
- Unión a sesión finalizada.
- Envío de mensajes en sesión no activa.
- Registro de ubicación en sesión finalizada.
- Edición de parada de otro guía.
- Uso de función Premium desde plan Freemium.
- Superación de capacidad de turistas.
- Subida de imágenes no permitidas.

## 23. Errores habituales y comportamiento esperado

### El guía no ha iniciado sesión

La aplicación pide iniciar sesión o devuelve error de autenticación.

### El usuario no es guía

La aplicación bloquea creación y gestión de rutas.

### Se supera un límite de plan

La aplicación devuelve un mensaje orientado al límite alcanzado.

Ejemplos:

- Demasiadas rutas simultáneas.
- Demasiadas generaciones IA.
- Demasiadas paradas.
- Demasiados turistas.
- Función solo disponible en Premium.

### La IA falla

La aplicación devuelve mensajes comprensibles:

- IA no disponible.
- Respuesta de IA inválida.
- Problema de conexión.
- Error inesperado al generar.

### Stripe no está configurado

La aplicación puede mostrar el plan, pero no ofrecer checkout real.

### La ubicación no es válida

La aplicación rechaza coordenadas fuera de rango.

## 24. Tareas en segundo plano y rendimiento

AURA usa tareas en segundo plano y caché para mejorar rendimiento.

### Celery y Redis

Se usan para tareas pesadas o programadas, como operaciones relacionadas con sesiones, recordatorios o procesos que no deberían bloquear la navegación.

### Caché de ruta por sesión

Cuando se crea o consulta una sesión, la aplicación guarda un resumen de la ruta:

- ID de sesión.
- ID de ruta.
- Estado.
- Paradas ordenadas.
- Geometría.
- Fecha de generación del resumen.

Esto acelera la carga de mapas del guía y turistas.

La caché se invalida cuando cambian datos relevantes de sesión, ruta o paradas.

## 25. Resumen completo de casos de uso por rol

### Visitante no registrado

- Ver landing.
- Registrarse como guía.
- Iniciar sesión.
- Acceder a enlace de tour como turista.
- Recibir error si entra a una zona privada.

### Guía Freemium

- Crear 1 ruta manual simultánea.
- Crear 1 ruta IA simultánea.
- Generar hasta 3 rutas IA al mes.
- Usar hasta 5 paradas por ruta.
- Usar hasta 15 turistas por sesión.
- Crear una sesión activa por ruta.
- Usar chat común.
- Usar etiquetas Freemium.
- Crear o mostrar curiosidades en hasta 3 rutas.
- Consultar consumo del plan.
- Mejorar a Premium si Stripe está activo.

### Guía Premium

- Crear hasta 10 rutas manuales simultáneas.
- Crear hasta 10 rutas IA simultáneas.
- Generar hasta 10 rutas IA al mes.
- Usar hasta 15 paradas por ruta.
- Usar hasta 50 turistas por sesión.
- Crear varias sesiones por ruta.
- Usar todas las etiquetas.
- Usar chat común y privado.
- Crear quedadas programadas.
- Usar campo deseos en IA.
- Usar curiosidades sin límite de rutas.
- Programar baja al final del periodo.

### Turista

- Unirse con código o enlace.
- Identificarse con alias.
- Esperar inicio del tour.
- Ver mapa.
- Ver ruta y paradas.
- Compartir ubicación.
- Ver ubicación del guía.
- Enviar mensajes comunes.
- Enviar o recibir privados si está habilitado.
- Recibir recordatorios Premium.
- Consultar curiosidades disponibles.

### Administrador

- Acceder al panel allowlist.
- Buscar POIs en OSM.
- Importar POIs.
- Crear POIs manuales.
- Eliminar POIs.
- Gestionar acceso a funciones por plan.
- Usar Django Admin para mantenimiento avanzado.

## 26. Recorrido ideal de uso de AURA

1. El guía se registra.
2. Crea una ruta manual o con IA.
3. Revisa la ruta en el catálogo.
4. Ajusta paradas, duración, etiquetas y descripción.
5. Añade curiosidades para enriquecer el discurso.
6. Crea una sesión para una fecha concreta.
7. Comparte el código con turistas.
8. Los turistas se unen con alias.
9. El guía inicia el tour.
10. Todos ven el mapa en vivo.
11. El guía y turistas comparten ubicación.
12. Se comunican por chat.
13. El guía muestra curiosidades y controla la parada actual.
14. Si es Premium, puede usar chat privado y quedadas programadas.
15. Al terminar, el guía cierra la sesión.

## 27. Glosario

- Allowlist: lista curada de lugares autorizados para usar como puntos de interés.
- Checkpoint: punto guardado dentro del proceso de generación IA.
- Freemium: plan gratuito o base con límites.
- Geometría: línea del recorrido que se pinta en el mapa.
- Guía: usuario registrado que crea y dirige tours.
- IA: inteligencia artificial usada para proponer rutas, paradas y curiosidades.
- Parada: lugar concreto dentro de una ruta.
- POI: punto de interés.
- Premium: plan ampliado con más límites y funciones.
- Sesión: ejecución en directo de una ruta.
- Token: identificador seguro incluido en enlaces de acceso a sesiones.
- Turista: participante anónimo unido a una sesión.

