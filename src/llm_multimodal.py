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

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


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

    def diagnosticar(
        self,
        prompt_texto: str,
        imagen_bytes: Optional[bytes] = None,
    ) -> str:
        """
        Genera diagnóstico multimodal con Gemini.
        
        Envía texto + imagen (gráfica de telemetría) al modelo.
        Cada llamada es independiente (stateless).
        Incluye retry con backoff exponencial para errores 429.
        """
        self._inicializar_modelo()

        try:
            from vertexai.generative_models import Part, Image

            # Construir el system prompt desde YAML
            try:
                persona = self.config.agente_persona
                system_prompt = persona.get('system_prompt', '')
                tono = persona.get('tono', 'técnico y directo')
                estructura = persona.get('estructura_respuesta', '')
            except FileNotFoundError:
                system_prompt = self._system_prompt_default()
                tono = 'técnico y directo'
                estructura = ''

            # Construir políticas desde YAML
            try:
                politicas = self.config.politicas_empresa
                guardarrailes = politicas.get('restricciones', '')
            except FileNotFoundError:
                guardarrailes = self._guardarrailes_default()

            # Construir el prompt completo
            prompt_completo = self._construir_prompt(
                system_prompt=system_prompt,
                tono=tono,
                estructura=estructura,
                guardarrailes=guardarrailes,
                contexto_alerta=prompt_texto,
            )

            # Preparar contenido multimodal
            contenido = [prompt_completo]

            if imagen_bytes:
                imagen_part = Part.from_data(
                    data=imagen_bytes,
                    mime_type='image/png',
                )
                contenido.append(imagen_part)
                contenido.append(
                    "ANALIZA la gráfica anterior junto con el contexto técnico. "
                    "Identifica patrones visuales (caídas abruptas, oscilaciones, "
                    "tendencias) que complementen tu diagnóstico."
                )
                logger.info("Enviando prompt MULTIMODAL a Gemini (texto + imagen)")
            else:
                logger.info("Enviando prompt de solo texto a Gemini")

            # Llamar al modelo con RETRY para rate limits (429)
            max_reintentos = 3
            espera_base = 5  # segundos

            for intento in range(max_reintentos):
                try:
                    response = self._model.generate_content(
                        contenido,
                        generation_config={
                            'temperature': 0.3,
                            'max_output_tokens': 800,
                            'top_p': 0.8,
                        }
                    )

                    prescripcion = response.text.strip()
                    logger.info(
                        "Prescripción generada por Gemini (%d caracteres)",
                        len(prescripcion)
                    )
                    return prescripcion

                except Exception as api_error:
                    error_str = str(api_error)
                    if '429' in error_str or 'Resource exhausted' in error_str:
                        espera = espera_base * (2 ** intento)
                        logger.warning(
                            "Rate limit Gemini (429). Reintento %d/%d "
                            "en %d seg...",
                            intento + 1, max_reintentos, espera
                        )
                        time.sleep(espera)
                    else:
                        raise api_error

            # Si agotó reintentos
            logger.error("Agotados %d reintentos para Gemini.", max_reintentos)
            return self._prescripcion_fallback(prompt_texto)

        except Exception as e:
            logger.error("Error en llamada a Gemini: %s", e)
            return self._prescripcion_fallback(prompt_texto)

    def _construir_prompt(
        self,
        system_prompt: str,
        tono: str,
        estructura: str,
        guardarrailes: str,
        contexto_alerta: str,
    ) -> str:
        """Construye el prompt completo con todas las capas de contexto."""
        return f"""
{system_prompt}

## TONO DE COMUNICACIÓN
{tono}

## ESTRUCTURA DE RESPUESTA REQUERIDA
{estructura}

## RESTRICCIONES DE SEGURIDAD (GUARDARRAÍLES)
{guardarrailes}

## CONTEXTO DE LA ALERTA ACTUAL
{contexto_alerta}

## INSTRUCCIONES
1. Analiza los datos técnicos proporcionados.
2. Si hay una gráfica adjunta, examina los patrones visuales de la serie temporal.
3. Genera un diagnóstico técnico con causa probable y acción recomendada.
4. Tu respuesta será convertida a audio y enviada al operario. Sé claro y conciso.
5. NUNCA recomiendes acciones que excedan las capacidades mecánicas del equipo.
6. Responde SIEMPRE en español.
"""

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
            "⚠️ PRESCRIPCIÓN DE RESPALDO (API no disponible): "
            "Se ha detectado una desviación en los parámetros operativos. "
            "Favor verificar los valores en el panel de control de la máquina "
            "y notificar al supervisor de turno si la condición persiste."
        )


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
