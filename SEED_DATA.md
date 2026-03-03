# Datos de Prueba - Documentación Completa

## Cómo Ejecutar

### Opción 1: Crear datos (sin limpiar existentes)
```bash
python manage.py seed_demo_data
```

### Opción 2: Limpiar y crear datos (recomendado para desarrollo)
```bash
python manage.py seed_demo_data --clean
```

---

## Datos que se Crean

### 📊 Resumen
- **3 Guías** con diferentes suscripciones
- **4 Rutas turísticas** con temas variados
- **13 Paradas geolocaliza das** en la región de Sevilla
- **5 Turistas** para pruebas
- **3 Sesiones de tour** en diferentes estados

---

## 👥 Guías Creadas

| # | Usuario | Nombre | Email | Suscripción | Contraseña |
|---|---------|--------|-------|-------------|-----------|
| 1 | `guia_ana` | Ana García | ana@example.com | **Premium** | demo123 |
| 2 | `guia_carlos` | Carlos López | carlos@example.com | **Freemium** | demo123 |
| 3 | `guia_maria` | María Rodríguez | maria@example.com | **Premium** | demo123 |

**Notas:**
- Todas las contraseñas son `demo123`
- Las guías Premium pueden crear más rutas
- Carlos (Freemium) tiene limitaciones en su suscripción

---

## 🗺️ Rutas Turísticas

### Ruta 1: Tour Histórico por el Centro de Sevilla
- **Guía:** Ana García (Premium)
- **Duración:** 3.5 horas
- **Capacidad:** 15 personas
- **Nivel:** Bajo
- **Temas:** Historia, Arquitectura y Diseño
- **Paradas:** 5 ubicaciones históricas
- **Generada por IA:** No

#### Paradas:
1. **Plaza Nueva** (37.3891, -5.9923) - Inicio
2. **Catedral de Sevilla** (37.3860, -5.9926) - Monumento principal
3. **Barrio Santa Cruz** (37.3870, -5.9880) - Zona histórica
4. **Real Alcázar** (37.3838, -5.9930) - Palacio histórico
5. **Torre del Oro** (37.3824, -5.9963) - Última parada

---

### Ruta 2: Ruta Gastronómica por Triana
- **Guía:** Carlos López (Freemium)
- **Duración:** 2.5 horas
- **Capacidad:** 10 personas
- **Nivel:** Bajo
- **Temas:** Gastronomía, Local
- **Paradas:** 4 ubicaciones gastronómicas
- **Generada por IA:** No

#### Paradas:
1. **Plaza de Castilla** (37.3752, -5.9982) - Punto de encuentro
2. **Mercado de Triana** (37.3745, -6.0010) - Mercado tradicional
3. **Taberna Tradicional** (37.3789, -6.0020) - Comida local
4. **Cerámica de Triana** (37.3708, -6.0020) - Artesanía y tienda

---

### Ruta 3: Misterios y Leyendas de Sevilla
- **Guía:** María Rodríguez (Premium)
- **Duración:** 2.0 horas
- **Capacidad:** 12 personas
- **Nivel:** Medio
- **Temas:** Misterio y Leyendas
- **Paradas:** 3 ubicaciones misteriosas
- **Generada por IA:** No

#### Paradas:
1. **Barrio de Santa Cruz** (37.3870, -5.9880) - Barrio antiguo
2. **Callejones Oscuros** (37.3845, -5.9900) - Zona legendaria
3. **Iglesia de la Magdalena** (37.3882, -5.9853) - Monumento histórico

---

### Ruta 4: Naturaleza y Parques de la Región
- **Guía:** Ana García (Premium)
- **Duración:** 4.0 horas
- **Capacidad:** 20 personas
- **Nivel:** Medio
- **Temas:** Naturaleza
- **Paradas:** 3 ubicaciones naturales
- **Generada por IA:** No

#### Paradas:
1. **Parque Natural Doñana** (37.1761, -6.4400) - Área protegida
2. **Centro de Visitantes** (37.1950, -6.4500) - Centro informativo
3. **Laguna de Santa Olalla** (37.1500, -6.4250) - Ecosistema

---

## 🚶 Turistas Creados

| # | Alias | Estado | Usuario Vinculado |
|---|-------|--------|------------------|
| 1 | `turista_juan` | Activo | Sin cuenta |
| 2 | `turista_elena` | Activo | Sin cuenta |
| 3 | `turista_miguel` | Activo | Sin cuenta |
| 4 | `turista_sofia` | Activo | Sin cuenta |
| 5 | `turista_pedro` | Activo | Sin cuenta |

