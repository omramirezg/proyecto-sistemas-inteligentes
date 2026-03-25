"""
Feedback Loop — RLHF Liviano
================================
Implementa el principio de RLHF (Reinforcement Learning from Human Feedback)
sin fine-tuning del modelo: usa el feedback real de los operarios para mejorar
las prescripciones futuras mediante inyección dinámica de few-shot examples.

¿Por qué es RLHF liviano y no RLHF real?
    RLHF real:    feedback humano → ajuste de pesos del modelo (requiere GPU masiva + datos masivos)
    RLHF liviano: feedback humano → mejora del contexto en inferencia (lo que hacemos aquí)

El principio es idéntico: señal humana de "bueno/malo" alimenta al modelo para que
mejore su comportamiento. La implementación usa el prompt en lugar de los gradientes.

Señales de recompensa disponibles:
    UTIL          → score 1.0  (prescripción correcta, operario la aplicó)
    FALLA_MECANICA→ score 0.5  (diagnóstico parcialmente correcto, falla real confirmada)
    FALSO_POSITIVO→ score 0.0  (prescripción incorrecta, no había problema real)

Componentes:
    1. Extracción de ejemplos few-shot desde prescripciones con UTIL
    2. Extracción de antipatrones desde prescripciones con FALSO_POSITIVO
    3. Detección de deriva de umbrales (tasa falsos > 30% → umbral mal calibrado)
    4. Estadísticas de efectividad por máquina/variable
"""

import csv
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de calibración
# ---------------------------------------------------------------------------

REWARD_SCORES: dict[str, float] = {
    "UTIL":           1.0,
    "FALLA_MECANICA": 0.5,
    "FALSO_POSITIVO": 0.0,
}

# Una tasa de falsos positivos >= 30% en N alertas evaluadas indica
# que el umbral de esa variable probablemente está mal calibrado.
_TASA_DERIVA            = 0.30
_MIN_ALERTAS_PARA_DERIVA = 5
_CACHE_TTL_SEG          = 300.0   # 5 minutos de caché para el CSV


