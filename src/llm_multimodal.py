"""
Capa de IA Multimodal (LLM)
============================
Integración con Gemini 2.0 Flash vía Vertex AI para generar
prescripciones basadas en texto + imagen (MULTIMODAL).

Arquitectura con patrón Strategy: interfaz abstracta LLMProvider
que permite intercambiar proveedores (Gemini, OpenAI, Anthropic)
sin modificar la lógica del sistema.

Cada llamada es STATELESS (sin memoria entre alertas) para
prevenir alucinaciones por arrastre de historial.
"""

import hashlib
import logging
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


@dataclass
class VarianteParams:
    """
    Parámetros de generación que definen una variante del LLM.
    Usado por ShadowTester para sobreescribir la config base
    del GeminiProvider sin modificar la instancia principal.

    Todos los campos son opcionales — si son None, se usa el valor
    por defecto del proveedor. Esto permite cambiar solo lo que interesa
    en el experimento y mantener todo lo demás igual.
    """
    nombre: str = "challenger"
    modelo: Optional[str] = None               # Override del modelo Gemini
    temperatura: Optional[float] = None        # Override de temperatura
    max_tokens: Optional[int] = None           # Override de max_output_tokens
    top_p: Optional[float] = None              # Override de top_p
    system_prompt_override: Optional[str] = None  # Reemplaza todo el system prompt


class LLMProvider(ABC):
    """
    Interfaz abstracta para proveedores de LLM.
    
    Permite intercambiar el proveedor de IA sin modificar
    la lógica de negocio del sistema (Principio de Inyección
    de Dependencias).
    """

    @abstractmethod
    def diagnosticar(
        self,
        prompt_texto: str,
        imagen_bytes: Optional[bytes] = None,
    ) -> str:
        """
        Genera un diagnóstico/prescripción basándose en el contexto.
        
        Args:
            prompt_texto: Contexto técnico completo de la alerta.
            imagen_bytes: Gráfica PNG de la serie temporal (multimodal).
            
        Returns:
            Prescripción en texto plano.
        """
        ...


