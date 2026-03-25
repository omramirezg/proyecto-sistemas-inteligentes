"""
Proveedor Local de IA — Gemma 3 2B vía Ollama
===============================================
Fallback inteligente cuando Google Cloud / Vertex AI no está disponible.

Arquitectura de resiliencia (Circuit Breaker):

    CERRADO  → Gemini OK, flujo normal
        ↓  3 fallos consecutivos
    ABIERTO  → Gemini caído, redirigir a Gemma local
        ↓  5 minutos después (TTL de enfriamiento)
    [auto-reset] → volver a intentar Gemini

Ollama expone una REST API en localhost:11434. Con Gemma 3 2B:
    - ~1.5 GB RAM (CPU)
    - ~800ms de latencia en CPU moderno
    - Contexto 8K tokens (comprimido vs. 1M de Gemini)
    - Sin herramientas / tool use — single-shot

Para activar:
    1. Instalar Ollama: https://ollama.ai
    2. Descargar modelo:  ollama pull gemma3:2b
    3. Iniciar servidor:  ollama serve
    4. En .env:           GEMMA_FALLBACK_HABILITADO=1

Uso:
    provider = GemmaLocalProvider(config)
    if provider.disponible():
        texto = provider.diagnosticar_fallback(prompt, feedback_loop, maquina, variable)
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Segundos de espera máxima a Ollama antes de abandonar
_OLLAMA_TIMEOUT_SEG: int = 90

# System prompt compacto — cabe en el contexto de 8K de Gemma
# (vs. el bloque fijo completo de ~3K tokens del proveedor Gemini)
_SYSTEM_PROMPT_COMPACTO: str = """Eres un ingeniero de procesos experto en plantas de peletización industrial.
Analiza la alerta y genera una prescripción técnica concisa con este formato:

1. DIAGNÓSTICO: qué ocurre y severidad (BAJA / MEDIA / ALTA / CRÍTICA)
2. CAUSA PROBABLE: razón técnica más probable
3. ACCIÓN INMEDIATA: pasos específicos para el operario en campo
4. PRIORIDAD: INMEDIATO / 15 MIN / 30 MIN

