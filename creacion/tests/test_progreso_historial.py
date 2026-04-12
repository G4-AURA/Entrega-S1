import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from creacion.models import Historial_ia
from rutas.models import AuthUser, Guia

class ProgresoGeneracionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='guia_progreso', password='1234')
        self.client.force_login(self.user)
        self.auth_profile = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_profile)

        Historial_ia.objects.create(
            prompt='{}',
            estado_tarea='completado',
            etapa_actual='finalizado',
            duracion_generacion=12.0,
            duracion_validacion=4.0,
            duracion_scoring=3.0,
            duracion_optimizacion=1.0,
            duracion_total=20.0
        )
        Historial_ia.objects.create(
            prompt='{}',
            estado_tarea='completado',
            etapa_actual='finalizado',
            duracion_generacion=8.0,
            duracion_validacion=4.0,
            duracion_scoring=1.0,
            duracion_optimizacion=3.0,
            duracion_total=16.0
        )
    def test_progreso_retorna_401_sin_login(self):
        client_anon = Client()
        url = reverse('creacion:obtener_progreso_generacion', kwargs={'historial_id': 999})
        response = client_anon.get(url)
        self.assertEqual(response.status_code, 401)

    def test_progreso_historial_completado(self):
        historial = Historial_ia.objects.create(
            prompt='{}',
            estado_tarea='completado',
            etapa_actual='finalizado'
        )
        url = reverse('creacion:obtener_progreso_generacion', kwargs={'historial_id': historial.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        datos = response.json()['datos']
        self.assertEqual(datos['cargando_porcentaje'], 100.0)
        self.assertEqual(datos['eta_segundos'], 0.0)
        self.assertIsNone(datos['mensaje_error'])

    def test_progreso_historial_error(self):
        historial = Historial_ia.objects.create(
            prompt='{}',
            estado_tarea='error',
            etapa_actual='generacion',
            mensaje_error='Error de conexión IA'
        )
        url = reverse('creacion:obtener_progreso_generacion', kwargs={'historial_id': historial.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        datos = response.json()['datos']
        self.assertEqual(datos['cargando_porcentaje'], 100.0)
        self.assertEqual(datos['eta_segundos'], 0.0)
        self.assertEqual(datos['mensaje_error'], 'Error de conexión IA')

    def test_progreso_historial_procesando_etapa_inicial(self):
        historial = Historial_ia.objects.create(
            prompt='{}',
            estado_tarea='procesando',
            etapa_actual='generacion',
            timestamp_inicio_etapa=timezone.now()
        )
        url = reverse('creacion:obtener_progreso_generacion', kwargs={'historial_id': historial.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        datos = response.json()['datos']
        
        self.assertGreater(datos['eta_segundos'], 10.0)
        self.assertEqual(datos['detalle_etapas']['generacion']['estado'], 'procesando')
        self.assertEqual(datos['detalle_etapas']['validacion']['estado'], 'pendiente')

    def test_progreso_historial_procesando_etapa_avanzada(self):
        historial = Historial_ia.objects.create(
            prompt='{}',
            estado_tarea='procesando',
            etapa_actual='scoring',
            timestamp_inicio_etapa=timezone.now()
        )
        url = reverse('creacion:obtener_progreso_generacion', kwargs={'historial_id': historial.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        datos = response.json()['datos']
        
        self.assertGreaterEqual(datos['cargando_porcentaje'], 77.0)
        self.assertEqual(datos['detalle_etapas']['generacion']['estado'], 'completado')
        self.assertEqual(datos['detalle_etapas']['validacion']['estado'], 'completado')
        self.assertEqual(datos['detalle_etapas']['scoring']['estado'], 'procesando')
        self.assertEqual(datos['detalle_etapas']['optimizacion']['estado'], 'pendiente')

    def test_tope_seguridad_progreso(self):
        timestamp_antiguo = timezone.now() - timezone.timedelta(seconds=100)
        historial = Historial_ia.objects.create(
            prompt='{}',
            estado_tarea='procesando',
            etapa_actual='generacion',
            timestamp_inicio_etapa=timestamp_antiguo
        )
        url = reverse('creacion:obtener_progreso_generacion', kwargs={'historial_id': historial.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        datos = response.json()['datos']
        
        self.assertLess(datos['cargando_porcentaje'], 60.0)
        self.assertEqual(datos['detalle_etapas']['generacion']['progreso_interno'], 99.0)
        self.assertAlmostEqual(datos['eta_segundos'], 8.0, places=1)