**Notas:**
- Los turistas se crean sin User vinculado (pueden unirse anónimamente)
- Pueden usar alias para identificarse en las sesiones
- Se pueden vincular a múltiples sesiones

---

## 🎫 Sesiones de Tour

### Sesión 1: TOUR001
- **Ruta:** Tour Histórico por el Centro de Sevilla
- **Estado:** EN CURSO ⏳
- **Código de acceso:** `TOUR001`
- **Parada Actual:** Catedral de Sevilla (parada 2)
- **Turistas Unidos:** 3
  - turista_juan
  - turista_elena
  - turista_miguel
- **Token:** UUID único para identificación
- **Fecha de Inicio:** Hoy (fecha actual del sistema)

**Uso:** Para pruebas de seguimiento en tiempo real

---

### Sesión 2: TOUR002
- **Ruta:** Ruta Gastronómica por Triana
- **Estado:** PENDIENTE ⏸️
- **Código de acceso:** `TOUR002`
- **Parada Actual:** Mercado de Triana (parada 1)
- **Turistas Unidos:** 2
  - turista_sofia
  - turista_pedro
- **Token:** UUID único para identificación
- **Fecha de Inicio:** Hoy

**Uso:** Para pruebas de unión a sesiones pendientes

---

### Sesión 3: TOUR003
- **Ruta:** Misterios y Leyendas de Sevilla
- **Estado:** PENDIENTE ⏸️
- **Código de acceso:** `TOUR003`
- **Parada Actual:** Sin parada actual
- **Turistas Unidos:** 2
  - turista_juan
  - turista_sofia
- **Token:** UUID único para identificación
- **Fecha de Inicio:** Hoy

**Uso:** Para pruebas de sesiones sin parada inicial

---

## 🔑 Qué Puedes Probar

### Como Guía:
```bash
# Iniciar sesión en /admin
Usuario: guia_ana / Contraseña: demo123

# Desde aquí puedes:
- Ver tus rutas
- Editar rutas y paradas
- Ver sesiones activas
- Gestionar turistas
```

### Como Turista:
```
# Usar códigos de acceso en la aplicación:
TOUR001 (en curso, con parada asignada)
TOUR002 (pendiente)
TOUR003 (pendiente, sin parada)
```

### En Django Shell:
```bash
python manage.py shell

# Ver todas las rutas
from rutas.models import Ruta
Ruta.objects.all()

# Ver sesiones activas
from tours.models import SESION_TOUR
SESION_TOUR.objects.filter(estado='en_curso')

# Ver turistas en una sesión
sesion = SESION_TOUR.objects.get(codigo_acceso='TOUR001')
sesion.turistas.all()

# Ver paradas de una ruta
ruta = Ruta.objects.first()
ruta.parada_set.all().order_by('orden')
```

---

## 📍 Coordenadas Totales

**13 Paradas distribuidas en Sevilla y alrededores:**

```
Centro Histórico (Paradas 1-5):
- Plaza Nueva: 37.3891, -5.9923
- Catedral: 37.3860, -5.9926
- Santa Cruz: 37.3870, -5.9880
- Alcázar: 37.3838, -5.9930
- Torre del Oro: 37.3824, -5.9963

Triana (Paradas 6-9):
- Plaza Castilla: 37.3752, -5.9982
- Mercado Triana: 37.3745, -6.0010
- Taberna: 37.3789, -6.0020
- Cerámica: 37.3708, -6.0020

Misterios (Paradas 10-12):
- Barrio Santa Cruz: 37.3870, -5.9880
- Callejones: 37.3845, -5.9900
- Iglesia Magdalena: 37.3882, -5.9853

Naturaleza (Paradas 13-15):
- Parque Doñana: 37.1761, -6.4400
- Centro Visitantes: 37.1950, -6.4500
- Laguna Santa Olalla: 37.1500, -6.4250
```


---

## Operaciones Útiles en Django Shell

### Ver toda la información de una ruta
```python
from rutas.models import Ruta
ruta = Ruta.objects.get(titulo='Tour Histórico por el Centro de Sevilla')
print(f"Ruta: {ruta.titulo}")
print(f"Guía: {ruta.guia.user.user.first_name}")
print(f"Duración: {ruta.duracion_horas}h")
print("Paradas:")
for parada in ruta.parada_set.all().order_by('orden'):
    print(f"  {parada.orden}. {parada.nombre} ({parada.coordenadas.y}, {parada.coordenadas.x})")
```

### Ver sesiones y sus turistas
```python
from tours.models import SESION_TOUR
sesion = SESION_TOUR.objects.get(codigo_acceso='TOUR001')
print(f"Sesión: {sesion.codigo_acceso}")
print(f"Estado: {sesion.estado}")
print(f"Ruta: {sesion.ruta.titulo}")
print(f"Parada actual: {sesion.parada_actual}")
print("Turistas:")
for turista in sesion.turistas.all():
    print(f"  - {turista.alias}")
```

