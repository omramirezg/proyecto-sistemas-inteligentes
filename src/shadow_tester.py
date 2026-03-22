"""
Shadow Mode / A/B Testing
==========================
Orquesta experimentos controlados sobre el sistema de prescripción IA,
permitiendo comparar dos variantes del LLM en producción real sin riesgo.

Modos disponibles:
    off    → sistema normal, solo variante A (sin overhead)
    shadow → A llega al operario, B corre en paralelo en silencio
    ab     → tráfico dividido según SHADOW_PORCENTAJE_B (ej: 20% va a B)

Flujo en modo shadow:
    Alerta → [A en paralelo con B]
                ├─ Prescripción A → operario (visible)
                └─ Prescripción B → log (invisible)
    Operario evalúa → feedback registrado con variante que recibió
    Análisis → compara tasa UTIL y FALSO_POSITIVO entre variantes

Flujo en modo ab:
    Alerta → dado de 0-100
                ├─ < SHADOW_PORCENTAJE_B → operario recibe B
                └─ >= SHADOW_PORCENTAJE_B → operario recibe A
    Ambas respuestas quedan en el log para análisis posterior

Registro:
    data/shadow_log.csv — cada fila es una alerta con respuesta A y B,
    variante mostrada, tiempos de respuesta y diferencia de longitud.
    Este CSV es la base para decidir si desplegar la variante B.
"""

import csv
import hashlib
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

from llm_multimodal import VarianteParams

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_MODO_OFF    = "off"
_MODO_SHADOW = "shadow"
_MODO_AB     = "ab"
_MODOS_VALIDOS = {_MODO_OFF, _MODO_SHADOW, _MODO_AB}


