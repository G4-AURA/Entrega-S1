"""
Tests unitarios para tours/views.py

Valida las vistas HTTP y redirecciones.
"""
import json
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.gis.geos import Point

from rutas.models import AuthUser, Guia, Ruta, Parada
from tours.models import (
    Turista, SesionTour, TuristaSesion, UbicacionVivo, MensajeChat
)
from tours import services


class JoinTourByCodeTests(TestCase):
    """Tests para vista join_tour_by_code"""

    def setUp(self):
        """Setup con sesión"""
        self.client = Client()
        
        guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Join',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='JOIN001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_codigo_valido_redirige(self):
        """Verifica que código válido redirige a join_tour"""
        response = self.client.get(
            reverse('tours:join_tour_by_code', args=['JOIN001'])
        )
        
        self.assertEqual(response.status_code, 302)
        self.assertIn(str(self.sesion.token), response.url)

    def test_codigo_insensible_mayusculas(self):
        """Verifica que código es insensible a mayúsculas"""
        response = self.client.get(
            reverse('tours:join_tour_by_code', args=['join001'])
        )
        
        self.assertEqual(response.status_code, 302)

    def test_codigo_invalido_404(self):
        """Verifica que código inválido devuelve 404"""
        response = self.client.get(
            reverse('tours:join_tour_by_code', args=['INVALIDO'])
        )
        
        self.assertEqual(response.status_code, 404)

    def test_sesion_finalizada_410(self):
        """Verifica que sesión finalizada devuelve 410"""
        self.sesion.estado = SesionTour.FINALIZADO
        self.sesion.save()
        
        response = self.client.get(
            reverse('tours:join_tour_by_code', args=['JOIN001'])
        )
        
        self.assertEqual(response.status_code, 410)


