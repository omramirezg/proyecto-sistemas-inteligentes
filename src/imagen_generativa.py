"""
Generacion de fichas visuales con Gemini Image (Nano Banana) via Vertex AI.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Optional

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class NanoBananaProvider:
    """Genera una ficha visual ejecutiva a partir de contexto textual e imagen."""

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()
        self._cliente = None

    def _obtener_cliente(self):
        if self._cliente is not None:
            return self._cliente

        from google import genai

        os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'true'
        os.environ['GOOGLE_CLOUD_PROJECT'] = self.config.gcp_project
        os.environ['GOOGLE_CLOUD_LOCATION'] = self.config.gemini_location

        self._cliente = genai.Client()
        logger.info(
            "NanoBananaProvider inicializado con modelo %s en %s",
            self.config.gemini_image_model,
            self.config.gemini_location,
        )
        return self._cliente

    def generar_ficha_visual(
        self,
        prompt_texto: str,
        imagen_referencia_bytes: bytes,
    ) -> tuple[Optional[bytes], str]:
        """
        Genera una ficha visual ejecutiva usando una imagen base del proceso.

        Returns:
            Tupla (imagen_png, texto_resumen).
        """
        try:
            from google.genai import types
            from PIL import Image

            cliente = self._obtener_cliente()
            imagen = Image.open(io.BytesIO(imagen_referencia_bytes))

            response = cliente.models.generate_content(
                model=self.config.gemini_image_model,
                contents=[imagen, prompt_texto],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                ),
            )

            imagen_generada: Optional[bytes] = None
            texto_generado = "Ficha visual IA generada correctamente."

            for part in response.candidates[0].content.parts:
                if getattr(part, 'text', None):
                    texto_generado = part.text.strip()
                inline_data = getattr(part, 'inline_data', None)
                if inline_data and getattr(inline_data, 'data', None):
                    imagen_generada = inline_data.data

            if imagen_generada is None:
                logger.warning("Nano Banana no devolvio imagen en la respuesta.")
                return None, texto_generado

            logger.info(
                "Ficha visual generada con Nano Banana: %.1f KB",
                len(imagen_generada) / 1024,
            )
            return imagen_generada, texto_generado

        except Exception as e:
            logger.error("Error generando ficha visual con Nano Banana: %s", e, exc_info=True)
            return None, (
                "No fue posible generar la ficha visual con IA en este momento. "
                "Se mantiene disponible el panel tecnico actual."
            )