class FeedbackLoop:
    """
    Motor de feedback que conecta las reacciones del operario con el LLM.

    Uso típico:
        fl = FeedbackLoop(config.data_dir)

        # Inyectar few-shot en el prompt antes de llamar al modelo
        bloque = fl.construir_bloque_fewshot("301", "presion_vapor")
        prompt_enriquecido = prompt_base + bloque

        # Detectar umbrales mal calibrados
        derivas = fl.detectar_deriva_umbrales(ventana_dias=14)
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self._cache_alertas: Optional[list[dict]] = None
        self._cache_ts: float = 0.0

    # -----------------------------------------------------------------------
    # Lectura con caché
    # -----------------------------------------------------------------------

    def _leer_historial(self, forzar: bool = False) -> list[dict]:
        """
        Lee historial_alertas.csv con caché de 5 minutos.
        El caché evita múltiples lecturas de disco en un mismo ciclo del worker.
        """
        if (
            not forzar
            and self._cache_alertas is not None
            and (time.time() - self._cache_ts) < _CACHE_TTL_SEG
        ):
            return self._cache_alertas

        archivo = self.data_dir / "historial_alertas.csv"
        if not archivo.exists():
            logger.warning("historial_alertas.csv no encontrado en %s", self.data_dir)
            return []

        try:
            with archivo.open(encoding="utf-8") as f:
                self._cache_alertas = list(csv.DictReader(f))
            self._cache_ts = time.time()
            logger.debug(
                "[FEEDBACK] Historial cargado: %d alertas.", len(self._cache_alertas)
            )
            return self._cache_alertas
        except Exception as e:
            logger.error("[FEEDBACK] Error leyendo historial_alertas.csv: %s", e)
            return []

    # -----------------------------------------------------------------------
    # Señal de recompensa
    # -----------------------------------------------------------------------

    def calcular_score(self, feedback: Optional[str]) -> Optional[float]:
        """
        Convierte el tipo de feedback en un score de recompensa en [0, 1].
        Retorna None si no hay feedback (alerta sin evaluar).
        """
        if not feedback or not feedback.strip():
            return None
        return REWARD_SCORES.get(feedback.strip().upper())

    # -----------------------------------------------------------------------
    # Few-shot examples
    # -----------------------------------------------------------------------

    def obtener_ejemplos_positivos(
        self,
        id_maquina: str,
        variable: str,
        limite: int = 3,
    ) -> list[dict]:
        """
        Retorna las últimas N prescripciones marcadas como UTIL para esta
        máquina+variable. Son los casos de éxito que el modelo debe imitar.
        """
        alertas = self._leer_historial()
        ejemplos = [
            {
                "timestamp":       a.get("timestamp", ""),
                "tipo_alerta":     a.get("tipo_alerta", ""),
                "valor_crudo":     a.get("valor_crudo", ""),
                "limite_violado":  a.get("limite_violado", ""),
                "porcentaje_carga": a.get("porcentaje_carga", ""),
                "prescripcion":    a.get("prescripcion_ia", "")[:400],
            }
            for a in alertas
            if (
                str(a.get("id_maquina", "")) == str(id_maquina)
                and a.get("variable", "") == variable
                and a.get("feedback_operario", "").strip().upper() == "UTIL"
                and a.get("prescripcion_ia", "").strip()
            )
        ]
        # Más recientes primero
        ejemplos.sort(key=lambda x: x["timestamp"], reverse=True)
        return ejemplos[:limite]

    def obtener_antipatrones(
        self,
        id_maquina: str,
        variable: str,
        limite: int = 3,
    ) -> list[dict]:
        """
        Retorna las últimas N prescripciones marcadas como FALSO_POSITIVO.
        Son los enfoques incorrectos que el modelo debe evitar.
        """
        alertas = self._leer_historial()
        antipatrones = [
            {
                "timestamp":           a.get("timestamp", ""),
                "tipo_alerta":         a.get("tipo_alerta", ""),
                "valor_crudo":         a.get("valor_crudo", ""),
                "prescripcion_fallida": a.get("prescripcion_ia", "")[:300],
            }
            for a in alertas
            if (
                str(a.get("id_maquina", "")) == str(id_maquina)
                and a.get("variable", "") == variable
                and a.get("feedback_operario", "").strip().upper() == "FALSO_POSITIVO"
                and a.get("prescripcion_ia", "").strip()
            )
        ]
        antipatrones.sort(key=lambda x: x["timestamp"], reverse=True)
        return antipatrones[:limite]

    def construir_bloque_fewshot(
        self,
        id_maquina: str,
        variable: str,
    ) -> str:
        """
        Construye el bloque de few-shot para inyectar en el prompt del LLM.

        Contiene:
          - Ejemplos de prescripciones exitosas (UTIL) → el modelo aprende qué funciona
          - Antipatrones (FALSO_POSITIVO) → el modelo aprende qué evitar

        Si no hay feedback disponible aún, retorna string vacío
        (el sistema funciona igual, sin penalización).
        """
        ejemplos     = self.obtener_ejemplos_positivos(id_maquina, variable)
        antipatrones = self.obtener_antipatrones(id_maquina, variable)

        if not ejemplos and not antipatrones:
            return ""

        lineas: list[str] = []

        if ejemplos:
            lineas.append(
                "## PRESCRIPCIONES EXITOSAS EN ESTA MÁQUINA\n"
                "El operario confirmó que los siguientes enfoques fueron efectivos "
                "para situaciones similares. Aprende de ellos:"
            )
            for i, e in enumerate(ejemplos, 1):
                lineas.append(
                    f"\nEjemplo {i} — {e['tipo_alerta']} | "
                    f"Valor: {e['valor_crudo']} | Carga: {e['porcentaje_carga']}%"
                )
                lineas.append(f"Prescripción efectiva: {e['prescripcion']}")

        if antipatrones:
            lineas.append(
                "\n## ENFOQUES QUE GENERARON FALSO POSITIVO EN ESTA MÁQUINA\n"
                "El operario marcó los siguientes enfoques como incorrectos. "
                "No repitas estas prescripciones:"
            )
            for i, a in enumerate(antipatrones, 1):
                lineas.append(
                    f"\nAntipatrón {i} — {a['tipo_alerta']} | Valor: {a['valor_crudo']}"
                )
                lineas.append(f"Prescripción fallida: {a['prescripcion_fallida']}")

        # Agregar conversaciones pasadas relevantes si existen
        conv_block = self._obtener_conversaciones_relevantes(id_maquina)
        if conv_block:
            lineas.append(conv_block)

        return "\n".join(lineas)

    def _obtener_conversaciones_relevantes(
        self, id_maquina: str, max_conv: int = 2,
    ) -> str:
        """Recupera conversaciones pasadas exitosas para esta máquina (RAG).

        Lee del historial_conversaciones.csv y extrae las últimas conversaciones
        completas para dar contexto al LLM sobre cómo se resolvieron incidentes
        anteriores en esta misma máquina.
        """
        archivo = self._data_dir / 'historial_conversaciones.csv'
        if not archivo.exists():
            return ""

        try:
            conversaciones: dict[str, list] = {}
            with open(archivo, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if str(row.get('id_maquina', '')) != str(id_maquina):
                        continue
                    inc_id = row.get('incidente_id', '')
                    if inc_id not in conversaciones:
                        conversaciones[inc_id] = []
                    conversaciones[inc_id].append({
                        'rol': row.get('rol', ''),
                        'contenido': row.get('contenido', ''),
                    })

            if not conversaciones:
                return ""

            # Tomar las últimas N conversaciones
            ultimas = list(conversaciones.values())[-max_conv:]

            lineas = [
                "\n## CONVERSACIONES PASADAS EXITOSAS EN ESTA MÁQUINA",
                "Estos son intercambios reales que resolvieron incidentes anteriores. "
                "Úsalos como referencia para el tono, nivel de detalle y enfoque:",
            ]
            for i, conv in enumerate(ultimas, 1):
                lineas.append(f"\n--- Incidente resuelto {i} ---")
                for msg in conv:
                    prefijo = "Operario" if msg['rol'] == 'operario' else "María"
                    lineas.append(f"{prefijo}: {msg['contenido']}")

            return "\n".join(lineas)

        except Exception as e:
            logger.debug("[RLHF] Error leyendo conversaciones: %s", e)
            return ""

    # -----------------------------------------------------------------------
    # Detección de deriva de umbrales
    # -----------------------------------------------------------------------

    def detectar_deriva_umbrales(
        self,
        ventana_dias: int = 14,
    ) -> list[dict]:
        """
        Analiza el historial para detectar pares (máquina, variable) donde
        la tasa de falsos positivos supera el 30%.

        Una tasa alta de falsos positivos indica que el umbral configurado
        en maestro_formulas.csv está mal calibrado para las condiciones reales
        de operación — genera alarmas innecesarias que el operario ignora.

        Returns:
            Lista de derivas detectadas con recomendación por cada par afectado.
        """
        alertas  = self._leer_historial(forzar=True)
        corte    = (datetime.now() - timedelta(days=ventana_dias)).isoformat()

        # Acumular estadísticas por (máquina, variable)
        grupos: dict = defaultdict(lambda: {"total": 0, "falsos": 0, "utiles": 0})

        for a in alertas:
            if a.get("timestamp", "") < corte:
                continue
            fb = a.get("feedback_operario", "").strip().upper()
            if fb not in REWARD_SCORES:
                continue                               # Sin feedback — no cuenta

            clave = (str(a.get("id_maquina", "")), str(a.get("variable", "")))
            grupos[clave]["total"] += 1
            if fb == "FALSO_POSITIVO":
                grupos[clave]["falsos"] += 1
            elif fb == "UTIL":
                grupos[clave]["utiles"] += 1

        derivas: list[dict] = []
        for (maquina, variable), stats in grupos.items():
            if stats["total"] < _MIN_ALERTAS_PARA_DERIVA:
                continue                               # Muestra insuficiente
            tasa = stats["falsos"] / stats["total"]
            if tasa < _TASA_DERIVA:
                continue

            derivas.append({
                "id_maquina":            maquina,
                "variable":              variable,
                "tasa_falsos_positivos": round(tasa, 3),
                "alertas_evaluadas":     stats["total"],
                "falsos":                stats["falsos"],
                "utiles":                stats["utiles"],
                "ventana_dias":          ventana_dias,
                "recomendacion": (
                    f"Revisar umbral de '{variable}' para máquina {maquina}. "
                    f"El {tasa * 100:.0f}% de las alertas evaluadas en los últimos "
                    f"{ventana_dias} días fueron marcadas como falso positivo, "
                    f"lo que sugiere que el umbral actual genera alarmas innecesarias."
                ),
            })

        if derivas:
            logger.warning(
                "[FEEDBACK] Deriva de umbrales detectada en %d pares (máquina, variable). "
                "Revisar maestro_formulas.csv.",
                len(derivas),
            )
        else:
            logger.info(
                "[FEEDBACK] Sin deriva de umbrales detectada en ventana de %d días.",
                ventana_dias,
            )

        return derivas

    # -----------------------------------------------------------------------
    # Estadísticas de efectividad
    # -----------------------------------------------------------------------

    def estadisticas(
        self,
        id_maquina: Optional[str] = None,
        variable: Optional[str] = None,
    ) -> dict:
        """
        Calcula métricas de efectividad del sistema de prescripción.
        Filtrable por máquina y/o variable. Sin filtros = estadísticas globales.

        Returns dict con:
            total_alertas, con_feedback, cobertura_feedback,
            tasa_utiles, tasa_falsos, score_promedio
        """
        alertas = self._leer_historial()

        if id_maquina:
            alertas = [a for a in alertas if str(a.get("id_maquina", "")) == str(id_maquina)]
        if variable:
            alertas = [a for a in alertas if a.get("variable", "") == variable]

        total       = len(alertas)
        evaluadas   = [a for a in alertas if a.get("feedback_operario", "").strip()]
        n_evaluadas = len(evaluadas)

        utiles   = sum(1 for a in evaluadas if a.get("feedback_operario", "").upper() == "UTIL")
        falsos   = sum(1 for a in evaluadas if a.get("feedback_operario", "").upper() == "FALSO_POSITIVO")
        mecanicos = sum(1 for a in evaluadas if a.get("feedback_operario", "").upper() == "FALLA_MECANICA")

        scores = [
            REWARD_SCORES.get(a.get("feedback_operario", "").upper(), 0.0)
            for a in evaluadas
        ]
        score_promedio = round(sum(scores) / n_evaluadas, 3) if n_evaluadas else 0.0

        return {
            "total_alertas":     total,
            "con_feedback":      n_evaluadas,
            "sin_feedback":      total - n_evaluadas,
            "cobertura_feedback": round(n_evaluadas / total, 3) if total else 0.0,
            "utiles":            utiles,
            "falsos_positivos":  falsos,
            "mecanicos":         mecanicos,
            "tasa_utiles":       round(utiles / n_evaluadas, 3) if n_evaluadas else 0.0,
            "tasa_falsos":       round(falsos / n_evaluadas, 3) if n_evaluadas else 0.0,
            "score_promedio":    score_promedio,
        }
