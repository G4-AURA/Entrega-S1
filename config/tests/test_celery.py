from unittest.mock import patch

from django.test import SimpleTestCase


class CeleryAppConfigTest(SimpleTestCase):

    def test_app_celery_existe(self):
        from config.celery import app
        self.assertIsNotNone(app)

    def test_nombre_app_celery_es_config(self):
        from config.celery import app
        self.assertEqual(app.main, 'config')

    def test_debug_task_esta_registrada_en_la_app(self):
        from config.celery import app
        self.assertIn('config.celery.debug_task', app.tasks)

    def test_debug_task_es_invocable(self):
        from config.celery import debug_task
        self.assertTrue(callable(debug_task))

    def test_debug_task_imprime_el_request(self):
        from config.celery import debug_task

        with patch('builtins.print') as mock_print:
            debug_task.run()
            mock_print.assert_called_once()
            printed_output = str(mock_print.call_args)
            self.assertIn('Request:', printed_output)
