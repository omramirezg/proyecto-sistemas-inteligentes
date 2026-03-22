"""
Herramientas del Agente IA (Tool Use)
======================================
Define las 6 herramientas que el agente puede invocar durante su ciclo
de razonamiento. Cada herramienta accede a datos reales del sistema
(historial, fórmulas, personal, umbrales) para que el modelo razone
con información específica de esta planta, esta máquina y este turno.

Arquitectura:
    - HerramientasAgente encapsula toda la lógica de ejecución.
    - GeminiProvider llama a .declaraciones para registrar las tools en Gemini.
    - GeminiProvider llama a .ejecutar(nombre, args) para despachar cada tool call.
    - Las tools son SÍNCRONAS y devuelven dict siempre (nunca lanzan excepción).
    - Las escalaciones se encolan en self.cola_escalaciones para que el worker
      las procese de forma asíncrona sin bloquear el loop del agente.
"""

import csv
import json
import logging
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Límites de seguridad absolutos — no modificar sin aprobación de ingeniería
# ---------------------------------------------------------------------------
_LIMITES_SEGURIDAD = {
    "presion_vapor": {"min": 2.0, "max": 45.0},   # PSI
    "temp_acond":    {"min": 40.0, "max": 120.0},  # °C
    "corriente":     {"min": 0.0,  "max": 490.0},  # A
}


