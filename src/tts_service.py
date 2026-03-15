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


class ElevenLabsTTSProvider(TTSProvider):
    """Implementacion de TTS usando ElevenLabs."""

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()
        import os
        self.api_key = os.getenv('ELEVENLABS_API_KEY', '')
        self.voice_id = os.getenv('ELEVENLABS_VOICE_ID', 'pNInz6obpgDQGcFmaJgB')
        logger.info("ElevenLabsTTSProvider configurado.")

    def sintetizar(self, texto: str) -> bytes:
        import requests

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key,
        }
        data = {
            "text": texto,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            audio_bytes = response.content
            logger.info(
                "Audio generado por ElevenLabs: %d bytes (%.1f KB)",
                len(audio_bytes),
                len(audio_bytes) / 1024,
            )
            return audio_bytes
        except Exception as e:
            logger.error("Error en ElevenLabs TTS: %s", e)
            raise