class GeminiProvider(LLMProvider):
    """
    Implementación de LLMProvider usando Gemini 2.0 Flash
    a través de Vertex AI (Google Cloud).
    
    Soporta entrada multimodal: TEXTO + IMAGEN.
    """

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()
        self._model = None
        self._inicializado = False
        self._cliente_genai = None
        self._cache = None              # CachedContent activo
        self._cache_clave = None        # MD5 del bloque fijo (detecta cambios de config)
        self._cache_creado_en = 0.0     # Epoch de creación — TTL local sin red
        self._bloque_fijo_cache: Optional[str] = None   # Bloque fijo pre-construido
        self._bloque_fijo_hash: Optional[str] = None    # MD5 del bloque fijo
        # Circuit breaker — estado en memoria (no persiste entre reinicios)
        self._fallos_consecutivos_gemini: int   = 0
        self._ts_apertura_circuito:       float = 0.0
        self._gemma = None   # GemmaLocalProvider — lazy init para no importar si no se usa
        logger.info(
            "GeminiProvider configurado: modelo=%s, location=%s",
            self.config.gemini_model, self.config.gemini_location
        )

    def _inicializar_modelo(self) -> None:
        """Inicializa el modelo de Gemini (lazy loading)."""
        if self._inicializado:
            return

        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel

            vertexai.init(
                project=self.config.gcp_project,
                location=self.config.gemini_location,
            )

            self._model = GenerativeModel(self.config.gemini_model)
            self._inicializado = True
            logger.info("Modelo Gemini inicializado correctamente.")

        except Exception as e:
            logger.error("Error inicializando Gemini: %s", e)
            raise

    def _obtener_cliente_genai(self):
        """Cliente alterno para audio directo con Vertex AI."""
        if self._cliente_genai is not None:
            return self._cliente_genai

        from google import genai

        os.environ['GOOGLE_GENAI_USE_VERTEXAI'] = 'true'
        os.environ['GOOGLE_CLOUD_PROJECT'] = self.config.gcp_project
        os.environ['GOOGLE_CLOUD_LOCATION'] = self.config.gemini_location
        self._cliente_genai = genai.Client()
        logger.info(
            "Cliente google-genai inicializado (diagnósticos + audio), modelos=%s/%s",
            self.config.gemini_model,
            self.config.gemini_audio_model,
        )
        return self._cliente_genai

    # 9 min de margen — el caché real dura 10 min en Vertex AI
    _CACHE_TTL_SEG: float = 540.0

    # Circuit Breaker: protege contra cascada de fallos cuando Gemini no está disponible.
    # Tras _UMBRAL_FALLOS_CIRCUITO errores consecutivos, el circuito se "abre" y las
    # llamadas se redirigen a Gemma local. Tras _TTL_CIRCUITO_ABIERTO_SEG segundos
    # el circuito se "resetea" automáticamente para intentar Gemini de nuevo.
    _UMBRAL_FALLOS_CIRCUITO:    int   = 3
    _TTL_CIRCUITO_ABIERTO_SEG: float = 300.0   # 5 minutos de enfriamiento

    def _obtener_o_crear_cache(self, bloque_fijo: str, clave: str):
        """
        Crea o reutiliza el caché del system prompt (bloque fijo).

        La validez se comprueba localmente con un timestamp (sin red):
        si el bloque no cambió y el TTL local no expiró, se devuelve el
        caché directamente — cero llamadas extra a la API.
        Si la creación falla (p.ej. tokens insuficientes), retorna None
        y el sistema continúa sin caché de forma transparente.
        """
        from google.genai import types

        # Validar caché con TTL local — sin roundtrip de red
        if (
            self._cache is not None
            and self._cache_clave == clave
            and (time.time() - self._cache_creado_en) < self._CACHE_TTL_SEG
        ):
            logger.debug("Reutilizando caché de system prompt: %s", self._cache.name)
            return self._cache

        # Caché expirado o inexistente — crear uno nuevo
        if self._cache is not None:
            logger.info("Caché expirado por TTL local, recreando...")

        cliente = self._obtener_cliente_genai()
        # Vertex AI exige mínimo 1024 tokens para cachear.
        # Estimamos ~4 chars/token; si no alcanza, saltamos sin intentar la llamada.
        tokens_estimados = len(bloque_fijo) // 4
        if tokens_estimados < 1024:
            logger.debug(
                "Bloque fijo demasiado corto para caché (~%d tokens, mínimo 1024). "
                "Continuando sin caché.",
                tokens_estimados,
            )
            # Marcar como "intentado" con la clave actual para no reintentar cada alerta
            self._cache = None
            self._cache_clave = clave
            self._cache_creado_en = time.time()
            return None

        try:
            self._cache = cliente.caches.create(
                model=self.config.gemini_model,
                config=types.CreateCachedContentConfig(
                    system_instruction=bloque_fijo,
                    ttl='600s',  # 10 minutos en Vertex AI
                ),
            )
            self._cache_clave = clave
            self._cache_creado_en = time.time()
            logger.info(
                "Caché de system prompt creado: %s (TTL 10min)",
                self._cache.name,
            )
            return self._cache
        except Exception as e:
            logger.warning(
                "No se pudo crear caché (tokens insuficientes o API no disponible): %s. "
                "Continuando sin caché.",
                e,
            )
            self._cache = None
            self._cache_clave = None
            self._cache_creado_en = 0.0
            return None

    def diagnosticar(
        self,
        prompt_texto: str,
        imagen_bytes: Optional[bytes] = None,
    ) -> str:
        """
        Genera diagnóstico multimodal con Gemini.

        El bloque fijo (system prompt + guardarraíles) se cachea en Vertex AI:
        la primera llamada lo procesa completo; las siguientes lo recuperan de
        caché pagando ~10% del costo normal. El contexto de la alerta (variable)
        se envía siempre fresco, garantizando stateless por alerta.

        Incluye retry con backoff exponencial para errores 429.
        """
        try:
            from google.genai import types

            cliente = self._obtener_cliente_genai()

            # --- Bloque FIJO: construido una sola vez por instancia ---
            bloque_fijo, clave = self._obtener_bloque_fijo_cacheado()

            # --- Bloque VARIABLE: cambia en cada alerta ---
            contenido = [self._construir_bloque_variable(prompt_texto)]
            if imagen_bytes:
                contenido.append(
                    types.Part.from_bytes(data=imagen_bytes, mime_type='image/png')
                )
                contenido.append(
                    "ANALIZA la gráfica anterior junto con el contexto técnico. "
                    "Identifica patrones visuales (caídas abruptas, oscilaciones, "
                    "tendencias) que complementen tu diagnóstico."
                )
                logger.info("Enviando prompt MULTIMODAL a Gemini (texto + imagen)")
            else:
                logger.info("Enviando prompt de solo texto a Gemini")

            # Intentar usar caché; si falla, incluir bloque fijo directamente
            cache = self._obtener_o_crear_cache(bloque_fijo, clave)
            gen_config = types.GenerateContentConfig(
                cached_content=cache.name if cache else None,
                temperature=0.3,
                max_output_tokens=800,
                top_p=0.8,
            )
            if cache is None:
                contenido = [bloque_fijo] + contenido

            # Llamar al modelo con RETRY para rate limits (429)
            max_reintentos = 3
            espera_base = 5

            for intento in range(max_reintentos):
                try:
                    response = cliente.models.generate_content(
                        model=self.config.gemini_model,
                        contents=contenido,
                        config=gen_config,
                    )
                    prescripcion = response.text.strip()
                    logger.info(
                        "Prescripción generada por Gemini (%d caracteres) [caché=%s]",
                        len(prescripcion),
                        "activo" if cache else "inactivo",
                    )
                    return prescripcion

                except Exception as api_error:
                    error_str = str(api_error)
                    if '429' in error_str or 'Resource exhausted' in error_str:
                        espera = espera_base * (2 ** intento)
                        logger.warning(
                            "Rate limit Gemini (429). Reintento %d/%d en %d seg...",
                            intento + 1, max_reintentos, espera,
                        )
                        time.sleep(espera)
                    else:
                        raise api_error

            logger.error("Agotados %d reintentos para Gemini.", max_reintentos)
            return self._prescripcion_fallback(prompt_texto)

        except Exception as e:
            logger.error("Error en llamada a Gemini: %s", e)
            return self._prescripcion_fallback(prompt_texto)

    def diagnosticar_con_herramientas(
        self,
        prompt_texto: str,
        herramientas,                           # HerramientasAgente instance
        imagen_bytes: Optional[bytes] = None,
        video_bytes:  Optional[bytes] = None,   # GIF animado de serie temporal (Feature 8)
        max_iteraciones: int = 5,
        feedback_loop=None,                     # FeedbackLoop instance (opcional)
        id_maquina: Optional[str] = None,       # Para few-shot lookup en FeedbackLoop
        variable: Optional[str] = None,         # Para few-shot lookup en FeedbackLoop
        variante_params: Optional[VarianteParams] = None,  # Override para A/B testing
    ) -> str:
        """
        Loop agentico con Tool Use y few-shot dinámico desde feedback real.

        El modelo razona en múltiples rondas, invocando herramientas reales
        (historial, fórmula, operario, umbrales, escalación) hasta tener
        suficiente contexto para generar una prescripción específica y accionable.

        Si se provee un FeedbackLoop con id_maquina y variable, inyecta automáticamente
        ejemplos de prescripciones exitosas y antipatrones del historial real,
        mejorando la calidad de la prescripción con cada alerta evaluada por el operario.

        Flujo por iteración:
            1. Enviar contenido al modelo (bloque variable + few-shot + imagen).
            2. Si el modelo responde con function_call → ejecutar herramienta → añadir resultado.
            3. Si el modelo responde con texto → retornar prescripción final.
            4. Si se agota max_iteraciones → retornar último texto disponible o fallback.
        """
        # Circuit breaker: si Gemini está marcado como inaccesible, ir directo a Gemma
        if self._circuito_abierto():
            logger.warning(
                "[CIRCUITO] Circuito ABIERTO — omitiendo Gemini, usando Gemma local. "
                "(%d fallos consecutivos, enfriamiento %.0fs)",
                self._fallos_consecutivos_gemini,
                self._TTL_CIRCUITO_ABIERTO_SEG,
            )
            return self._prescripcion_con_gemma(
                prompt_texto, feedback_loop, id_maquina, variable
            )

        try:
            from google.genai import types

            cliente = self._obtener_cliente_genai()
            bloque_fijo, clave = self._obtener_bloque_fijo_cacheado()
            cache = self._obtener_o_crear_cache(bloque_fijo, clave)

            # --- Few-shot dinámico desde feedback real ---
            bloque_fewshot = ""
            if feedback_loop is not None and id_maquina and variable:
                bloque_fewshot = feedback_loop.construir_bloque_fewshot(id_maquina, variable)
                if bloque_fewshot:
                    logger.info(
                        "[RLHF] Few-shot inyectado para máquina=%s variable=%s",
                        id_maquina, variable,
                    )

            # Bloque variable + few-shot combinados
            texto_usuario = self._construir_bloque_variable(prompt_texto)
            if bloque_fewshot:
                texto_usuario = bloque_fewshot + "\n\n" + texto_usuario

            # Construir turno inicial del usuario
            partes_usuario = [types.Part(text=texto_usuario)]
            if imagen_bytes:
                partes_usuario.append(
                    types.Part.from_bytes(data=imagen_bytes, mime_type='image/png')
                )
                partes_usuario.append(types.Part(
                    text=(
                        "ANALIZA la gráfica estática anterior junto con el contexto técnico. "
                        "Identifica patrones visuales que complementen tu diagnóstico."
                    )
                ))

            if video_bytes:
                # GIF animado de la serie temporal — Gemini extrae todos los frames.
                # Muestra la evolución de temp_acond, presion_vapor y corriente
                # en las últimas ~30 lecturas (Feature 8: Video temporal).
                partes_usuario.append(
                    types.Part.from_bytes(data=video_bytes, mime_type='image/gif')
                )
                partes_usuario.append(types.Part(
                    text=(
                        "EXAMINA el GIF animado anterior. Muestra la evolución temporal "
                        "de temperatura, presión y corriente en las últimas 30 lecturas. "
                        "Identifica: velocidad de cambio, oscilaciones, tendencias, "
                        "puntos de inflexión — patrones dinámicos que la imagen estática "
                        "no puede revelar."
                    )
                ))

            if imagen_bytes or video_bytes:
                logger.info(
                    "[AGENTE] Loop agentico MULTIMODAL — imagen=%s gif=%s",
                    "sí" if imagen_bytes else "no",
                    "sí" if video_bytes  else "no",
                )
            else:
                logger.info("[AGENTE] Iniciando loop agentico de solo texto")

            # Historial de la conversación agente ↔ modelo
            contenido: list = [types.Content(role="user", parts=partes_usuario)]

            # Si no hay caché, inyectar el bloque fijo como primer mensaje de sistema
            if cache is None:
                contenido.insert(0, types.Content(
                    role="user",
                    parts=[types.Part(text=bloque_fijo)],
                ))

            # Aplicar overrides de variante (A/B testing) si se proveen
            _temperatura  = (variante_params.temperatura  if variante_params and variante_params.temperatura  is not None else 0.3)
            _max_tokens   = (variante_params.max_tokens   if variante_params and variante_params.max_tokens   is not None else 1200)
            _top_p        = (variante_params.top_p        if variante_params and variante_params.top_p        is not None else 0.8)
            _modelo       = (variante_params.modelo       if variante_params and variante_params.modelo       else self.config.gemini_model)

            if variante_params:
                logger.info(
                    "[A/B] Variante '%s': modelo=%s temperatura=%.2f max_tokens=%d",
                    variante_params.nombre, _modelo, _temperatura, _max_tokens,
                )

            # Si la variante tiene system_prompt_override, forzar bloque fijo distinto
            if variante_params and variante_params.system_prompt_override:
                bloque_fijo_variante = variante_params.system_prompt_override
                clave_variante = hashlib.md5(bloque_fijo_variante.encode()).hexdigest()
                cache_variante = self._obtener_o_crear_cache(bloque_fijo_variante, clave_variante)
                if cache_variante is None and contenido[0].role == "user":
                    contenido.insert(0, types.Content(
                        role="user",
                        parts=[types.Part(text=bloque_fijo_variante)],
                    ))
                gen_config_cached = cache_variante.name if cache_variante else None
            else:
                gen_config_cached = cache.name if cache else None

            # Configuración de generación con tools habilitadas
            gen_config = types.GenerateContentConfig(
                cached_content=gen_config_cached,
                temperature=_temperatura,
                max_output_tokens=_max_tokens,
                top_p=_top_p,
                tools=[types.Tool(function_declarations=herramientas.declaraciones_gemini())],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="AUTO"),
                ),
            )

            ultimo_texto: str = ""
            _MAX_REINTENTOS_429 = 3
            _ESPERA_BASE_429    = 8   # segundos base — duplica con cada reintento

            for iteracion in range(1, max_iteraciones + 1):
                logger.info("[AGENTE] Iteración %d/%d", iteracion, max_iteraciones)

                # Retry con backoff exponencial ante rate limit (429)
                response = None
                for _reintento in range(_MAX_REINTENTOS_429):
                    try:
                        response = cliente.models.generate_content(
                            model=_modelo,
                            contents=contenido,
                            config=gen_config,
                        )
                        break   # éxito — salir del loop de reintentos
                    except Exception as _err:
                        _es_429 = '429' in str(_err) or 'RESOURCE_EXHAUSTED' in str(_err)
                        if _es_429 and _reintento < _MAX_REINTENTOS_429 - 1:
                            _espera = _ESPERA_BASE_429 * (2 ** _reintento)
                            logger.warning(
                                "[AGENTE] Rate limit 429 en iteración %d. "
                                "Reintento %d/%d en %ds...",
                                iteracion, _reintento + 1, _MAX_REINTENTOS_429, _espera,
                            )
                            time.sleep(_espera)
                        else:
                            raise  # re-raise hacia el except externo

                candidato = response.candidates[0]
                partes = candidato.content.parts

                # Capturar texto si existe en esta ronda
                textos = [p.text for p in partes if hasattr(p, "text") and p.text]
                if textos:
                    ultimo_texto = " ".join(textos).strip()

                # Separar function calls del resto
                llamadas = [p for p in partes if p.function_call is not None]

                if not llamadas:
                    # Sin llamadas pendientes → respuesta final
                    logger.info(
                        "[AGENTE] Prescripción final en iteración %d (%d chars)",
                        iteracion, len(ultimo_texto),
                    )
                    return ultimo_texto or self._prescripcion_fallback(prompt_texto)

                # Añadir respuesta del modelo al historial
                contenido.append(candidato.content)

                # Ejecutar cada herramienta y construir respuesta de tool
                partes_tool: list = []
                for parte in llamadas:
                    fc = parte.function_call
                    resultado = herramientas.ejecutar(fc.name, dict(fc.args))
                    partes_tool.append(
                        types.Part.from_function_response(
                            name=fc.name,
                            response=resultado,
                        )
                    )

                # Añadir resultados al historial para la siguiente ronda
                contenido.append(types.Content(role="tool", parts=partes_tool))

            # Agotó iteraciones sin respuesta limpia
            logger.warning(
                "[AGENTE] Alcanzó max_iteraciones (%d) sin respuesta final. "
                "Usando último texto disponible.",
                max_iteraciones,
            )
            return ultimo_texto or self._prescripcion_fallback(prompt_texto)

        except Exception as e:
            logger.error("[AGENTE] Error en loop agentico: %s", e, exc_info=True)
            # 429 = cuota agotada (Gemini está UP) — NO abrir el circuit breaker.
            # El circuito solo se abre por fallos reales: red, auth, servidor caído.
            _es_cuota = '429' in str(e) or 'RESOURCE_EXHAUSTED' in str(e)
            if not _es_cuota:
                self._registrar_fallo_gemini()
            return self._prescripcion_con_gemma(
                prompt_texto, feedback_loop, id_maquina, variable
            )

    # -----------------------------------------------------------------------
    # Circuit Breaker — resiliencia ante fallos de Gemini
    # -----------------------------------------------------------------------

    def _circuito_abierto(self) -> bool:
        """
        Retorna True si el circuito está abierto (Gemini marcado como inaccesible).

        El circuito se abre tras _UMBRAL_FALLOS_CIRCUITO fallos consecutivos.
        Se auto-resetea tras _TTL_CIRCUITO_ABIERTO_SEG segundos para permitir
        que el sistema vuelva a intentar Gemini (patrón semi-abierto implícito).
        """
        if self._fallos_consecutivos_gemini < self._UMBRAL_FALLOS_CIRCUITO:
            return False   # Circuito CERRADO — Gemini OK

        # Verificar si el TTL de enfriamiento ya expiró
        tiempo_abierto = time.time() - self._ts_apertura_circuito
        if tiempo_abierto > self._TTL_CIRCUITO_ABIERTO_SEG:
            # Auto-reset: volver a intentar Gemini
            logger.info(
                "[CIRCUITO] TTL de enfriamiento expirado (%.0fs). "
                "Reseteando circuito para re-intentar Gemini.",
                tiempo_abierto,
            )
            self._fallos_consecutivos_gemini = 0
            self._ts_apertura_circuito = 0.0
            return False   # Circuito auto-cerrado

        return True   # Circuito ABIERTO — redirigir a Gemma

    def _registrar_fallo_gemini(self) -> None:
        """
        Registra un fallo de Gemini. Abre el circuito tras _UMBRAL_FALLOS_CIRCUITO
        errores consecutivos y registra el timestamp de apertura.
        """
        self._fallos_consecutivos_gemini += 1
        if (
            self._fallos_consecutivos_gemini >= self._UMBRAL_FALLOS_CIRCUITO
            and self._ts_apertura_circuito == 0.0
        ):
            self._ts_apertura_circuito = time.time()
            logger.warning(
                "[CIRCUITO] ¡CIRCUITO ABIERTO! %d fallos consecutivos de Gemini. "
                "Redirigiendo a Gemma local por %.0f segundos.",
                self._fallos_consecutivos_gemini,
                self._TTL_CIRCUITO_ABIERTO_SEG,
            )

    def _obtener_gemma(self):
        """
        Lazy init del GemmaLocalProvider.
        Solo se instancia si el fallback está habilitado en config.
        Retorna None si no está habilitado o si el import falla.
        """
        if self._gemma is not None:
            return self._gemma
        if not self.config.gemma_fallback_habilitado:
            return None
        try:
            from gemma_local_provider import GemmaLocalProvider
            self._gemma = GemmaLocalProvider(self.config)
            logger.info(
                "[CIRCUITO] GemmaLocalProvider inicializado — modelo=%s url=%s",
                self.config.gemma_modelo_local,
                self.config.gemma_ollama_url,
            )
            return self._gemma
        except Exception as e:
            logger.warning("[CIRCUITO] No se pudo inicializar GemmaLocalProvider: %s", e)
            return None

    def _prescripcion_con_gemma(
        self,
        prompt_texto: str,
        feedback_loop,
        id_maquina: Optional[str],
        variable:   Optional[str],
    ) -> str:
        """
        Intenta generar prescripción con Gemma local.
        Si Gemma no está disponible o falla, retorna el texto determinista de fallback.
        """
        gemma = self._obtener_gemma()
        if gemma is not None and gemma.disponible():
            try:
                texto = gemma.diagnosticar_fallback(
                    prompt_texto=prompt_texto,
                    feedback_loop=feedback_loop,
                    id_maquina=id_maquina,
                    variable=variable,
                )
                if texto:
                    return texto
            except Exception as e:
                logger.error("[CIRCUITO] Fallo en Gemma local: %s", e)
        else:
            if gemma is not None:
                logger.warning(
                    "[CIRCUITO] Gemma no disponible (Ollama inaccesible o modelo "
                    "no descargado). Usando prescripción determinista."
                )
            else:
                logger.debug(
                    "[CIRCUITO] Fallback Gemma no habilitado (GEMMA_FALLBACK_HABILITADO=0). "
                    "Usando prescripción determinista."
                )
        return self._prescripcion_fallback(prompt_texto)

    def _cargar_contexto_fijo(self) -> tuple:
        """
        Carga system_prompt, tono, estructura y guardarrailes desde YAML.
        Si los archivos no existen, aplica defaults internos.
        Retorna (system_prompt, tono, estructura, guardarrailes).
        """
        try:
            persona = self.config.agente_persona
            system_prompt = persona.get('system_prompt', '')
            tono = persona.get('tono', 'técnico y directo')
            estructura = persona.get('estructura_respuesta', '')
        except FileNotFoundError:
            system_prompt = self._system_prompt_default()
            tono = 'técnico y directo'
            estructura = ''

        try:
            guardarrailes = self.config.politicas_empresa.get('restricciones', '')
        except FileNotFoundError:
            guardarrailes = self._guardarrailes_default()

        return system_prompt, tono, estructura, guardarrailes

    def _obtener_bloque_fijo_cacheado(self) -> tuple:
        """
        Devuelve (bloque_fijo, md5) calculados una sola vez por instancia.
        El bloque fijo no cambia entre alertas — se construye en la primera
        llamada y se reutiliza en todas las siguientes sin costo de string.
        """
        if self._bloque_fijo_cache is None:
            system_prompt, tono, estructura, guardarrailes = self._cargar_contexto_fijo()
            self._bloque_fijo_cache = self._construir_bloque_fijo(
                system_prompt, tono, estructura, guardarrailes
            )
            self._bloque_fijo_hash = hashlib.md5(
                self._bloque_fijo_cache.encode()
            ).hexdigest()
            logger.debug("Bloque fijo construido y hasheado por primera vez.")
        return self._bloque_fijo_cache, self._bloque_fijo_hash

    def _construir_bloque_fijo(
        self,
        system_prompt: str,
        tono: str,
        estructura: str,
        guardarrailes: str,
    ) -> str:
        """
        Ensambla el bloque fijo del prompt: todo lo que NO cambia entre alertas.
        Este bloque es el candidato a ser cacheado en Vertex AI.
        """
        return f"""{system_prompt}

## TONO DE COMUNICACIÓN
{tono}

## ESTRUCTURA DE RESPUESTA REQUERIDA
{estructura}

## RESTRICCIONES DE SEGURIDAD (GUARDARRAÍLES)
{guardarrailes}"""

    def _construir_bloque_variable(self, prompt_texto: str) -> str:
        """Ensambla la parte variable del prompt (cambia en cada alerta)."""
        return (
            f"## CONTEXTO DE LA ALERTA ACTUAL\n{prompt_texto}\n\n"
            "## INSTRUCCIONES\n"
            "1. Analiza los datos técnicos proporcionados.\n"
            "2. Si hay una gráfica adjunta, examina los patrones visuales de la serie temporal.\n"
            "3. Genera un diagnóstico técnico con causa probable y acción recomendada.\n"
            "4. Tu respuesta será convertida a audio y enviada al operario. Sé claro y conciso.\n"
            "5. NUNCA recomiendes acciones que excedan las capacidades mecánicas del equipo.\n"
            "6. Responde SIEMPRE en español."
        )

    def _system_prompt_default(self) -> str:
        """System prompt por defecto si no existe el YAML."""
        return """
Eres un Ingeniero de Procesos Senior especializado en plantas de peletización 
industrial. Tu rol es analizar desviaciones en los parámetros operativos de 
las máquinas peletizadoras y generar prescripciones técnicas claras, seguras 
y accionables para los operarios.

Tu diagnóstico debe incluir:
1. **DIAGNÓSTICO**: Qué está ocurriendo y su severidad (BAJA/MEDIA/ALTA/CRÍTICA)
2. **CAUSA PROBABLE**: La razón más probable de la desviación
3. **ACCIÓN RECOMENDADA**: Pasos específicos que el operario debe seguir
4. **PRIORIDAD**: Tiempo estimado para actuar (INMEDIATO / 15 MIN / 30 MIN)
"""

    def _guardarrailes_default(self) -> str:
        """Guardarraíles por defecto si no existe el YAML."""
        return """
- NUNCA sugerir operar equipos más allá de su capacidad nominal.
- NUNCA ignorar presiones por debajo del mínimo de seguridad.
- NUNCA recomendar manipulación eléctrica directa al operario.
- SIEMPRE priorizar la seguridad del personal sobre la productividad.
- SIEMPRE recomendar notificar al supervisor si la severidad es ALTA o CRÍTICA.
"""

    def _prescripcion_fallback(self, contexto: str) -> str:
        """Prescripción de emergencia si la API de Gemini falla."""
        return (
            "Se detecta una condicion operativa que requiere verificacion en campo. "
            "Revise el panel de control, confirme tendencia de variables y mantenga monitoreo reforzado. "
            "Si la condicion persiste, escale al supervisor de turno."
        )

    def interpretar_audio_operario(
        self,
        audio_bytes: bytes,
        mime_type: str,
        prompt_texto: str,
    ) -> dict:
        """Interpreta directamente un audio del operario con Gemini."""
        try:
            from google.genai import types

            cliente = self._obtener_cliente_genai()
            parte_audio = types.Part.from_bytes(
                data=audio_bytes,
                mime_type=mime_type,
            )
            instruccion = f"""
Eres un analista de operaciones industriales. Escucha el audio del operario y responde SOLO en JSON valido.

Contexto disponible:
{prompt_texto}

Formato requerido:
{{
  "transcripcion": "...",
  "intencion": "ACCION_EJECUTADA | FALSO_POSITIVO | MANTENIMIENTO | OBSERVACION_OPERATIVA | ESCALAMIENTO | OTRO",
  "accion_detectada": "...",
  "resumen_operario": "...",
  "nivel_urgencia": "BAJO | MEDIO | ALTO",
  "respuesta_asistente": "...",
  "senal_resolucion": "SI | NO"
}}

Reglas:
- No inventes datos que no se entiendan.
- Responde en espanol.
- Si el audio no es claro, deja constancia en la transcripcion.
- "respuesta_asistente" debe ser la respuesta de Maria al operario, maximo 2 oraciones, directa y accionable.
- "senal_resolucion" debe ser SI solo si el operario confirma claramente que el problema se soluciono, quedo estable o ya puede reanudarse el monitoreo normal.
"""

            # Retry con backoff exponencial ante rate limit (429)
            # Backoff más corto que el agente (4s/8s/16s) para caber en el
            # timeout de 60s de asyncio.wait_for en _procesar_audio_operario.
            _max_reintentos = 3
            _espera_base    = 4
            response = None
            for _reintento in range(_max_reintentos):
                try:
                    response = cliente.models.generate_content(
                        model=self.config.gemini_audio_model,
                        contents=[parte_audio, instruccion],
                        config=types.GenerateContentConfig(
                            temperature=0.2,
                        ),
                    )
                    break
                except Exception as _err:
                    _es_429 = '429' in str(_err) or 'RESOURCE_EXHAUSTED' in str(_err)
                    if _es_429 and _reintento < _max_reintentos - 1:
                        _espera = _espera_base * (2 ** _reintento)
                        logger.warning(
                            "[AUDIO] Rate limit 429. Reintento %d/%d en %ds...",
                            _reintento + 1, _max_reintentos, _espera,
                        )
                        time.sleep(_espera)
                    else:
                        raise

            return self._parsear_json_audio(response.text.strip())

        except Exception as e:
            logger.error(
                "Error interpretando audio del operario con Gemini: %s | "
                "modelo=%s | mime_type=%s | audio_size=%d bytes",
                e, self.config.gemini_audio_model, mime_type, len(audio_bytes),
                exc_info=True,
            )
            return {
                'transcripcion': '',
                'intencion': 'OTRO',
                'accion_detectada': 'No fue posible interpretar el audio con Gemini.',
                'resumen_operario': 'La interpretacion automatica del audio fallo.',
                'nivel_urgencia': 'MEDIO',
                'respuesta_asistente': (
                    'No pude interpretar bien la nota de voz. '
                    'Repitala indicando la novedad o la accion realizada.'
                ),
                'senal_resolucion': 'NO',
            }

    def _parsear_json_audio(self, texto: str) -> dict:
        """Parsea la respuesta del modelo para audio del operario."""
        try:
            inicio = texto.find('{')
            fin = texto.rfind('}')
            if inicio >= 0 and fin > inicio:
                texto = texto[inicio:fin + 1]
            data = json.loads(texto)
            return {
                'transcripcion': str(data.get('transcripcion', '')).strip(),
                'intencion': str(data.get('intencion', 'OTRO')).strip().upper(),
                'accion_detectada': str(data.get('accion_detectada', '')).strip(),
                'resumen_operario': str(data.get('resumen_operario', '')).strip(),
                'nivel_urgencia': str(data.get('nivel_urgencia', 'MEDIO')).strip().upper(),
                'respuesta_asistente': str(data.get('respuesta_asistente', '')).strip(),
                'senal_resolucion': str(data.get('senal_resolucion', 'NO')).strip().upper(),
            }
        except Exception:
            return {
                'transcripcion': texto.strip(),
                'intencion': 'OTRO',
                'accion_detectada': 'Salida no estructurada del modelo.',
                'resumen_operario': texto.strip()[:300],
                'nivel_urgencia': 'MEDIO',
                'respuesta_asistente': texto.strip()[:180],
                'senal_resolucion': 'NO',
            }


