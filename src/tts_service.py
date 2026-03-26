"""
Servicio de Text-to-Speech (TTS).
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class TTSProvider(ABC):
    """Interfaz abstracta para proveedores de TTS."""

    @abstractmethod
    def sintetizar(self, texto: str) -> bytes:
        """Convierte texto a audio reproducible por Telegram."""
        ...


class GoogleTTSProvider(TTSProvider):
    """Implementacion de TTS usando Google Cloud."""

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()
        self._client = None
        self._inicializado = False
        logger.info(
            "GoogleTTSProvider configurado: idioma=%s, voz=%s",
            self.config.tts_language,
            self.config.tts_voice,
        )

    def _inicializar_cliente(self) -> None:
        if self._inicializado:
            return

        try:
            from google.cloud import texttospeech

            self._client = texttospeech.TextToSpeechClient()
            self._inicializado = True
            logger.info("Cliente de Google Cloud TTS inicializado.")
        except Exception as e:
            logger.error("Error inicializando Google Cloud TTS: %s", e)
            raise

    def sintetizar(self, texto: str) -> bytes:
        """
        Convierte texto a MP3 para enviarlo como audio.
        """
        self._inicializar_cliente()

        try:
            from google.cloud import texttospeech

            synthesis_input = texttospeech.SynthesisInput(text=texto)
            voice = texttospeech.VoiceSelectionParams(
                language_code=self.config.tts_language,
                name=self.config.tts_voice,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,
                pitch=0.0,
                volume_gain_db=2.0,
            )

            response = self._client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )

            audio_bytes = response.audio_content
            logger.info(
                "Audio MP3 generado por Google TTS: %d bytes (%.1f KB) | Texto: %d caracteres",
                len(audio_bytes),
                len(audio_bytes) / 1024,
                len(texto),
            )
            return audio_bytes
        except Exception as e:
            logger.error("Error en Google Cloud TTS: %s", e)
            raise


