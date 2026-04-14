# Contrato de Errores API Uniforme

## Resumen

Todas las respuestas de error JSON en los endpoints de la aplicación (status >= 400) son normalizadas automáticamente por el middleware [`config.middleware.ApiErrorMiddleware`](config/middleware.py).

## Características

### 1. **Trazabilidad con `request_id`**
Cada petición recibe un identificador único que permite rastrear errores en logs:

- **Header**: `X-Request-ID` (presente en response)
- **Body JSON**: campo `request_id` (idéntico al header)

El `request_id` puede venir del cliente (header `X-Request-ID`) o se genera automáticamente (UUID v4 en hex).

### 2. **Estructura de Error Uniforme**

```json
{
  "status": "ERROR",
  "error": "Descripción del error",
  "code": "CODIGO_ERROR",
  "request_id": "abc123def456",
  "...otros campos originales..."
}
```

**Campos garantizados:**
- `status`: siempre `"ERROR"` para respuestas de error
- `error`: mensaje legible en español (del endpoint o fallback según HTTP status)
- `code`: código único del error (original o `HTTP_<status_code>`)
- `request_id`: para trazabilidad

**Campos preservados:**
- Cualquier otro campo que devolviera el endpoint original se mantiene (ej: `mensaje`, `metadata`, etc.)

### 3. **Cobertura Global**

El middleware aplica a **TODAS** las apps:
- `billing` (checkout, webhooks, suscripciones)
- `tours` (sesiones, chat, ubicación)
- `creacion` (generación IA de rutas)
- `rutas` (gestión de rutas)
- `allowList` (gestión de POIs)

## Ejemplos

### Ejemplo 1: Error de autenticación (status 401)

**Request:**
```bash
POST /billing/create-checkout-session/ HTTP/1.1
Content-Type: application/json
```

**Response:**
```json
{
  "status": "ERROR",
  "error": "Debes iniciar sesión para acceder al checkout.",
  "code": "HTTP_401",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Headers:**
```
HTTP/1.1 401 Unauthorized
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json
```

### Ejemplo 2: Con request_id del cliente

**Request:**
```bash
POST /billing/create-checkout-session/ HTTP/1.1
Content-Type: application/json
X-Request-ID: client-req-12345
```

**Response:**
```json
{
  "status": "ERROR",
  "error": "Debes iniciar sesión para acceder al checkout.",
  "code": "HTTP_401",
  "request_id": "client-req-12345"
}
```

**Headers:**
```
X-Request-ID: client-req-12345
```

### Ejemplo 3: Error custom preservado

**Endpoint original devuelve:**
```json
{
  "status": "ERROR",
  "mensaje": "Falló la validación",
  "code": "VALIDATION_ERROR",
  "field_errors": {"email": "Email inválido"}
}
```

**Middleware normaliza a:**
```json
{
  "status": "ERROR",
  "error": "Falló la validación",
  "code": "VALIDATION_ERROR",
  "request_id": "xyz789",
  "mensaje": "Falló la validación",
  "field_errors": {"email": "Email inválido"}
}
```

## Validación de Errores

```python
# En tests: Todos los errors incluyen request_id
response = client.post('/api/endpoint/', ...)
assert response.status_code >= 400
assert 'X-Request-ID' in response
body = response.json()
assert body['request_id'] == response['X-Request-ID']
assert 'error' in body
```

## Casos Especiales

### Excepción no controlada (500)
Si una excepción no capturada ocurre en un endpoint JSON, se convierte a:

```json
{
  "status": "ERROR",
  "error": "Ha ocurrido un error interno. Inténtalo de nuevo en unos minutos.",
  "code": "INTERNAL_SERVER_ERROR",
  "request_id": "uuid-aqui"
}
```

### Sin autenticación para vistas HTML
Las vistas HTML (no JSON) redirigen a login sin cambios (el middleware no las toca).

## Referencia de Implementación

**Archivo:** [`config/middleware.py`](config/middleware.py)

**Constantes:**
```python
REQUEST_ID_HEADER = 'X-Request-ID'
REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9._-]+$')  # Caracteres válidos
MAX_REQUEST_ID_LENGTH = 128  # Cliente puede enviar hasta 128 caracteres
```

**Tests:** [`config/tests/test_middleware.py`](config/tests/test_middleware.py)

## Migración Gradual

No se requiere cambio en endpoints existentes. El middleware:
- ✅ Normaliza automáticamente
- ✅ Preserva campos originales
- ✅ Retrocompatible con respuestas existentes