Reglas críticas:
- Responde en español.
- Máximo 150 palabras.
- Sin tecnicismos innecesarios — el operario puede no ser ingeniero.
- NUNCA recomendar manipulación eléctrica directa.
- SIEMPRE priorizar seguridad personal sobre productividad.
- No menciones que eres un modelo de IA local."""


class GemmaLocalProvider:
    """
    Proveedor de prescripciones con Gemma 3 2B vía Ollama (local, CPU).

    No soporta tool use ni imágenes (solo texto). Produce prescripciones
    single-shot usando el contexto de alerta + few-shot del feedback loop.

    Diseñado para usarse exclusivamente como fallback: nunca reemplaza a
    Gemini en condiciones normales, solo actúa cuando el circuit breaker
    del GeminiProvider detecta fallos consecutivos.
    """

    def __init__(self, config) -> None:
        self.config = config
        self._base_url: str = config.gemma_ollama_url.rstrip('/')
        self._modelo:   str = config.gemma_modelo_local

    # -----------------------------------------------------------------------
    # Verificación de disponibilidad
    # -----------------------------------------------------------------------

    def disponible(self) -> bool:
        """
        Comprueba que Ollama esté corriendo y el modelo esté descargado.

        Hace GET /api/tags con timeout de 3 segundos — < 50ms en localhost.
        Si el modelo base (sin tag de versión) está en la lista, retorna True.
        """
        try:
            resp = requests.get(
                f"{self._base_url}/api/tags",
                timeout=3,
            )
            if resp.status_code != 200:
                logger.debug("[GEMMA] Ollama respondió %d en /api/tags.", resp.status_code)
                return False

            modelos_instalados = [m['name'] for m in resp.json().get('models', [])]
            # Comparar base del modelo ignorando el tag (ej: "gemma3" en "gemma3:2b")
            base_modelo = self._modelo.split(':')[0]
            encontrado = any(base_modelo in m for m in modelos_instalados)

            if not encontrado:
                logger.warning(
                    "[GEMMA] Modelo '%s' no encontrado en Ollama. "
                    "Modelos disponibles: %s. "
                    "Ejecuta: ollama pull %s",
                    self._modelo, modelos_instalados, self._modelo,
                )
            return encontrado

        except requests.ConnectionError:
            logger.debug("[GEMMA] Ollama no está corriendo en %s.", self._base_url)
            return False
        except Exception as e:
            logger.debug("[GEMMA] Error verificando Ollama: %s", e)
            return False

    # -----------------------------------------------------------------------
    # Generación de prescripción (single-shot, sin herramientas)
    # -----------------------------------------------------------------------

    def diagnosticar_fallback(
        self,
        prompt_texto: str,
        feedback_loop=None,
        id_maquina: Optional[str] = None,
        variable:   Optional[str] = None,
    ) -> str:
        """
        Genera una prescripción con Gemma local.

        El prompt se comprime para caber en el contexto de 8K tokens:
            - System prompt compacto de ingeniería industrial (~200 tokens)
            - Few-shot del feedback loop para esta máquina + variable (~300 tokens)
            - Contexto completo de la alerta actual (~500 tokens)
            - Total estimado: ~1000 tokens — amplio margen en 8K

        No usa herramientas ni imágenes. La calidad es menor que Gemini
        pero significativamente mejor que el texto determinista de fallback.

        Args:
            prompt_texto:  Contexto de la alerta (idéntico al enviado a Gemini).
            feedback_loop: FeedbackLoop para few-shot dinámico. Opcional.
            id_maquina:    Para filtrar few-shot por máquina.
            variable:      Para filtrar few-shot por variable en alerta.

        Returns:
            Prescripción en texto plano, o '' si Ollama falla.
        """
        # Construir mensaje de usuario con few-shot opcional
        partes: list[str] = []

        if feedback_loop is not None and id_maquina and variable:
            try:
                fewshot = feedback_loop.construir_bloque_fewshot(id_maquina, variable)
                if fewshot:
                    partes.append(fewshot)
                    logger.debug(
                        "[GEMMA] Few-shot inyectado para máquina=%s variable=%s",
                        id_maquina, variable,
                    )
            except Exception as ex:
                logger.debug("[GEMMA] Error obteniendo few-shot: %s", ex)

        partes.append(f"## ALERTA ACTUAL\n{prompt_texto}")
        mensaje_usuario = "\n\n".join(partes)

        payload = {
            "model":  self._modelo,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT_COMPACTO},
                {"role": "user",   "content": mensaje_usuario},
            ],
            "stream": False,
            "options": {
                "temperature":  0.2,    # Más determinista que Gemini — menos riesgo en fallback
                "num_predict":  350,    # ~150 palabras máximo
                "top_p":        0.85,
            },
        }

        try:
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=_OLLAMA_TIMEOUT_SEG,
            )
            resp.raise_for_status()

            texto = resp.json().get("message", {}).get("content", "").strip()
            if texto:
                logger.info(
                    "[GEMMA] Prescripción local generada (%d chars) | Modelo: %s | "
                    "Máquina: %s | Variable: %s",
                    len(texto), self._modelo, id_maquina or "?", variable or "?",
                )
                return texto

            logger.warning("[GEMMA] Respuesta vacía de Ollama.")
            return ""

        except requests.Timeout:
            logger.error(
                "[GEMMA] Timeout (%ds) esperando respuesta de Ollama.", _OLLAMA_TIMEOUT_SEG
            )
            return ""
        except Exception as e:
            logger.error("[GEMMA] Error en llamada a Ollama /api/chat: %s", e)
            return ""
