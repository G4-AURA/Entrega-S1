"""
tours/models.py
"""
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.gis.db import models as gis_models
from django.db import models

from rutas.models import Ruta


class Turista(models.Model):
    """
    Participante anónimo en un tour.

    El campo `user` se conserva en BD por compatibilidad con migraciones previas,
    pero ya no se asigna: todos los turistas son anónimos y se identifican
    únicamente por alias + cookie de sesión Django.
    TODO: eliminar `user` en una migración futura cuando se confirme que no hay
    datos históricos con usuario asignado.
    """
    # Deprecated — siempre null en nuevos registros
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, null=True, blank=True
    )
    alias = models.CharField(max_length=50)

    class Meta:
        db_table = "tours_turista"
        verbose_name = "Turista"
        verbose_name_plural = "Turistas"

    def __str__(self) -> str:
        return self.alias


class SesionTour(models.Model):
    PENDIENTE = "pendiente"
    EN_CURSO = "en_curso"
    FINALIZADO = "finalizado"

    ESTADO_CHOICES = [
        (PENDIENTE, "Pendiente"),
        (EN_CURSO, "En Curso"),
        (FINALIZADO, "Finalizado"),
    ]

    codigo_acceso = models.CharField(max_length=50, unique=True)
    # UUID inmutable usado como token en URLs /live/ — más seguro que exponer el PK
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    estado = models.CharField(
        max_length=20, choices=ESTADO_CHOICES, default=PENDIENTE
    )
    fecha_inicio = models.DateTimeField()
    ruta = models.ForeignKey(
        Ruta, on_delete=models.CASCADE, related_name="sesiones"
    )
    turistas = models.ManyToManyField(
        Turista, through="TuristaSesion", blank=True
    )
    parada_actual = models.ForeignKey(
        "rutas.Parada",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sesiones_actuales",
    )

    class Meta:
        db_table = "tours_sesion_tour"
        verbose_name = "Sesión de Tour"
        verbose_name_plural = "Sesiones de Tour"
        indexes = [
            models.Index(fields=["estado", "fecha_inicio"]),
        ]

    def __str__(self) -> str:
        return f"{self.ruta.titulo} – {self.codigo_acceso}"

    @property
    def esta_activa(self) -> bool:
        return self.estado == self.EN_CURSO

    @property
    def esta_finalizada(self) -> bool:
        return self.estado == self.FINALIZADO


class TuristaSesion(models.Model):
    """
    Tabla intermedia del M2M Turista ↔ SesionTour.
    `activo=False` permite desconectar sin borrar historial.
    """
    turista = models.ForeignKey(Turista, on_delete=models.CASCADE)
    sesion_tour = models.ForeignKey(SesionTour, on_delete=models.CASCADE)
    fecha_union = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "tours_turistasesion"
        unique_together = ["turista", "sesion_tour"]
        verbose_name = "Turista en Sesión"
        verbose_name_plural = "Turistas en Sesión"

    def __str__(self) -> str:
        return f"{self.turista.alias} – {self.sesion_tour.codigo_acceso}"


class UbicacionVivo(models.Model):
    """
    Snapshot GPS dentro de una sesión activa.
    Puede pertenecer al guía autenticado (`usuario`) o a un turista anónimo
    (`turista`) según el origen del reporte.
    """
    coordenadas = gis_models.PointField(null=True, blank=True)
    timestamp = models.DateTimeField()
    sesion_tour = models.ForeignKey(SesionTour, on_delete=models.CASCADE)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    turista = models.ForeignKey(
        Turista,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ubicaciones_vivas",
    )

    class Meta:
        db_table = "tours_ubicacion_vivo"
        verbose_name = "Ubicación en Vivo"
        verbose_name_plural = "Ubicaciones en Vivo"
        indexes = [
            # Optimiza obtener la última posición del guía sin full-scan
            models.Index(fields=["sesion_tour", "usuario", "-timestamp"]),
        ]

    def __str__(self) -> str:
        if self.usuario_id:
            return f"{self.usuario.username} – {self.timestamp}"
        if self.turista_id:
            return f"{self.turista.alias} – {self.timestamp}"
        return f"Ubicación sin remitente – {self.timestamp}"


class MensajeChat(models.Model):
    """
    Mensaje en el canal de chat de una sesión.
    `remitente` (User) se usa solo para el guía autenticado.
    `turista` (Turista) se usa para participantes anónimos.
    """
    sesion_tour = models.ForeignKey(
        SesionTour, on_delete=models.CASCADE, related_name="mensajes"
    )
    remitente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    turista = models.ForeignKey(
        Turista,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mensajes_enviados",
    )
    nombre_remitente = models.CharField(max_length=255, default="Anónimo")
    texto = models.TextField()
    momento = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tours_mensaje_chat"
        ordering = ["momento"]
        verbose_name = "Mensaje de Chat"
        verbose_name_plural = "Mensajes de Chat"

    def __str__(self) -> str:
        hora = self.momento.strftime("%H:%M") if self.momento else "S/F"
        return f"[{hora}] {self.nombre_remitente}: {self.texto[:30]}"


# ---------------------------------------------------------------------------
# Aliases de compatibilidad — eliminar cuando todo el código use PascalCase
# ---------------------------------------------------------------------------
TURISTA = Turista
SESION_TOUR = SesionTour
TURISTASESION = TuristaSesion
UBICACION_VIVO = UbicacionVivo
MENSAJE_CHAT = MensajeChat