### Cambiar estado de una sesión
```python
sesion = SESION_TOUR.objects.get(codigo_acceso='TOUR002')
sesion.estado = 'en_curso'
sesion.save()
print(f"Sesión {sesion.codigo_acceso} ahora está en: {sesion.estado}")
```

### Cambiar parada actual
```python
from rutas.models import Parada
sesion = SESION_TOUR.objects.get(codigo_acceso='TOUR001')
nueva_parada = Parada.objects.get(ruta=sesion.ruta, orden=3)
sesion.parada_actual = nueva_parada
sesion.save()
print(f"Parada actual: {sesion.parada_actual.nombre}")
```

### Agregar turista a sesión
```python
from tours.models import TURISTASESION, TURISTA
turista = TURISTA.objects.get(alias='turista_juan')
sesion = SESION_TOUR.objects.get(codigo_acceso='TOUR002')
TURISTASESION.objects.get_or_create(turista=turista, sesion_tour=sesion)
print(f"{turista.alias} agregado a {sesion.codigo_acceso}")
```

---

## Limpiar Datos Específicos

### Eliminar solo una sesión
```bash
python manage.py shell
```
```python
from tours.models import SESION_TOUR
SESION_TOUR.objects.filter(codigo_acceso='TOUR001').delete()
```

### Eliminar turistas de una sesión
```python
from tours.models import SESION_TOUR, TURISTASESION
sesion = SESION_TOUR.objects.get(codigo_acceso='TOUR001')
TURISTASESION.objects.filter(sesion_tour=sesion).delete()
```

### Eliminar solo las paradas de una ruta
```python
from rutas.models import Parada, Ruta
ruta = Ruta.objects.get(titulo='Tour Histórico por el Centro de Sevilla')
Parada.objects.filter(ruta=ruta).delete()
```

---

## Personalizar Datos

Para cambiar los datos de prueba permanentemente, edita:
**[tours/management/commands/seed_demo_data.py](tours/management/commands/seed_demo_data.py)**

### Agregar una nueva guía:
```python
# En el diccionario guides_data, agrega:
{
    'username': 'guia_nuevo',
    'email': 'nuevo@example.com',
    'first_name': 'Nombre',
    'last_name': 'Apellido',
    'suscripcion': 'Premium'
}
```

### Agregar una nueva ruta:
```python
# En el diccionario routes_data, agrega:
{
    'titulo': 'Título de la Ruta',
    'descripcion': 'Descripción detallada',
    'duracion_horas': 2.5,
    'num_personas': 15,
    'nivel_exigencia': 'Baja',  # 'Baja', 'Media' o 'Alta'
    'mood': ['Historia', 'Arquitectura y Diseño'],
    'es_generada_ia': False,
    'guia_idx': 0  # Índice del guía en la lista
}
```

### Agregar paradas a una ruta:
```python
# En el diccionario stops_by_route, agrega:
4: [  # Índice de la ruta (nueva ruta)
    {"nombre": "Nombre Parada", "lat": 37.3891, "lng": -5.9923, "orden": 1},
    # ... más paradas
]
```

---

## Troubleshooting

### Error: "No app registrada"
Asegúrate de que `tours` está en `INSTALLED_APPS` en `config/settings.py`

### Error: "código_acceso duplicado"
Usa `--clean` para limpiar y recrear desde cero:
```bash
python manage.py seed_demo_data --clean
```

### Error: "No hay rutas en la base de datos"
Ejecuta el comando completo:
```bash
python manage.py seed_demo_data --clean
```

### Error: "operación geoespacial"
Verifica que PostGIS está instalado y la base de datos PostGIS está configurada correctamente.

---

## Información Técnica

### Archivo del comando
- **Path:** `tours/management/commands/seed_demo_data.py`
- **Métodos principales:**
  - `handle()` - Orquesta la creación de datos
  - `_create_guides()` - Crea guías
  - `_create_routes()` - Crea rutas
  - `_create_stops()` - Crea paradas
  - `_create_tourists()` - Crea turistas
  - `_create_sessions()` - Crea sesiones
  - `_clean_data()` - Limpia datos existentes

### Modelos involucrados
- `rutas.models.Guia` - Guías turísticos
- `rutas.models.Ruta` - Rutas turísticas
- `rutas.models.Parada` - Paradas de las rutas
- `tours.models.TURISTA` - Turistas
- `tours.models.SESION_TOUR` - Sesiones de tour
- `tours.models.TURISTASESION` - Relación turista-sesión
