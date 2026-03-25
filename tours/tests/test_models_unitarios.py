"""
Tests unitarios para tours/models.py

Valida la lógica de modelos, propiedades, y relaciones.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from django.contrib.gis.geos import Point
import uuid

from rutas.models import AuthUser, Guia, Ruta, Parada
from tours.models import (
    Turista, SesionTour, TuristaSesion, UbicacionVivo, MensajeChat,
    TURISTA, SESION_TOUR, TURISTASESION, UBICACION_VIVO, MENSAJE_CHAT
)


class TuristaModelTests(TestCase):
    """Tests para el modelo Turista"""

    def test_crear_turista_anonimo(self):
        """Verifica creación de turista anónimo sin usuario"""
        turista = Turista.objects.create(alias='turista_test')
        self.assertIsNone(turista.user)
        self.assertEqual(turista.alias, 'turista_test')
        self.assertEqual(str(turista), 'turista_test')

    def test_crear_turista_con_usuario(self):
        """Verifica creación de turista con usuario (compatibilidad histórica)"""
        user = User.objects.create_user(username='user_test', password='pass123')
        turista = Turista.objects.create(user=user, alias='turista_con_user')
        self.assertEqual(turista.user, user)
        self.assertEqual(turista.alias, 'turista_con_user')

    def test_alias_vacio_se_permite(self):
        """Verifica que alias vacío se crea (no es requerido)"""
        turista = Turista.objects.create(alias='')
        self.assertEqual(turista.alias, '')

    def test_turista_str_representation(self):
        """Verifica la representación en string del turista"""
        turista = Turista.objects.create(alias='juan')
        self.assertEqual(str(turista), 'juan')

    def test_turista_db_table_name(self):
        """Verifica el nombre de la tabla en BD"""
        self.assertEqual(Turista._meta.db_table, 'tours_turista')


class SesionTourModelTests(TestCase):
    """Tests para el modelo SesionTour"""

    def setUp(self):
        """Crear guía y ruta para las pruebas"""
        self.guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        self.guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Test',
            descripcion='Descripción',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=self.guia,
        )

    def test_crear_sesion_por_defecto_pendiente(self):
        """Verifica que una sesión nueva es PENDIENTE por defecto"""
        sesion = SesionTour.objects.create(
            codigo_acceso='TEST001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.assertEqual(sesion.estado, SesionTour.PENDIENTE)
        self.assertFalse(sesion.esta_activa)
        self.assertFalse(sesion.esta_finalizada)

    def test_sesion_token_unico(self):
        """Verifica que cada sesión tiene token único e inmutable"""
        sesion1 = SesionTour.objects.create(
            codigo_acceso='TEST002',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        sesion2 = SesionTour.objects.create(
            codigo_acceso='TEST003',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.assertNotEqual(sesion1.token, sesion2.token)
        self.assertIsInstance(sesion1.token, uuid.UUID)

    def test_codigo_acceso_unico(self):
        """Verifica que código de acceso es único"""
        SesionTour.objects.create(
            codigo_acceso='UNICO001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        with self.assertRaises(Exception):
            SesionTour.objects.create(
                codigo_acceso='UNICO001',
                fecha_inicio=timezone.now(),
                ruta=self.ruta,
            )

    def test_esta_activa_property(self):
        """Verifica la propiedad esta_activa"""
        sesion = SesionTour.objects.create(
            codigo_acceso='ACTIVA001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.assertTrue(sesion.esta_activa)

    def test_esta_finalizada_property(self):
        """Verifica la propiedad esta_finalizada"""
        sesion = SesionTour.objects.create(
            codigo_acceso='FINAL001',
            estado=SesionTour.FINALIZADO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.assertTrue(sesion.esta_finalizada)

    def test_parada_actual_null(self):
        """Verifica que parada_actual puede ser null"""
        sesion = SesionTour.objects.create(
            codigo_acceso='NOPARA001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.assertIsNone(sesion.parada_actual)

    def test_parada_actual_relacion(self):
        """Verifica relación con parada_actual"""
        parada = Parada.objects.create(
            ruta=self.ruta,
            nombre='Parada 1',
            orden=1,
            coordenadas=Point(37.3891, -5.9845),
        )
        sesion = SesionTour.objects.create(
            codigo_acceso='PARA001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
            parada_actual=parada,
        )
        self.assertEqual(sesion.parada_actual, parada)

    def test_sesion_str_representation(self):
        """Verifica la representación en string"""
        sesion = SesionTour.objects.create(
            codigo_acceso='STR001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        expected = f"{self.ruta.titulo} – STR001"
        self.assertEqual(str(sesion), expected)

    def test_sesion_db_table_name(self):
        """Verifica el nombre de la tabla en BD"""
        self.assertEqual(SesionTour._meta.db_table, 'tours_sesion_tour')

    def test_turistas_many_to_many(self):
        """Verifica relación M2M con turistas"""
        sesion = SesionTour.objects.create(
            codigo_acceso='M2M001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        turista = Turista.objects.create(alias='turista_m2m')
        sesion.turistas.add(turista)
        self.assertIn(turista, sesion.turistas.all())


class TuristaSesionModelTests(TestCase):
    """Tests para el modelo TuristaSesion"""

    def setUp(self):
        """Setup inicial"""
        self.guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        self.guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Test',
            descripcion='Descripción',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=self.guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='TEST001',
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.turista = Turista.objects.create(alias='turista_test')

    def test_crear_turista_sesion(self):
        """Verifica creación de relación TuristaSesion"""
        ts = TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
        )
        self.assertTrue(ts.activo)
        self.assertIsNotNone(ts.fecha_union)

    def test_turista_sesion_activo_por_defecto(self):
        """Verifica que activo es True por defecto"""
        ts = TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
        )
        self.assertTrue(ts.activo)

    def test_turista_sesion_unico_junto(self):
        """Verifica que la combinación turista+sesion es única"""
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
        )
        with self.assertRaises(Exception):
            TuristaSesion.objects.create(
                turista=self.turista,
                sesion_tour=self.sesion,
            )

    def test_turista_sesion_str_representation(self):
        """Verifica la representación en string"""
        ts = TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
        )
        expected = f"{self.turista.alias} – {self.sesion.codigo_acceso}"
        self.assertEqual(str(ts), expected)

    def test_turista_sesion_desactivacion(self):
        """Verifica que se puede desactivar sin eliminar"""
        ts = TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
        )
        ts.activo = False
        ts.save()
        ts.refresh_from_db()
        self.assertFalse(ts.activo)
        # Verificar que el registro sigue en BD
        self.assertTrue(
            TuristaSesion.objects.filter(id=ts.id).exists()
        )


class UbicacionVivoModelTests(TestCase):
    """Tests para el modelo UbicacionVivo"""

    def setUp(self):
        """Setup inicial"""
        self.user = User.objects.create_user(username='user', password='pass123')
        self.turista = Turista.objects.create(alias='turista_ubicacion')
        
        guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Test',
            descripcion='Descripción',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='TEST001',
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_ubicacion_vivo_usuario(self):
        """Verifica creación de ubicación para usuario"""
        punto = Point(-5.9845, 37.3891)
        ubicacion = UbicacionVivo.objects.create(
            coordenadas=punto,
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            usuario=self.user,
        )
        self.assertEqual(ubicacion.usuario, self.user)
        self.assertIsNone(ubicacion.turista)

    def test_ubicacion_vivo_turista(self):
        """Verifica creación de ubicación para turista"""
        punto = Point(-5.9845, 37.3891)
        ubicacion = UbicacionVivo.objects.create(
            coordenadas=punto,
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            turista=self.turista,
        )
        self.assertEqual(ubicacion.turista, self.turista)
        self.assertIsNone(ubicacion.usuario)

    def test_ubicacion_vivo_sin_coordenadas(self):
        """Verifica que coordenadas puede ser null"""
        ubicacion = UbicacionVivo.objects.create(
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            turista=self.turista,
        )
        self.assertIsNone(ubicacion.coordenadas)

    def test_ubicacion_vivo_str_usuario(self):
        """Verifica str() para ubicación de usuario"""
        ubicacion = UbicacionVivo.objects.create(
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            usuario=self.user,
        )
        self.assertIn(self.user.username, str(ubicacion))

    def test_ubicacion_vivo_str_turista(self):
        """Verifica str() para ubicación de turista"""
        ubicacion = UbicacionVivo.objects.create(
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            turista=self.turista,
        )
        self.assertIn(self.turista.alias, str(ubicacion))


class MensajeChatModelTests(TestCase):
    """Tests para el modelo MensajeChat"""

    def setUp(self):
        """Setup inicial"""
        self.user = User.objects.create_user(username='user', password='pass123')
        self.turista = Turista.objects.create(alias='turista_chat')
        
        guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Test',
            descripcion='Descripción',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='TEST001',
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_crear_mensaje_remitente_usuario(self):
        """Verifica creación de mensaje enviado por usuario"""
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            remitente=self.user,
            nombre_remitente='Juan',
            texto='Hola a todos',
        )
        self.assertEqual(mensaje.remitente, self.user)
        self.assertIsNone(mensaje.turista)
        self.assertEqual(mensaje.nombre_remitente, 'Juan')

    def test_crear_mensaje_remitente_turista(self):
        """Verifica creación de mensaje enviado por turista"""
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            nombre_remitente='Anónimo',
            texto='Pregunta del turista',
        )
        self.assertEqual(mensaje.turista, self.turista)
        self.assertIsNone(mensaje.remitente)

    def test_mensaje_nombre_remitente_default(self):
        """Verifica el valor por defecto de nombre_remitente"""
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            texto='Texto del mensaje',
        )
        self.assertEqual(mensaje.nombre_remitente, 'Anónimo')

    def test_mensaje_chat_momento_automatico(self):
        """Verifica que momento se asigna automáticamente"""
        import time
        antes = timezone.now()
        time.sleep(0.01)  # Pequeña pausa para asegurar diferencia de tiempo
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            texto='Mensaje con timestamp',
        )
        time.sleep(0.01)
        despues = timezone.now()
        self.assertGreaterEqual(mensaje.momento, antes)
        self.assertLessEqual(mensaje.momento, despues)

    def test_mensaje_chat_str_representation(self):
        """Verifica la representación en string"""
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            nombre_remitente='Pedro',
            texto='Este es un mensaje largo que debe acortarse',
        )
        str_msg = str(mensaje)
        self.assertIn('Pedro', str_msg)
        self.assertIn('Este es un mensaje largo', str_msg)

    def test_mensaje_chat_ordering(self):
        """Verifica que los mensajes se ordenan por momento"""
        msg1 = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            texto='Primer mensaje',
        )
        msg2 = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            texto='Segundo mensaje',
        )
        msgs = list(MensajeChat.objects.all())
        self.assertEqual(msgs[0], msg1)
        self.assertEqual(msgs[1], msg2)

    def test_mensaje_con_imagen(self):
        """Verifica que imagen puede ser agregada"""
        mensaje = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            texto='Mensaje con imagen',
            imagen=None,  # En test real sería un archivo
        )
        # FieldFile(None) no es None, comparar con bool(imagen)
        self.assertFalse(bool(mensaje.imagen))


class ModeloAliasesCompatibilidadTests(TestCase):
    """Tests para verificar los aliases de compatibilidad"""

    def test_alias_turista(self):
        """Verifica que TURISTA es alias de Turista"""
        self.assertIs(TURISTA, Turista)

    def test_alias_sesion_tour(self):
        """Verifica que SESION_TOUR es alias de SesionTour"""
        self.assertIs(SESION_TOUR, SesionTour)

    def test_alias_turistasesion(self):
        """Verifica que TURISTASESION es alias de TuristaSesion"""
        self.assertIs(TURISTASESION, TuristaSesion)

    def test_alias_ubicacion_vivo(self):
        """Verifica que UBICACION_VIVO es alias de UbicacionVivo"""
        self.assertIs(UBICACION_VIVO, UbicacionVivo)

    def test_alias_mensaje_chat(self):
        """Verifica que MENSAJE_CHAT es alias de MensajeChat"""
        self.assertIs(MENSAJE_CHAT, MensajeChat)