class ShadowTester:
    """
    Motor de A/B testing para el sistema de prescripción IA.

    Uso típico:
        tester = ShadowTester(llm_provider, config)

        prescripcion, variante = tester.generar_con_shadow(
            prompt_texto=prompt,
            herramientas=herramientas,
            imagen_bytes=imagen,
            feedback_loop=feedback_loop,
            id_maquina="301",
            variable="presion_vapor",
            alerta_id=42,
        )
        # 'prescripcion' es la que va al operario
        # 'variante' es "A" o "B" — registrar junto al feedback
    """

    def __init__(self, llm_provider, config) -> None:
        self.llm    = llm_provider
        self.config = config
        self._lock  = threading.Lock()
        self._total_a   = 0
        self._total_b   = 0

        modo = config.shadow_modo
        if modo not in _MODOS_VALIDOS:
            logger.warning(
                "[A/B] Modo '%s' inválido. Usando 'off'.", modo
            )

        logger.info(
            "[A/B] ShadowTester iniciado. Modo: %s | Modelo B: %s | "
            "Temperatura B: %.2f | Porcentaje B: %d%%",
            config.shadow_modo,
            config.shadow_modelo_b,
            config.shadow_temperatura_b,
            config.shadow_porcentaje_b,
        )

    # -----------------------------------------------------------------------
    # Punto de entrada principal
    # -----------------------------------------------------------------------

    def generar_con_shadow(
        self,
        prompt_texto: str,
        herramientas,
        imagen_bytes: Optional[bytes] = None,
        video_bytes:  Optional[bytes] = None,
        feedback_loop=None,
        id_maquina: Optional[str] = None,
        variable: Optional[str] = None,
        alerta_id: Optional[int] = None,
    ) -> tuple[str, str]:
        """
        Genera la prescripción final según el modo configurado.

        Returns:
            (prescripcion_final, variante_asignada)
            variante_asignada es "A" o "B" — debe registrarse junto al feedback
            para poder atribuir el resultado al experimento correcto.
        """
        modo = self.config.shadow_modo

        # Modo off — cero overhead, comportamiento idéntico al sistema original
        if modo == _MODO_OFF:
            prescripcion = self.llm.diagnosticar_con_herramientas(
                prompt_texto=prompt_texto,
                herramientas=herramientas,
                imagen_bytes=imagen_bytes,
                video_bytes=video_bytes,
                feedback_loop=feedback_loop,
                id_maquina=id_maquina,
                variable=variable,
            )
            return prescripcion, "A"

        # Construir params de la variante B
        params_b = self._construir_params_b()

        # Determinar qué variante verá el operario
        if modo == _MODO_SHADOW:
            variante_mostrada = "A"                   # B siempre silenciosa
        else:
            variante_mostrada = self._sortear_variante()

        # Correr A y B en paralelo para no multiplicar latencia
        t0 = time.time()
        resultados: dict[str, str] = {}
        tiempos:    dict[str, float] = {}
        errores:    dict[str, str] = {}

        def correr(variante: str, params: Optional[VarianteParams]) -> None:
            ts = time.time()
            try:
                r = self.llm.diagnosticar_con_herramientas(
                    prompt_texto=prompt_texto,
                    herramientas=herramientas,
                    imagen_bytes=imagen_bytes,
                    video_bytes=video_bytes,
                    feedback_loop=feedback_loop,
                    id_maquina=id_maquina,
                    variable=variable,
                    variante_params=params,
                )
                resultados[variante] = r or ""
            except Exception as e:
                logger.error("[A/B] Variante %s falló: %s", variante, e)
                errores[variante] = str(e)
                resultados[variante] = ""
            tiempos[variante] = round((time.time() - ts) * 1000)   # ms

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="shadow") as ex:
            futuros = {
                ex.submit(correr, "A", None):      "A",
                ex.submit(correr, "B", params_b):  "B",
            }
            for f in as_completed(futuros):
                f.result()   # re-raise si hay excepción no capturada

        tiempo_total_ms = round((time.time() - t0) * 1000)

        # Registrar en log
        self._registrar(
            alerta_id=alerta_id,
            id_maquina=id_maquina,
            variable=variable,
            variante_mostrada=variante_mostrada,
            prescripcion_a=resultados.get("A", ""),
            prescripcion_b=resultados.get("B", ""),
            tiempo_a_ms=tiempos.get("A", 0),
            tiempo_b_ms=tiempos.get("B", 0),
            tiempo_total_ms=tiempo_total_ms,
            error_a=errores.get("A", ""),
            error_b=errores.get("B", ""),
        )

        # Contadores internos
        with self._lock:
            if variante_mostrada == "A":
                self._total_a += 1
            else:
                self._total_b += 1

        # Devolver la prescripción de la variante asignada (fallback a A)
        prescripcion_final = (
            resultados.get(variante_mostrada)
            or resultados.get("A")
            or ""
        )

        logger.info(
            "[A/B] Alerta #%s → Variante %s mostrada | A: %dms %dchars | "
            "B: %dms %dchars | Total: %dms",
            alerta_id,
            variante_mostrada,
            tiempos.get("A", 0), len(resultados.get("A", "")),
            tiempos.get("B", 0), len(resultados.get("B", "")),
            tiempo_total_ms,
        )

        return prescripcion_final, variante_mostrada

    # -----------------------------------------------------------------------
    # Análisis de resultados
    # -----------------------------------------------------------------------

    def analizar_resultados(self, ventana_dias: int = 7) -> dict:
        """
        Lee el shadow_log.csv y calcula métricas comparativas entre variantes.
        Combina el log con el historial de feedback para calcular tasas de éxito.

        Returns dict con:
            total_a, total_b, porcentaje_b_real,
            tasa_util_a, tasa_util_b, tasa_falso_a, tasa_falso_b,
            diferencia_longitud_promedio, latencia_a_promedio, latencia_b_promedio,
            recomendacion: "DESPLEGAR_B" | "MANTENER_A" | "INSUFICIENTE"
        """
        log_path = self.config.data_dir / "shadow_log.csv"
        alertas_path = self.config.data_dir / "historial_alertas.csv"

        if not log_path.exists():
            return {"error": "shadow_log.csv no encontrado. No hay experimentos registrados."}

        from datetime import timedelta
        corte = (datetime.now() - timedelta(days=ventana_dias)).isoformat()

        # Leer log de shadow
        filas_log = []
        try:
            with log_path.open(encoding="utf-8") as f:
                for fila in csv.DictReader(f):
                    if fila.get("timestamp", "") >= corte:
                        filas_log.append(fila)
        except Exception as e:
            return {"error": f"Error leyendo shadow_log.csv: {e}"}

        if not filas_log:
            return {"error": f"Sin datos en los últimos {ventana_dias} días."}

        # Leer feedback del historial de alertas
        feedback_por_alerta: dict[str, str] = {}
        if alertas_path.exists():
            try:
                with alertas_path.open(encoding="utf-8") as f:
                    for fila in csv.DictReader(f):
                        alerta_id = str(fila.get("id", ""))
                        fb = fila.get("feedback_operario", "").strip().upper()
                        if alerta_id and fb:
                            feedback_por_alerta[alerta_id] = fb
            except Exception:
                pass

        # Calcular métricas
        stats: dict[str, dict] = {
            "A": {"total": 0, "util": 0, "falso": 0, "latencias": [], "longitudes": []},
            "B": {"total": 0, "util": 0, "falso": 0, "latencias": [], "longitudes": []},
        }

        for fila in filas_log:
            v = fila.get("variante_mostrada", "A")
            if v not in stats:
                continue
            stats[v]["total"] += 1

            alerta_id = str(fila.get("alerta_id", ""))
            fb = feedback_por_alerta.get(alerta_id, "")
            if fb == "UTIL":
                stats[v]["util"] += 1
            elif fb == "FALSO_POSITIVO":
                stats[v]["falso"] += 1

            try:
                lat_key = f"tiempo_{v.lower()}_ms"
                stats[v]["latencias"].append(int(fila.get(lat_key, 0)))
            except ValueError:
                pass

            try:
                pres = fila.get(f"prescripcion_{v.lower()}", "")
                stats[v]["longitudes"].append(len(pres))
            except Exception:
                pass

        def tasa(n, total):
            return round(n / total, 3) if total else 0.0

        def promedio(lst):
            return round(sum(lst) / len(lst)) if lst else 0

        total_a = stats["A"]["total"]
        total_b = stats["B"]["total"]
        total   = total_a + total_b

        tasa_util_a  = tasa(stats["A"]["util"],  total_a)
        tasa_util_b  = tasa(stats["B"]["util"],  total_b)
        tasa_falso_a = tasa(stats["A"]["falso"], total_a)
        tasa_falso_b = tasa(stats["B"]["falso"], total_b)

        # Recomendación automática
        evaluadas_a = stats["A"]["util"] + stats["A"]["falso"]
        evaluadas_b = stats["B"]["util"] + stats["B"]["falso"]
        min_evaluadas = 20  # mínimo para recomendar con confianza

        if evaluadas_a < min_evaluadas or evaluadas_b < min_evaluadas:
            recomendacion = "INSUFICIENTE"
        elif tasa_util_b > tasa_util_a and tasa_falso_b < tasa_falso_a:
            recomendacion = "DESPLEGAR_B"
        elif tasa_util_a >= tasa_util_b:
            recomendacion = "MANTENER_A"
        else:
            recomendacion = "REVISAR_MANUAL"

        return {
            "ventana_dias":             ventana_dias,
            "total_alertas":            total,
            "total_a":                  total_a,
            "total_b":                  total_b,
            "porcentaje_b_real":        round(total_b / total * 100) if total else 0,
            "evaluadas_a":              evaluadas_a,
            "evaluadas_b":              evaluadas_b,
            "tasa_util_a":              tasa_util_a,
            "tasa_util_b":              tasa_util_b,
            "tasa_falso_a":             tasa_falso_a,
            "tasa_falso_b":             tasa_falso_b,
            "latencia_a_promedio_ms":   promedio(stats["A"]["latencias"]),
            "latencia_b_promedio_ms":   promedio(stats["B"]["latencias"]),
            "longitud_a_promedio":      promedio(stats["A"]["longitudes"]),
            "longitud_b_promedio":      promedio(stats["B"]["longitudes"]),
            "recomendacion":            recomendacion,
        }

    def resumen_consola(self) -> str:
        """Retorna un string legible con los resultados del experimento actual."""
        r = self.analizar_resultados()
        if "error" in r:
            return f"[A/B] {r['error']}"

        lineas = [
            f"[A/B] Resultados del experimento (últimos {r['ventana_dias']} días)",
            f"  Total alertas: {r['total_alertas']} | A: {r['total_a']} | B: {r['total_b']} ({r['porcentaje_b_real']}%)",
            f"  Tasa UTIL   → A: {r['tasa_util_a']*100:.1f}%  B: {r['tasa_util_b']*100:.1f}%",
            f"  Tasa FALSO  → A: {r['tasa_falso_a']*100:.1f}%  B: {r['tasa_falso_b']*100:.1f}%",
            f"  Latencia    → A: {r['latencia_a_promedio_ms']}ms  B: {r['latencia_b_promedio_ms']}ms",
            f"  Recomendación: {r['recomendacion']}",
        ]
        return "\n".join(lineas)

    # -----------------------------------------------------------------------
    # Helpers internos
    # -----------------------------------------------------------------------

    def _construir_params_b(self) -> VarianteParams:
        """Construye la VarianteParams para la variante B desde la config."""
        return VarianteParams(
            nombre="challenger",
            modelo=self.config.shadow_modelo_b or None,
            temperatura=self.config.shadow_temperatura_b,
            max_tokens=self.config.shadow_max_tokens_b,
            top_p=self.config.shadow_top_p_b,
            system_prompt_override=self.config.shadow_system_prompt_b or None,
        )

    def _sortear_variante(self) -> str:
        """Asigna variante al azar según el porcentaje configurado para B."""
        return "B" if random.random() * 100 < self.config.shadow_porcentaje_b else "A"

    def _registrar(
        self,
        alerta_id,
        id_maquina,
        variable,
        variante_mostrada,
        prescripcion_a,
        prescripcion_b,
        tiempo_a_ms,
        tiempo_b_ms,
        tiempo_total_ms,
        error_a,
        error_b,
    ) -> None:
        """Persiste una fila en data/shadow_log.csv (append-safe con lock)."""
        archivo = self.config.data_dir / "shadow_log.csv"
        campos = [
            "timestamp", "alerta_id", "id_maquina", "variable",
            "variante_mostrada", "modo",
            "prescripcion_a", "prescripcion_b",
            "longitud_a", "longitud_b", "diferencia_longitud",
            "tiempo_a_ms", "tiempo_b_ms", "tiempo_total_ms",
            "modelo_b", "temperatura_b",
            "error_a", "error_b",
        ]
        fila = {
            "timestamp":           datetime.now().isoformat(),
            "alerta_id":           alerta_id or "",
            "id_maquina":          id_maquina or "",
            "variable":            variable or "",
            "variante_mostrada":   variante_mostrada,
            "modo":                self.config.shadow_modo,
            "prescripcion_a":      (prescripcion_a or "")[:500],
            "prescripcion_b":      (prescripcion_b or "")[:500],
            "longitud_a":          len(prescripcion_a or ""),
            "longitud_b":          len(prescripcion_b or ""),
            "diferencia_longitud": len(prescripcion_a or "") - len(prescripcion_b or ""),
            "tiempo_a_ms":         tiempo_a_ms,
            "tiempo_b_ms":         tiempo_b_ms,
            "tiempo_total_ms":     tiempo_total_ms,
            "modelo_b":            self.config.shadow_modelo_b,
            "temperatura_b":       self.config.shadow_temperatura_b,
            "error_a":             error_a[:200] if error_a else "",
            "error_b":             error_b[:200] if error_b else "",
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
                logger.error("[A/B] Error escribiendo shadow_log.csv: %s", e)
