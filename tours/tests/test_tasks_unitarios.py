"""
Tests unitarios para tours/tasks.py

Valida las tareas Celery para limpieza y mantenimiento.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import (
    Turista, SesionTour, TuristaSesion, MensajeChat,
    SESION_TOUR, MENSAJE_CHAT
)
from tours.tasks import barrido_mensajes_efimeros


class BarridoMensajesEfimerosTests(TestCase):
    """Tests para la tarea barrido_mensajes_efimeros"""

    def setUp(self):
        """Setup con sesión y mensajes"""
        # Crear guía y ruta
        self.guia_user = User.objects.create_user(
            username='guia_barrido', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        ruta = Ruta.objects.create(
            titulo='Ruta Barrido',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )
        
        # Crear sesión finalizada
        self.sesion = SesionTour.objects.create(
            codigo_acceso='BARR001',
            estado=SesionTour.FINALIZADO,
            fecha_inicio=timezone.now(),
            ruta=ruta,
        )
        
        # Crear turista y mensajes
        self.turista = Turista.objects.create(alias='turista_barrido')
        TuristaSesion.objects.create(
            turista=self.turista,
            sesion_tour=self.sesion,
        )

    def test_barrido_sesion_finalizada_elimina_mensajes(self):
        """Verifica que elimina mensajes de sesión finalizada"""
        # Crear algunos mensajes
        MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            nombre_remitente='Turista 1',
            texto='Mensaje 1',
        )
        MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            nombre_remitente='Turista 2',
            texto='Mensaje 2',
        )
        
        self.assertEqual(MensajeChat.objects.filter(sesion_tour=self.sesion).count(), 2)
        
        # Ejecutar tarea
        resultado = barrido_mensajes_efimeros(self.sesion.id)
        
        # Verificar que fueron eliminados
        self.assertEqual(MensajeChat.objects.filter(sesion_tour=self.sesion).count(), 0)
        self.assertIn('2 mensajes eliminados', resultado)

    def test_barrido_sesion_pendiente_no_elimina(self):
        """Verifica que NO elimina mensajes de sesión pendiente"""
        sesion_pendiente = SesionTour.objects.create(
            codigo_acceso='BARR002',
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.sesion.ruta,
        )
        
        # Crear mensaje en sesión pendiente
        MensajeChat.objects.create(
            sesion_tour=sesion_pendiente,
            turista=self.turista,
            nombre_remitente='Turista',
            texto='Mensaje en pendiente',
        )
        
        inicial = MensajeChat.objects.filter(sesion_tour=sesion_pendiente).count()
        
        # Ejecutar tarea
        resultado = barrido_mensajes_efimeros(sesion_pendiente.id)
        
        # Verificar que NO fueron eliminados
        self.assertEqual(MensajeChat.objects.filter(sesion_tour=sesion_pendiente).count(), inicial)
        self.assertIn('cancelada', resultado)

    def test_barrido_sesion_en_curso_no_elimina(self):
        """Verifica que NO elimina mensajes de sesión en curso"""
        sesion_curso = SesionTour.objects.create(
            codigo_acceso='BARR003',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.sesion.ruta,
        )
        
        # Crear mensaje en sesión en curso
        MensajeChat.objects.create(
            sesion_tour=sesion_curso,
            turista=self.turista,
            nombre_remitente='Turista',
            texto='Mensaje en curso',
        )
        
        inicial = MensajeChat.objects.filter(sesion_tour=sesion_curso).count()
        
        # Ejecutar tarea
        resultado = barrido_mensajes_efimeros(sesion_curso.id)
        
        # Verificar que NO fueron eliminados
        self.assertEqual(MensajeChat.objects.filter(sesion_tour=sesion_curso).count(), inicial)
        self.assertIn('cancelada', resultado)

    def test_barrido_sesion_inexistente(self):
        """Verifica manejo de sesión inexistente"""
        resultado = barrido_mensajes_efimeros(9999)
        
        self.assertIn('Error', resultado)
        self.assertIn('No existe', resultado)

    def test_barrido_sin_mensajes(self):
        """Verifica tarea con sesión finalizada pero sin mensajes"""
        sesion_vacia = SesionTour.objects.create(
            codigo_acceso='BARR004',
            estado=SesionTour.FINALIZADO,
            fecha_inicio=timezone.now(),
            ruta=self.sesion.ruta,
        )
        
        # Verificar que no hay mensajes
        self.assertEqual(MensajeChat.objects.filter(sesion_tour=sesion_vacia).count(), 0)
        
        # Ejecutar tarea
        resultado = barrido_mensajes_efimeros(sesion_vacia.id)
        
        # Verificar que se completó correctamente
        self.assertIn('0 mensajes eliminados', resultado)

    def test_barrido_elimina_solo_mensajes_sesion_especifica(self):
        """Verifica que solo elimina mensajes de la sesión especificada"""
        # Crear otra sesión con mensajes
        otra_sesion = SesionTour.objects.create(
            codigo_acceso='BARR005',
            estado=SesionTour.FINALIZADO,
            fecha_inicio=timezone.now(),
            ruta=self.sesion.ruta,
        )
        
        # Crear mensajes en ambas sesiones
        msg_sesion1 = MensajeChat.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            nombre_remitente='Turista 1',
            texto='Mensaje sesión 1',
        )
        msg_sesion2 = MensajeChat.objects.create(
            sesion_tour=otra_sesion,
            turista=self.turista,
            nombre_remitente='Turista 2',
            texto='Mensaje sesión 2',
        )
        
        # Ejecutar barrido solo para primera sesión
        barrido_mensajes_efimeros(self.sesion.id)
        
        # Verificar que solo mensajes de sesión 1 fueron eliminados
        self.assertFalse(
            MensajeChat.objects.filter(id=msg_sesion1.id).exists()
        )
        self.assertTrue(
            MensajeChat.objects.filter(id=msg_sesion2.id).exists()
        )

    def test_barrido_retorna_mensaje_exito(self):
        """Verifica que retorna mensaje de éxito con cantidad"""
        # Crear varios mensajes
        for i in range(5):
            MensajeChat.objects.create(
                sesion_tour=self.sesion,
                turista=self.turista,
                nombre_remitente=f'Turista {i}',
                texto=f'Mensaje {i}',
            )
        
        resultado = barrido_mensajes_efimeros(self.sesion.id)
        
        self.assertIn('5 mensajes eliminados', resultado)
        self.assertIn('Limpieza completada', resultado)

    def test_alias_compatibilidad_sesion_tour(self):
        """Verifica que el alias SESION_TOUR funciona en la tarea"""
        # Usar alias de compatibilidad
        sesion_alias = SESION_TOUR.objects.create(
            codigo_acceso='BARR006',
            estado='finalizado',  # O SESION_TOUR.FINALIZADO
            fecha_inicio=timezone.now(),
            ruta=self.sesion.ruta,
        )
        
        # Crear mensaje
        MensajeChat.objects.create(
            sesion_tour=sesion_alias,
            turista=self.turista,
            nombre_remitente='Test',
            texto='Test',
        )
        
        # Ejecutar tarea
        resultado = barrido_mensajes_efimeros(sesion_alias.id)
        
        # Verificar que se ejecutó correctamente
        self.assertIn('1 mensajes eliminados', resultado)

    def test_alias_compatibilidad_mensaje_chat(self):
        """Verifica que el alias MENSAJE_CHAT funciona con la tarea"""
        # Crear mensaje usando alias
        msg = MENSAJE_CHAT.objects.create(
            sesion_tour=self.sesion,
            turista=self.turista,
            nombre_remitente='Test Alias',
            texto='Mensaje con alias',
        )
        
        self.assertTrue(
            MENSAJE_CHAT.objects.filter(id=msg.id).exists()
        )
        
        # Ejecutar tarea
        barrido_mensajes_efimeros(self.sesion.id)
        
        # Verificar que fue eliminado
        self.assertFalse(
            MENSAJE_CHAT.objects.filter(id=msg.id).exists()
        )


class BarridoMensajesIntegracionTests(TestCase):
    """Tests de integración para barrido de mensajes"""

    def setUp(self):
        """Setup completo"""
        self.guia_user = User.objects.create_user(
            username='guia_integ', password='pass123'
        )
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Integ',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=guia,
        )

    def test_ciclo_vida_sesion_completo(self):
        """Verifica ciclo completo: pendiente → en_curso → finalizado → limpieza"""
        # Crear sesión pendiente
        sesion = SesionTour.objects.create(
            codigo_acceso='CICLO001',
            estado=SesionTour.PENDIENTE,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        
        turista = Turista.objects.create(alias='turista_ciclo')
        
        # Agregar mensajes durante sesión activa
        for i in range(3):
            MensajeChat.objects.create(
                sesion_tour=sesion,
                turista=turista,
                nombre_remitente=f'Turista {i}',
                texto=f'Mensaje {i}',
            )
        
        # Cambiar a en_curso - mensajes persisten
        sesion.estado = SesionTour.EN_CURSO
        sesion.save()
        self.assertEqual(MensajeChat.objects.filter(sesion_tour=sesion).count(), 3)
        
        # Agregar más mensajes
        MensajeChat.objects.create(
            sesion_tour=sesion,
            turista=turista,
            nombre_remitente='Nuevo',
            texto='Mensaje en curso',
        )
        self.assertEqual(MensajeChat.objects.filter(sesion_tour=sesion).count(), 4)
        
        # Finalizar sesión - mensajes aún persisten
        sesion.estado = SesionTour.FINALIZADO
        sesion.save()
        self.assertEqual(MensajeChat.objects.filter(sesion_tour=sesion).count(), 4)
        
        # Ejecutar barrido - ahora se eliminan
        barrido_mensajes_efimeros(sesion.id)
        self.assertEqual(MensajeChat.objects.filter(sesion_tour=sesion).count(), 0)

    def test_barrido_multiples_sesiones(self):
        """Verifica barrido de múltiples sesiones finalizadas"""
        sesiones_finalizadas = []
        sesiones_activas = []
        
        # Crear 3 sesiones finalizadas y 2 activas
        for i in range(3):
            sesion = SesionTour.objects.create(
                codigo_acceso=f'MULTI_FIN_{i}',
                estado=SesionTour.FINALIZADO,
                fecha_inicio=timezone.now(),
                ruta=self.ruta,
            )
            sesiones_finalizadas.append(sesion)
        
        for i in range(2):
            sesion = SesionTour.objects.create(
                codigo_acceso=f'MULTI_ACTIVA_{i}',
                estado=SesionTour.EN_CURSO,
                fecha_inicio=timezone.now(),
                ruta=self.ruta,
            )
            sesiones_activas.append(sesion)
        
        turista = Turista.objects.create(alias='turista_multi')
        
        # Agregar mensajes a todas
        for sesion in sesiones_finalizadas + sesiones_activas:
            for j in range(2):
                MensajeChat.objects.create(
                    sesion_tour=sesion,
                    turista=turista,
                    nombre_remitente=f'Turista {j}',
                    texto=f'Mensaje {j}',
                )
        
        total_mensajes = MensajeChat.objects.count()
        self.assertEqual(total_mensajes, 10)  # 5 sesiones × 2 mensajes
        
        # Ejecutar barrido para sesiones finalizadas
        for sesion in sesiones_finalizadas:
            barrido_mensajes_efimeros(sesion.id)
        
        # Verificar que solo quedan mensajes de sesiones activas
        mensajes_restantes = MensajeChat.objects.count()
        self.assertEqual(mensajes_restantes, 4)  # 2 sesiones × 2 mensajes
        
        # Verificar que sesiones activas aún tienen sus mensajes
        for sesion in sesiones_activas:
            self.assertEqual(
                MensajeChat.objects.filter(sesion_tour=sesion).count(), 2
            )
