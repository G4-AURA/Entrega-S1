"""Middleware común para APIs JSON con trazabilidad por request_id."""

import json
import re
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse


REQUEST_ID_HEADER = 'X-Request-ID'
REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9._-]+$')
MAX_REQUEST_ID_LENGTH = 128


class ApiErrorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = self._resolve_request_id(request)
        request.request_id = request_id

        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request_id

        if self._is_json_response(response) and response.status_code >= 400:
            self._normalize_json_error_response(response, request_id)

        return response

    def process_exception(self, request, exception):
        if not self._should_return_json_error(request):
            return None

        request_id = getattr(request, 'request_id', None) or self._resolve_request_id(request)
        response = JsonResponse(
            {
                'status': 'ERROR',
                'error': 'Ha ocurrido un error interno. Inténtalo de nuevo en unos minutos.',
                'code': 'INTERNAL_SERVER_ERROR',
                'request_id': request_id,
            },
            status=500,
        )
        response[REQUEST_ID_HEADER] = request_id
        return response

    def _resolve_request_id(self, request):
        candidate = str(request.META.get('HTTP_X_REQUEST_ID', '') or '').strip()
        if candidate and len(candidate) <= MAX_REQUEST_ID_LENGTH and REQUEST_ID_PATTERN.match(candidate):
            return candidate
        return uuid.uuid4().hex

    def _should_return_json_error(self, request):
        accept_header = str(request.META.get('HTTP_ACCEPT', '') or '').lower()
        content_type = str(request.META.get('CONTENT_TYPE', '') or '').lower()
        return 'application/json' in accept_header or 'application/json' in content_type

    def _is_json_response(self, response):
        content_type = response.get('Content-Type', '') or ''
        return content_type.startswith('application/json')

    def _normalize_json_error_response(self, response, request_id):
        try:
            payload = json.loads(response.content.decode(response.charset or 'utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None

        if not isinstance(payload, dict):
            payload = {'error': self._stringify_payload(payload)}

        normalized = dict(payload)
        message = self._extract_message(payload, response.status_code)
        normalized['error'] = message
        normalized['code'] = normalized.get('code') or f'HTTP_{response.status_code}'
        normalized['request_id'] = request_id
        normalized['status'] = normalized.get('status') or 'ERROR'

        response.content = json.dumps(
            normalized,
            ensure_ascii=False,
            cls=DjangoJSONEncoder,
        ).encode(response.charset or 'utf-8')
        response[REQUEST_ID_HEADER] = request_id

    def _extract_message(self, payload, status_code):
        if isinstance(payload, dict):
            for key in ('error', 'mensaje', 'message', 'detail'):
                value = payload.get(key)
                if value not in (None, ''):
                    return str(value)
        return self._default_message_for_status(status_code)

    def _default_message_for_status(self, status_code):
        return {
            400: 'La petición no es válida.',
            401: 'No tienes permisos para realizar esta acción.',
            403: 'No tienes permisos para realizar esta acción.',
            404: 'No se encontró el recurso solicitado.',
            409: 'La operación no se puede completar en el estado actual.',
            500: 'Ha ocurrido un error interno. Inténtalo de nuevo en unos minutos.',
            502: 'El servicio externo no está disponible temporalmente.',
            503: 'El servicio no está disponible temporalmente.',
        }.get(status_code, 'Ha ocurrido un error.')

    def _stringify_payload(self, payload):
        if payload is None:
            return 'Ha ocurrido un error.'
        return str(payload)