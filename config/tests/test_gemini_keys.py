from django.test import SimpleTestCase, override_settings

from config.gemini_keys import (
    get_gemini_api_keys,
    is_quota_or_rate_limit_error,
    iter_gemini_api_keys,
)


class GeminiKeysHelpersTests(SimpleTestCase):
    @override_settings(GEMINI_API_KEYS=(), GEMINI_API_KEY='')
    def test_get_gemini_api_keys_vacia_sin_configuracion(self):
        self.assertEqual(get_gemini_api_keys(), [])

    @override_settings(
        GEMINI_API_KEYS=('key-a', ' key-b ', 'key-a', '', 'key-c'),
        GEMINI_API_KEY='legacy',
    )
    def test_get_gemini_api_keys_dedup_y_orden(self):
        self.assertEqual(get_gemini_api_keys(), ['key-a', 'key-b', 'key-c'])

    @override_settings(GEMINI_API_KEYS=(), GEMINI_API_KEY='legacy-key')
    def test_get_gemini_api_keys_fallback_a_legacy(self):
        self.assertEqual(get_gemini_api_keys(), ['legacy-key'])

    @override_settings(GEMINI_API_KEYS=('key-a', 'key-b', 'key-c'), GEMINI_API_KEY='key-a')
    def test_iter_gemini_api_keys_preferred_primero_sin_duplicados(self):
        resultado = list(iter_gemini_api_keys(preferred_key='key-b'))
        self.assertEqual(resultado, ['key-b', 'key-a', 'key-c'])

    @override_settings(GEMINI_API_KEYS=('key-a',), GEMINI_API_KEY='key-a')
    def test_iter_gemini_api_keys_ignora_preferred_vacio(self):
        resultado = list(iter_gemini_api_keys(preferred_key='  '))
        self.assertEqual(resultado, ['key-a'])

    def test_is_quota_or_rate_limit_error_true_para_429(self):
        self.assertTrue(is_quota_or_rate_limit_error(status_code=429))

    def test_is_quota_or_rate_limit_error_true_para_403_con_hint(self):
        self.assertTrue(
            is_quota_or_rate_limit_error(
                status_code=403,
                detail='RESOURCE_EXHAUSTED: quota exceeded',
            )
        )

    def test_is_quota_or_rate_limit_error_false_para_403_sin_hint(self):
        self.assertFalse(
            is_quota_or_rate_limit_error(
                status_code=403,
                detail='forbidden by policy',
            )
        )

    def test_is_quota_or_rate_limit_error_true_por_excepcion(self):
        self.assertTrue(
            is_quota_or_rate_limit_error(
                exception=RuntimeError('Too many requests from upstream provider'),
            )
        )

    def test_is_quota_or_rate_limit_error_false_sin_pistas(self):
        self.assertFalse(
            is_quota_or_rate_limit_error(
                status_code=500,
                detail='internal server error',
                exception=RuntimeError('connection reset by peer'),
            )
        )