class JoinTourTests(TestCase):
    """Tests para vista join_tour"""

    def setUp(self):
        """Setup con sesión"""
        self.client = Client()
        
        guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Join2',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='JOIN002',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_get_muestra_formulario(self):
        """Verifica que GET muestra el formulario de alias"""
        response = self.client.get(
            reverse('tours:join_tour', args=[self.sesion.token])
        )
        
        self.assertEqual(response.status_code, 200)
        # Verificar templates usadas en la respuesta
        template_names = [t.name for t in response.templates]
        self.assertIn('tours/join_tour.html', template_names)

    def test_post_valido_crea_turista(self):
        """Verifica que POST válido crea turista y redirige"""
        response = self.client.post(
            reverse('tours:join_tour', args=[self.sesion.token]),
            {'alias': 'Juan'},
        )
        
        self.assertEqual(response.status_code, 302)
        # Verificar que turista fue creado
        self.assertTrue(Turista.objects.filter(alias='Juan').exists())

    def test_post_alias_corto_error(self):
        """Verifica error si alias es muy corto"""
        response = self.client.post(
            reverse('tours:join_tour', args=[self.sesion.token]),
            {'alias': 'A'},
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('al menos 2 caracteres', response.content.decode())

    def test_post_alias_largo_error(self):
        """Verifica error si alias es muy largo"""
        response = self.client.post(
            reverse('tours:join_tour', args=[self.sesion.token]),
            {'alias': 'A' * 51},
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('no puede exceder 50', response.content.decode())

    def test_post_alias_duplicado_error(self):
        """Verifica error si alias ya existe activo"""
        turista = Turista.objects.create(alias='Carlos')
        TuristaSesion.objects.create(
            turista=turista,
            sesion_tour=self.sesion,
            activo=True,
        )
        
        response = self.client.post(
            reverse('tours:join_tour', args=[self.sesion.token]),
            {'alias': 'Carlos'},
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('ya está en uso', response.content.decode())

    def test_post_sesion_finalizada_410(self):
        """Verifica error si sesión está finalizada"""
        self.sesion.estado = SesionTour.FINALIZADO
        self.sesion.save()
        
        response = self.client.post(
            reverse('tours:join_tour', args=[self.sesion.token]),
            {'alias': 'Pedro'},
        )
        
        self.assertEqual(response.status_code, 410)


class CrearSesionTests(TestCase):
    """Tests para vista crear_sesion"""

    def setUp(self):
        """Setup con usuario autenticado"""
        self.client = Client()
        self.guia_user = User.objects.create_user(
            username='guia_crear', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        self.guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Crear',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=self.guia,
        )

    def test_crear_sesion_sin_ruta_id_error(self):
        """Verifica error si falta ruta_id"""
        self.client.force_login(self.guia_user)
        
        response = self.client.get(reverse('tours:crear_sesion'))
        
        self.assertEqual(response.status_code, 400)

    def test_crear_sesion_ruta_inexistente_404(self):
        """Verifica error si ruta no existe"""
        self.client.force_login(self.guia_user)
        
        response = self.client.get(
            reverse('tours:crear_sesion'),
            {'ruta_id': 9999},
        )
        
        self.assertEqual(response.status_code, 404)

    def test_crear_sesion_usuario_no_autenticado_redirect(self):
        """Verifica redirección si usuario no autenticado"""
        response = self.client.get(
            reverse('tours:crear_sesion'),
            {'ruta_id': self.ruta.id},
        )
        
        self.assertEqual(response.status_code, 302)

    def test_crear_sesion_usuario_no_es_guia_403(self):
        """Verifica error si usuario no es guía de la ruta"""
        otro_user = User.objects.create_user(
            username='otro_guia', password='pass123'
        )
        self.client.force_login(otro_user)
        
        response = self.client.get(
            reverse('tours:crear_sesion'),
            {'ruta_id': self.ruta.id},
        )
        
        self.assertEqual(response.status_code, 403)

    def test_crear_sesion_exitosa(self):
        """Verifica creación exitosa de sesión"""
        self.client.force_login(self.guia_user)
        
        response = self.client.get(
            reverse('tours:crear_sesion'),
            {'ruta_id': self.ruta.id},
        )
        
        self.assertEqual(response.status_code, 302)
        # Verificar que sesión fue creada
        self.assertTrue(SesionTour.objects.filter(ruta=self.ruta).exists())

    def test_crear_sesion_idempotencia_redirige_si_existente(self):
        """Verifica que redirige a sesión activa si ya existe y no crea duplicados"""
        sesion_existente = SesionTour.objects.create(
            codigo_acceso='EXIST1',
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        self.client.force_login(self.guia_user)
        
        response = self.client.get(
            reverse('tours:crear_sesion'),
            {'ruta_id': self.ruta.id},
        )
        
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('tours:guia_sesion', args=[sesion_existente.id]), response.url)
        # Verificar que NO se crearon nuevas sesiones (sólo debería existir la original)
        self.assertEqual(SesionTour.objects.filter(ruta=self.ruta).count(), 1)


class IniciarTourTests(TestCase):
    """Tests para vista iniciar_tour"""

    def setUp(self):
        """Setup con sesión pendiente"""
        self.client = Client()
        
        self.guia_user = User.objects.create_user(
            username='guia_iniciar', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Iniciar',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='INIT001',
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_iniciar_sin_autenticacion_redirect(self):
        """Verifica redirección si no autenticado"""
        response = self.client.post(
            reverse('tours:iniciar_tour', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 302)

    def test_iniciar_sesion_pendiente(self):
        """Verifica que inicia sesión pendiente"""
        self.client.force_login(self.guia_user)
        
        response = self.client.post(
            reverse('tours:iniciar_tour', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, SesionTour.EN_CURSO)
        self.assertEqual(data['estado'], 'en_curso')

    def test_iniciar_sesion_finalizada_error(self):
        """Verifica error al intentar iniciar sesión finalizada"""
        self.sesion.estado = SesionTour.FINALIZADO
        self.sesion.save()
        
        self.client.force_login(self.guia_user)
        
        response = self.client.post(
            reverse('tours:iniciar_tour', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 400)


class EstadoCronometroTests(TestCase):
    """Tests para vista estado_cronometro"""

    def setUp(self):
        """Setup con sesión"""
        self.client = Client()
        
        guia_user = User.objects.create_user(username='guia', password='pass123')
        auth_guia = AuthUser.objects.create(user=guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Crono',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='CRONO001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_estado_cronometro_sin_acceso_403(self):
        """Verifica error sin acceso"""
        response = self.client.get(
            reverse('tours:estado_cronometro', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 403)

    def test_estado_cronometro_con_acceso(self):
        """Verifica obtención de estado"""
        turista = Turista.objects.create(alias='turista_crono')
        TuristaSesion.objects.create(
            turista=turista,
            sesion_tour=self.sesion,
            activo=True,
        )
        
        self.client.get(reverse('tours:join_tour', args=[self.sesion.token]))
        self.client.post(
            reverse('tours:join_tour', args=[self.sesion.token]),
            {'alias': 'turista_crono'},
        )
        # Obtain turista_id from session
        session = self.client.session
        turista_id = session.get('turista_id')
        if turista_id:
            response = self.client.get(
                reverse('tours:estado_cronometro', args=[self.sesion.id])
            )
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertEqual(data['estado'], 'en_curso')


class SeleccionarParadaActualTests(TestCase):
    """Tests para vista seleccionar_parada_actual"""

    def setUp(self):
        """Setup con paradas"""
        self.client = Client()
        
        self.guia_user = User.objects.create_user(
            username='guia_parada', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Parada',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.parada = Parada.objects.create(
            ruta=self.ruta,
            nombre='Parada Test',
            orden=1,
            coordenadas=Point(37.3891, -5.9845),
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='PARADA001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

    def test_seleccionar_parada_sin_autenticacion_redirect(self):
        """Verifica redirección sin autenticación"""
        response = self.client.post(
            reverse('tours:seleccionar_parada_actual', args=[self.sesion.id]),
            json.dumps({'parada_id': self.parada.id}),
            content_type='application/json',
        )
        
        self.assertEqual(response.status_code, 302)

    def test_seleccionar_parada_json_invalido(self):
        """Verifica error con JSON inválido"""
        self.client.force_login(self.guia_user)
        
        response = self.client.post(
            reverse('tours:seleccionar_parada_actual', args=[self.sesion.id]),
            'invalid json',
            content_type='application/json',
        )
        
        self.assertEqual(response.status_code, 400)

    def test_seleccionar_parada_sin_parada_id(self):
        """Verifica error sin parada_id"""
        self.client.force_login(self.guia_user)
        
        response = self.client.post(
            reverse('tours:seleccionar_parada_actual', args=[self.sesion.id]),
            json.dumps({}),
            content_type='application/json',
        )
        
        self.assertEqual(response.status_code, 400)

    def test_seleccionar_parada_exitoso(self):
        """Verifica selección exitosa"""
        self.client.force_login(self.guia_user)
        
        response = self.client.post(
            reverse('tours:seleccionar_parada_actual', args=[self.sesion.id]),
            json.dumps({'parada_id': self.parada.id}),
            content_type='application/json',
        )
        
        self.assertEqual(response.status_code, 200)
        
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.parada_actual, self.parada)


class RegenerarCodigoTests(TestCase):
    """Tests para vista regenerar_codigo"""

    def setUp(self):
        """Setup con sesión"""
        self.client = Client()
        
        self.guia_user = User.objects.create_user(
            username='guia_regen', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Regen',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='REGEN001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_regenerar_codigo_sin_autenticacion_redirect(self):
        """Verifica redirección sin autenticación"""
        response = self.client.post(
            reverse('tours:regenerar_codigo', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 302)

    def test_regenerar_codigo_exitoso(self):
        """Verifica regeneración exitosa"""
        codigo_viejo = self.sesion.codigo_acceso
        
        self.client.force_login(self.guia_user)
        response = self.client.post(
            reverse('tours:regenerar_codigo', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 200)
        
        self.sesion.refresh_from_db()
        self.assertNotEqual(self.sesion.codigo_acceso, codigo_viejo)


class CerrarAccesoTests(TestCase):
    """Tests para vista cerrar_acceso"""

    def setUp(self):
        """Setup con sesión"""
        self.client = Client()
        
        self.guia_user = User.objects.create_user(
            username='guia_cerrar', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Cerrar',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='CERRAR001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_cerrar_acceso_exitoso(self):
        """Verifica cierre exitoso de sesión"""
        self.client.force_login(self.guia_user)
        
        response = self.client.post(
            reverse('tours:cerrar_acceso', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 200)
        
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.estado, SesionTour.FINALIZADO)


class ParticipantesSesionTests(TestCase):
    """Tests para vista participantes_sesion"""

    def setUp(self):
        """Setup con participantes"""
        self.client = Client()
        
        self.guia_user = User.objects.create_user(
            username='guia_particip', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Particip',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='PARTICIP001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )
        
        self.turista1 = Turista.objects.create(alias='turista1')
        TuristaSesion.objects.create(
            turista=self.turista1,
            sesion_tour=self.sesion,
            activo=True,
        )

    def test_participantes_sin_autenticacion_redirect(self):
        """Verifica redirección sin autenticación"""
        response = self.client.get(
            reverse('tours:participantes_sesion', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 302)

    def test_participantes_exitoso(self):
        """Verifica obtención de participantes"""
        self.client.force_login(self.guia_user)
        
        response = self.client.get(
            reverse('tours:participantes_sesion', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        self.assertEqual(len(data['participantes']), 1)
        self.assertEqual(data['participantes'][0]['alias'], 'turista1')


class RegistrarUbicacionTests(TestCase):
    """Tests para vistas de ubicación"""

    def setUp(self):
        """Setup con sesión"""
        self.client = Client()
        
        self.guia_user = User.objects.create_user(
            username='guia_ubicacion', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Ubicación',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='UBI001',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_registrar_ubicacion_sin_autenticacion_redirect(self):
        """Verifica redirección sin autenticación"""
        response = self.client.post(
            reverse('tours:registrar_ubicacion'),
            json.dumps({
                'sesion_id': self.sesion.id,
                'latitud': 37.3891,
                'longitud': -5.9845,
            }),
            content_type='application/json',
        )
        
        self.assertEqual(response.status_code, 302)

    def test_registrar_ubicacion_coordenadas_invalidas(self):
        """Verifica error con coordenadas inválidas"""
        self.client.force_login(self.guia_user)
        
        response = self.client.post(
            reverse('tours:registrar_ubicacion'),
            json.dumps({
                'sesion_id': self.sesion.id,
                'latitud': 'no_numero',
                'longitud': -5.9845,
            }),
            content_type='application/json',
        )
        
        self.assertEqual(response.status_code, 400)

    def test_registrar_ubicacion_coordenadas_fuera_rango(self):
        """Verifica error con coordenadas fuera de rango"""
        self.client.force_login(self.guia_user)
        
        response = self.client.post(
            reverse('tours:registrar_ubicacion'),
            json.dumps({
                'sesion_id': self.sesion.id,
                'latitud': 91.0,
                'longitud': -5.9845,
            }),
            content_type='application/json',
        )
        
        self.assertEqual(response.status_code, 400)

    def test_registrar_ubicacion_exitosa(self):
        """Verifica registro exitoso de ubicación"""
        self.client.force_login(self.guia_user)
        
        response = self.client.post(
            reverse('tours:registrar_ubicacion'),
            json.dumps({
                'sesion_id': self.sesion.id,
                'latitud': 37.3891,
                'longitud': -5.9845,
            }),
            content_type='application/json',
        )
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.content)
        
        self.assertEqual(data['latitud'], 37.3891)
        self.assertTrue(UbicacionVivo.objects.filter(id=data['ubicacion_id']).exists())


class ObtenerUbicacionGuiaTests(TestCase):
    """Tests para obtener_ubicacion_guia"""

    def setUp(self):
        """Setup con ubicación del guía"""
        self.client = Client()
        
        self.guia_user = User.objects.create_user(
            username='guia_ubi2', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Ubi2',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        self.sesion = SesionTour.objects.create(
            codigo_acceso='UBI002',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )

    def test_obtener_ubicacion_sin_ubicacion_404(self):
        """Verifica error si no hay ubicación"""
        response = self.client.get(
            reverse('tours:ubicacion_guia', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 404)

    def test_obtener_ubicacion_exitosa(self):
        """Verifica obtención de ubicación"""
        ubicacion = UbicacionVivo.objects.create(
            coordenadas=Point(-5.9845, 37.3891),
            timestamp=timezone.now(),
            sesion_tour=self.sesion,
            usuario=self.guia_user,
        )
        
        response = self.client.get(
            reverse('tours:ubicacion_guia', args=[self.sesion.id])
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        self.assertEqual(data['lat'], 37.3891)
        self.assertEqual(data['lng'], -5.9845)
