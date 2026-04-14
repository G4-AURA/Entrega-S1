"""
creacion/exceptions.py

Definiciones de excepciones de dominio para el módulo de creación de rutas.
Centralizado para evitar importaciones circulares y asegurar consistencia
entre servicios, nodos y utilidades.
"""

class ErrorRutaBase(Exception):
    """Clase base para errores de dominio en creación de rutas."""


class ErrorValidacionRuta(ErrorRutaBase):
    """Errores de validación de payload y datos de ruta."""
    def __init__(self, errores):
        if isinstance(errores, str):
            self.errores = {'general': errores}
        elif isinstance(errores, dict):
            self.errores = errores
        else:
            self.errores = {'general': str(errores)}
        super().__init__(str(self.errores))


class ErrorPermisosRuta(ErrorRutaBase):
    """Errores de permisos para crear/guardar rutas."""


class ErrorPersistenciaRuta(ErrorRutaBase):
    """Errores al persistir rutas o su historial en base de datos."""


class ErrorIntegracionIA(ErrorRutaBase):
    """Errores al comunicarse o normalizar respuestas del proveedor de IA."""


class ErrorSesionGeneracionRuta(ErrorRutaBase):
    """Errores de estado/checkpoints de sesión de generación IA."""


class ErrorSesionGeneracionExpirada(ErrorSesionGeneracionRuta):
    """La sesión de generación ya no está disponible por expiración."""


class ErrorSesionGeneracionNoEncontrada(ErrorSesionGeneracionRuta):
    """No existe una sesión de generación para el identificador indicado."""