class HerramientasAgente:
    """
    Colección de herramientas que el agente LLM puede invocar.

    Uso típico:
        herramientas = HerramientasAgente(data_dir, data_loader, config)
        # En GeminiProvider:
        tools = herramientas.declaraciones_gemini()
        resultado = herramientas.ejecutar("consultar_historial", {"id_maquina": "301"})
    """

    def __init__(
        self,
        data_dir: Path,
        data_loader=None,       # DataLoader instance (opcional, para personal)
        config=None,            # ConfigLoader instance (opcional, para límites YAML)
        feedback_loop=None,     # FeedbackLoop instance (opcional, para analizar_feedback)
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_loader = data_loader
        self.config = config
        self.feedback_loop = feedback_loop

        # Cola thread-safe para escalaciones pendientes.
        # El worker async drena esta cola y envía los mensajes de Telegram.
        self.cola_escalaciones: queue.Queue = queue.Queue()

        # Registro de ajustes de umbral hechos en esta sesión
        self._ajustes_umbral: list[dict] = []

        # Lock para escrituras concurrentes a CSVs
        self._lock = threading.Lock()

    # -----------------------------------------------------------------------
    # Dispatcher público
    # -----------------------------------------------------------------------

    def ejecutar(self, nombre: str, args: dict) -> dict:
        """
        Despacha la tool call del modelo a la función correspondiente.
        Siempre retorna dict. Nunca lanza excepción (el agente no puede crashear
        por una tool que falla — registra el error y continúa).
        """
        MAPA = {
            "consultar_historial":    self._consultar_historial,
            "obtener_formula_activa": self._obtener_formula_activa,
            "obtener_operario_turno": self._obtener_operario_turno,
            "ajustar_umbral":         self._ajustar_umbral,
            "escalar_supervisor":     self._escalar_supervisor,
            "registrar_accion":       self._registrar_accion,
            "analizar_feedback":      self._analizar_feedback,
        }
        fn = MAPA.get(nombre)
        if fn is None:
            logger.error("Herramienta desconocida solicitada por el agente: %s", nombre)
            return {"error": f"Herramienta '{nombre}' no existe."}

        try:
            logger.info("[AGENTE] Ejecutando herramienta: %s | args: %s", nombre, args)
            resultado = fn(**args)
            logger.info("[AGENTE] Resultado de %s: %s", nombre, str(resultado)[:200])
            return resultado
        except TypeError as e:
            logger.error("[AGENTE] Args incorrectos para %s: %s", nombre, e)
            return {"error": f"Argumentos inválidos para '{nombre}': {e}"}
        except Exception as e:
            logger.error("[AGENTE] Error ejecutando %s: %s", nombre, e, exc_info=True)
            return {"error": f"Error interno en '{nombre}': {e}"}

    # -----------------------------------------------------------------------
    # Declaraciones para Gemini (Function Declarations)
    # -----------------------------------------------------------------------

    def declaraciones_gemini(self) -> list:
        """
        Retorna la lista de FunctionDeclaration compatible con google-genai SDK.
        El agente Gemini usa estas declaraciones para saber qué herramientas
        tiene disponibles y con qué argumentos llamarlas.
        """
        from google.genai import types

        return [
            types.FunctionDeclaration(
                name="consultar_historial",
                description=(
                    "Consulta los últimos incidentes registrados para una máquina y variable específica. "
                    "Retorna causa probable, prescripción y feedback del operario de cada incidente. "
                    "Usar siempre al inicio para contextualizar el diagnóstico con historial real de la planta."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "id_maquina": types.Schema(
                            type=types.Type.STRING,
                            description="ID de la máquina (ej: '301', '302').",
                        ),
                        "variable": types.Schema(
                            type=types.Type.STRING,
                            description="Variable a consultar: 'presion_vapor' o 'temp_acond'.",
                        ),
                        "limite": types.Schema(
                            type=types.Type.INTEGER,
                            description="Número máximo de incidentes a retornar (default: 5, max: 10).",
                        ),
                    },
                    required=["id_maquina", "variable"],
                ),
            ),
            types.FunctionDeclaration(
                name="obtener_formula_activa",
                description=(
                    "Obtiene los parámetros de la fórmula de producción activa: "
                    "límites de temperatura, presión, humedad objetivo, durabilidad y PQF. "
                    "Usar cuando haya duda sobre si los umbrales son correctos para el producto actual."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "id_planta": types.Schema(
                            type=types.Type.STRING,
                            description="ID de la planta (ej: '001').",
                        ),
                        "id_formula": types.Schema(
                            type=types.Type.STRING,
                            description="ID de la fórmula activa (ej: '3360').",
                        ),
                    },
                    required=["id_planta", "id_formula"],
                ),
            ),
            types.FunctionDeclaration(
                name="obtener_operario_turno",
                description=(
                    "Retorna el nombre, rol y número de celular del operario actualmente "
                    "asignado a la máquina en el turno actual. "
                    "Usar para personalizar la prescripción o determinar a quién escalar."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "id_planta": types.Schema(
                            type=types.Type.STRING,
                            description="ID de la planta.",
                        ),
                        "id_maquina": types.Schema(
                            type=types.Type.STRING,
                            description="ID de la máquina.",
                        ),
                    },
                    required=["id_planta", "id_maquina"],
                ),
            ),
            types.FunctionDeclaration(
                name="ajustar_umbral",
                description=(
                    "Registra un ajuste recomendado de umbral operativo para una variable. "
                    "El ajuste se valida contra límites de seguridad absolutos antes de aceptarse. "
                    "Usar solo cuando la evidencia indique que el umbral actual es incorrecto para "
                    "el producto o las condiciones ambientales actuales."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "id_maquina": types.Schema(
                            type=types.Type.STRING,
                            description="ID de la máquina.",
                        ),
                        "variable": types.Schema(
                            type=types.Type.STRING,
                            description="Variable a ajustar: 'presion_vapor' o 'temp_acond'.",
                        ),
                        "tipo_limite": types.Schema(
                            type=types.Type.STRING,
                            description="Límite a modificar: 'min' o 'max'.",
                        ),
                        "nuevo_valor": types.Schema(
                            type=types.Type.NUMBER,
                            description="Nuevo valor propuesto para el límite.",
                        ),
                        "justificacion": types.Schema(
                            type=types.Type.STRING,
                            description="Razón técnica del ajuste (requerida para auditoría).",
                        ),
                    },
                    required=["id_maquina", "variable", "tipo_limite", "nuevo_valor", "justificacion"],
                ),
            ),
            types.FunctionDeclaration(
                name="escalar_supervisor",
                description=(
                    "Encola una notificación de escalamiento al supervisor de turno. "
                    "Usar cuando la severidad sea ALTA o CRÍTICA, cuando la situación supere "
                    "la capacidad de acción del operario, o cuando el incidente lleve más de "
                    "15 minutos sin resolución."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "id_maquina": types.Schema(
                            type=types.Type.STRING,
                            description="ID de la máquina con el incidente.",
                        ),
                        "mensaje": types.Schema(
                            type=types.Type.STRING,
                            description=(
                                "Mensaje técnico para el supervisor: qué pasó, "
                                "en qué máquina, qué variable, valor actual vs límite. "
                                "Máximo 200 caracteres."
                            ),
                        ),
                        "severidad": types.Schema(
                            type=types.Type.STRING,
                            description="Severidad del incidente: 'MEDIA', 'ALTA' o 'CRÍTICA'.",
                        ),
                    },
                    required=["id_maquina", "mensaje", "severidad"],
                ),
            ),
            types.FunctionDeclaration(
                name="registrar_accion",
                description=(
                    "Registra la acción prescrita por el agente en el historial de acciones. "
                    "Llamar siempre como última acción antes de dar la respuesta final, "
                    "para cerrar el loop de aprendizaje del sistema."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "id_maquina": types.Schema(
                            type=types.Type.STRING,
                            description="ID de la máquina.",
                        ),
                        "variable": types.Schema(
                            type=types.Type.STRING,
                            description="Variable involucrada en la alerta.",
                        ),
                        "accion_prescrita": types.Schema(
                            type=types.Type.STRING,
                            description="Descripción de la acción prescrita por el agente.",
                        ),
                        "nivel_confianza": types.Schema(
                            type=types.Type.STRING,
                            description="Confianza del agente en la prescripción: 'ALTA', 'MEDIA' o 'BAJA'.",
                        ),
                    },
                    required=["id_maquina", "variable", "accion_prescrita", "nivel_confianza"],
                ),
            ),
            types.FunctionDeclaration(
                name="analizar_feedback",
                description=(
                    "Consulta las estadísticas de feedback del operario para esta máquina y variable. "
                    "Retorna tasa de falsos positivos, score promedio de efectividad y si hay deriva "
                    "de umbrales detectada. Usar cuando haya duda sobre si el umbral está bien calibrado "
                    "o cuando la alerta parezca fuera de lo normal para esta máquina."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "id_maquina": types.Schema(
                            type=types.Type.STRING,
                            description="ID de la máquina.",
                        ),
                        "variable": types.Schema(
                            type=types.Type.STRING,
                            description="Variable a analizar: 'presion_vapor' o 'temp_acond'.",
                        ),
                    },
                    required=["id_maquina", "variable"],
                ),
            ),
        ]

    # -----------------------------------------------------------------------
    # Implementaciones de herramientas
    # -----------------------------------------------------------------------

    def _consultar_historial(
        self,
        id_maquina: str,
        variable: str,
        limite: int = 5,
    ) -> dict:
        """
        Busca los últimos incidentes de una máquina+variable en historial_alertas.csv.
        Retorna prescripciones previas y feedback del operario para que el modelo
        pueda razonar sobre patrones recurrentes.
        """
        limite = min(int(limite), 10)
        archivo = self.data_dir / "historial_alertas.csv"

        if not archivo.exists():
            return {"encontrados": 0, "incidentes": [], "nota": "Historial no disponible."}

        incidentes = []
        try:
            with archivo.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                # Leer todo y filtrar (CSV pequeño — cabe en memoria)
                filas = [
                    r for r in reader
                    if r.get("id_maquina") == str(id_maquina)
                    and r.get("variable") == variable
                    and r.get("prescripcion_ia", "").strip()
                ]

            # Tomar los más recientes
            for fila in filas[-limite:]:
                incidentes.append({
                    "timestamp":          fila.get("timestamp", ""),
                    "tipo_alerta":        fila.get("tipo_alerta", ""),
                    "valor_crudo":        fila.get("valor_crudo", ""),
                    "limite_violado":     fila.get("limite_violado", ""),
                    "prescripcion_ia":    fila.get("prescripcion_ia", "")[:300],
                    "feedback_operario":  fila.get("feedback_operario", "") or "Sin feedback",
                })

        except Exception as e:
            logger.error("Error leyendo historial_alertas.csv: %s", e)
            return {"encontrados": 0, "incidentes": [], "error": str(e)}

        return {
            "encontrados": len(incidentes),
            "maquina":     id_maquina,
            "variable":    variable,
            "incidentes":  incidentes,
        }

    def _obtener_formula_activa(
        self,
        id_planta: str,
        id_formula: str,
    ) -> dict:
        """
        Lee los parámetros de la fórmula activa desde maestro_formulas.csv.
        Incluye límites de temperatura/presión, humedad objetivo, durabilidad y PQF.
        """
        archivo = self.data_dir / "maestro_formulas.csv"

        if not archivo.exists():
            return {"error": "maestro_formulas.csv no encontrado."}

        try:
            with archivo.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for fila in reader:
                    if (
                        str(fila.get("id_planta", "")).zfill(3) == str(id_planta).zfill(3)
                        and str(fila.get("id_formula", "")) == str(id_formula)
                    ):
                        return {
                            "id_formula":          fila.get("id_formula"),
                            "codigo_producto":     fila.get("codigo_producto", ""),
                            "temp_min":            fila.get("t_min", ""),
                            "temp_max":            fila.get("t_max", ""),
                            "presion_min":         fila.get("p_min", ""),
                            "presion_max":         fila.get("p_max", ""),
                            "pqf":                 fila.get("pqf", ""),
                            "humedad_objetivo":    fila.get("humedad_objetivo", ""),
                            "durabilidad_objetivo": fila.get("durabilidad_objetivo", ""),
                        }

        except Exception as e:
            logger.error("Error leyendo maestro_formulas.csv: %s", e)
            return {"error": str(e)}

        return {
            "error": f"Fórmula {id_formula} no encontrada en planta {id_planta}."
        }

    def _obtener_operario_turno(
        self,
        id_planta: str,
        id_maquina: str,
    ) -> dict:
        """
        Retorna el operario actualmente en turno para la máquina dada.
        Usa DataLoader si está disponible; si no, lee maestro_personal.csv directamente.
        """
        if self.data_loader is not None:
            try:
                df = self.data_loader.obtener_personal_en_turno(id_planta, id_maquina)
                if df.empty:
                    return {"encontrado": False, "nota": "No hay operario asignado en este turno."}

                fila = df.iloc[0]
                return {
                    "encontrado":      True,
                    "nombre":          str(fila.get("nombre_completo", "")),
                    "rol":             str(fila.get("rol", "")),
                    "celular":         str(fila.get("numero_celular", "")),
                    "recibe_alertas":  str(fila.get("recibe_alertas", "")),
                }
            except Exception as e:
                logger.warning("DataLoader falló para personal en turno: %s. Leyendo CSV.", e)

        # Fallback: leer CSV directamente
        archivo = self.data_dir / "maestro_personal.csv"
        if not archivo.exists():
            return {"encontrado": False, "error": "maestro_personal.csv no encontrado."}

        hora_actual = datetime.now().strftime("%H:%M:%S")
        try:
            with archivo.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for fila in reader:
                    if (
                        str(fila.get("id_planta", "")).zfill(3) == str(id_planta).zfill(3)
                        and (
                            str(fila.get("id_maquina_asignada", "")) == str(id_maquina)
                            or fila.get("id_maquina_asignada", "") == "TODAS"
                        )
                    ):
                        inicio = fila.get("hora_inicio_turno", "00:00:00")
                        fin = fila.get("hora_fin_turno", "23:59:59")
                        if _en_turno(hora_actual, inicio, fin):
                            return {
                                "encontrado": True,
                                "nombre":     fila.get("nombre_completo", ""),
                                "rol":        fila.get("rol", ""),
                                "celular":    fila.get("numero_celular", ""),
                            }
        except Exception as e:
            logger.error("Error leyendo maestro_personal.csv: %s", e)
            return {"encontrado": False, "error": str(e)}

        return {"encontrado": False, "nota": "No se encontró operario en turno."}

    def _ajustar_umbral(
        self,
        id_maquina: str,
        variable: str,
        tipo_limite: str,
        nuevo_valor: float,
        justificacion: str,
    ) -> dict:
        """
        Valida y registra un ajuste de umbral recomendado por el agente.
        El ajuste se persiste en data/ajustes_umbrales_runtime.json para que
        el motor de reglas lo aplique en el siguiente ciclo.
        Los límites de seguridad absolutos nunca se pueden sobrepasar.
        """
        variable = variable.strip()
        tipo_limite = tipo_limite.strip().lower()
        nuevo_valor = float(nuevo_valor)

        # Validar variable permitida
        if variable not in _LIMITES_SEGURIDAD:
            return {
                "aceptado": False,
                "razon": f"Variable '{variable}' no está en el conjunto de variables ajustables.",
            }

        # Validar tipo de límite
        if tipo_limite not in ("min", "max"):
            return {
                "aceptado": False,
                "razon": "tipo_limite debe ser 'min' o 'max'.",
            }

        # Validar contra límites de seguridad absolutos
        seg = _LIMITES_SEGURIDAD[variable]
        if nuevo_valor < seg["min"] or nuevo_valor > seg["max"]:
            return {
                "aceptado": False,
                "razon": (
                    f"Valor {nuevo_valor} fuera de rango de seguridad absoluto "
                    f"[{seg['min']}, {seg['max']}] para {variable}."
                ),
            }

        ajuste = {
            "timestamp":    datetime.now().isoformat(),
            "id_maquina":   str(id_maquina),
            "variable":     variable,
            "tipo_limite":  tipo_limite,
            "nuevo_valor":  nuevo_valor,
            "justificacion": justificacion[:500],
            "origen":       "agente_ia",
        }

        # Persistir en JSON para que el motor de reglas lo aplique
        archivo_ajustes = self.data_dir / "ajustes_umbrales_runtime.json"
        with self._lock:
            try:
                ajustes_existentes = []
                if archivo_ajustes.exists():
                    with archivo_ajustes.open(encoding="utf-8") as f:
                        ajustes_existentes = json.load(f)
                ajustes_existentes.append(ajuste)
                with archivo_ajustes.open("w", encoding="utf-8") as f:
                    json.dump(ajustes_existentes, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error("Error persistiendo ajuste de umbral: %s", e)

        self._ajustes_umbral.append(ajuste)
        logger.info(
            "[AGENTE] Ajuste de umbral aceptado: %s %s.%s → %s",
            id_maquina, variable, tipo_limite, nuevo_valor,
        )
        return {
            "aceptado":    True,
            "id_maquina":  id_maquina,
            "variable":    variable,
            "tipo_limite": tipo_limite,
            "nuevo_valor": nuevo_valor,
            "nota": "Ajuste registrado. Se aplicará en el próximo ciclo del motor de reglas.",
        }

    def _escalar_supervisor(
        self,
        id_maquina: str,
        mensaje: str,
        severidad: str,
    ) -> dict:
        """
        Encola una notificación de escalamiento para el supervisor de turno.
        La cola es drenada por el worker async (main.py) sin bloquear al agente.
        """
        severidad = severidad.upper().strip()
        if severidad not in ("MEDIA", "ALTA", "CRÍTICA", "CRITICA"):
            severidad = "ALTA"

        escalacion = {
            "timestamp":  datetime.now().isoformat(),
            "id_maquina": str(id_maquina),
            "mensaje":    mensaje[:400],
            "severidad":  severidad,
            "origen":     "agente_ia",
        }

        self.cola_escalaciones.put(escalacion)
        logger.warning(
            "[AGENTE] Escalación encolada — Máquina: %s | Severidad: %s | Mensaje: %s",
            id_maquina, severidad, mensaje[:100],
        )
        return {
            "encolado":   True,
            "id_maquina": id_maquina,
            "severidad":  severidad,
            "nota": "Notificación encolada. El supervisor será alertado en segundos.",
        }

    def _registrar_accion(
        self,
        id_maquina: str,
        variable: str,
        accion_prescrita: str,
        nivel_confianza: str,
    ) -> dict:
        """
        Persiste la acción prescrita por el agente en historial_acciones_agente.csv.
        Cierra el loop de aprendizaje: este historial es consultado por consultar_historial
        en futuras alertas de la misma máquina.
        """
        nivel_confianza = nivel_confianza.upper().strip()
        if nivel_confianza not in ("ALTA", "MEDIA", "BAJA"):
            nivel_confianza = "MEDIA"

        archivo = self.data_dir / "historial_acciones_agente.csv"
        campos = [
            "timestamp", "id_maquina", "variable",
            "accion_prescrita", "nivel_confianza",
        ]
        fila = {
            "timestamp":       datetime.now().isoformat(),
            "id_maquina":      str(id_maquina),
            "variable":        variable,
            "accion_prescrita": accion_prescrita[:500],
            "nivel_confianza": nivel_confianza,
        }

        with self._lock:
            try:
                es_nuevo = not archivo.exists()
                with archivo.open("a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=campos)
                    if es_nuevo:
                        writer.writeheader()
                    writer.writerow(fila)
            except Exception as e:
                logger.error("Error escribiendo historial_acciones_agente.csv: %s", e)
                return {"registrado": False, "error": str(e)}

        logger.info(
            "[AGENTE] Acción registrada — Máquina: %s | Variable: %s | Confianza: %s",
            id_maquina, variable, nivel_confianza,
        )
        return {"registrado": True, "nivel_confianza": nivel_confianza}

    def _analizar_feedback(
        self,
        id_maquina: str,
        variable: str,
    ) -> dict:
        """
        Consulta las estadísticas de feedback del operario para esta máquina+variable.
        Permite al agente saber si hay un problema de calibración de umbrales
        antes de generar la prescripción.
        """
        if self.feedback_loop is None:
            return {
                "disponible": False,
                "nota": "FeedbackLoop no configurado en esta instancia.",
            }

        stats = self.feedback_loop.estadisticas(
            id_maquina=str(id_maquina),
            variable=variable,
        )
        derivas = self.feedback_loop.detectar_deriva_umbrales(ventana_dias=14)
        deriva_esta_variable = next(
            (d for d in derivas
             if d["id_maquina"] == str(id_maquina) and d["variable"] == variable),
            None,
        )

        resultado = {
            "disponible":        True,
            "id_maquina":        id_maquina,
            "variable":          variable,
            "total_alertas":     stats["total_alertas"],
            "con_feedback":      stats["con_feedback"],
            "tasa_utiles":       stats["tasa_utiles"],
            "tasa_falsos":       stats["tasa_falsos"],
            "score_promedio":    stats["score_promedio"],
            "deriva_detectada":  deriva_esta_variable is not None,
        }

        if deriva_esta_variable:
            resultado["alerta_deriva"] = deriva_esta_variable["recomendacion"]
            resultado["nota"] = (
                "ATENCIÓN: Alta tasa de falsos positivos detectada. "
                "El umbral puede estar mal calibrado. "
                "Considera esto antes de prescribir ajustes agresivos."
            )
        else:
            resultado["nota"] = "Sin deriva de umbrales detectada en los últimos 14 días."

        return resultado


# ---------------------------------------------------------------------------
# Utilidad interna
# ---------------------------------------------------------------------------

def _en_turno(hora_actual: str, inicio: str, fin: str) -> bool:
    """
    Verifica si hora_actual está dentro del turno [inicio, fin].
    Maneja turnos que cruzan la medianoche (ej: 22:00 - 06:00).
    """
    try:
        fmt = "%H:%M:%S"
        h = datetime.strptime(hora_actual, fmt).time()
        i = datetime.strptime(inicio, fmt).time()
        f = datetime.strptime(fin, fmt).time()
        if i <= f:
            return i <= h <= f
        return h >= i or h <= f          # Turno nocturno cruza medianoche
    except ValueError:
        return False
