"""
Tests package for the tours app.
This file enables Django test discovery for all test modules in this directory.
"""

from .test_chat_excepciones import ChatExcepcionesTestCase
from .test_chat_unitarios import (
    MensajeChatModelTest,
    ChatServicesTest,
    ChatIntegrationTest,
    ChatEdgeCasesTest,
)

__all__ = [
    'ChatExcepcionesTestCase',
    'MensajeChatModelTest',
    'ChatServicesTest',
    'ChatIntegrationTest',
    'ChatEdgeCasesTest',
]