def construir_contexto_alerta(
    tipo_alerta: str,
    id_planta: str,
    id_maquina: str,
    id_formula: str,
    codigo_producto: str,
    variable: str,
    valor_crudo: float,
    valor_suavizado: float,
    limite_min: float,
    limite_max: float,
    corriente_suavizada: float,
    capacidad_nominal: float,
    porcentaje_carga: float,
) -> str:
    """
    Construye el contexto técnico que se inyecta al LLM en cada alerta.
    
    Esta es la "Matriz de Toma de Decisiones (Features)" que el motor
    determinista le proporciona a la IA para generar prescripciones
    informadas y libres de alucinaciones.
    """
    nombres = {
        'presion_vapor': 'Presión de Vapor',
        'temp_acond': 'Temperatura del Acondicionador',
    }
    nombre_var = nombres.get(variable, variable)

    return f"""
### DATOS DEL EQUIPO
- **Planta**: {id_planta}
- **Máquina peletizadora**: {id_maquina}
- **Capacidad nominal**: {capacidad_nominal:.0f} unidades
- **Carga actual**: {porcentaje_carga:.1f}% ({corriente_suavizada:.1f} A)

### FÓRMULA EN OPERACIÓN
- **ID Fórmula**: {id_formula}
- **Código Producto**: {codigo_producto}

### DESVIACIÓN DETECTADA
- **Tipo de alerta**: {tipo_alerta}
- **Variable afectada**: {nombre_var}
- **Valor crudo del sensor**: {valor_crudo:.2f}
- **Valor suavizado (EMA)**: {valor_suavizado:.2f}
- **Límite mínimo permitido**: {limite_min:.1f}
- **Límite máximo permitido**: {limite_max:.1f}
- **Desviación**: {abs(valor_suavizado - (limite_min if 'BAJA' in tipo_alerta else limite_max)):.2f} unidades fuera de banda
"""
