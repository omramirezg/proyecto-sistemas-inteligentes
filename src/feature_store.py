"""Feature Store para enriquecimiento de telemetria en tiempo real.

Calcula features derivados de los sensores (tasas de cambio, tendencias,
correlaciones, estado combinado) y genera un bloque de texto listo para
inyectar en el prompt de Gemini. Esto permite que el LLM razone sobre
la dinamica temporal, no solo sobre valores puntuales.

Capas de analisis:
  1. Features individuales por variable (tasa, tendencia, sigma, tiempo fuera de banda)
  2. Matriz 3x3 de estado combinado temperatura x presion
  3. Correlaciones cruzadas entre variables
  4. Bloque de prompt enriquecido para Gemini
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses de salida
# ---------------------------------------------------------------------------

@dataclass
class FeatureVariable:
    """Features calculados para una variable individual."""
    nombre: str
    valor_actual: float
    unidad: str
    estado_banda: str              # BAJO | EN_BANDA | ALTO
    limite_min: float
    limite_max: float
    tasa_cambio: float             # unidad/min
    tasa_cambio_label: str         # CAYENDO RAPIDO | CAYENDO | ESTABLE | SUBIENDO | SUBIENDO RAPIDO
    tendencia: str                 # DESCENDENTE | ESTABLE | ASCENDENTE | OSCILANDO
    media_ventana: float
    min_ventana: float
    max_ventana: float
    std_ventana: float
    desviacion_sigma: float        # cuantas sigmas del centro de banda
    tiempo_fuera_banda_seg: float  # segundos fuera de banda
    n_lecturas: int


@dataclass
class EstadoCombinado:
    """Estado de la matriz 3x3 temperatura x presion."""
    cuadrante: str                 # ej: TEMP_BAJA__PRESION_ALTA
    diagnostico: str               # descripcion tecnica del cuadrante
    causas_probables: list[str]    # lista de causas posibles
    severidad: str                 # BAJA | MEDIA | ALTA | CRITICA
    tiempo_en_cuadrante_seg: float


@dataclass
class Correlacion:
    """Correlacion entre dos variables."""
    variable_a: str
    variable_b: str
    valor: float                   # coeficiente Pearson
    valor_normal: float            # valor esperado en condiciones normales
    estado: str                    # NORMAL | ANOMALA
    interpretacion: str


@dataclass
class FeatureStoreSnapshot:
    """Snapshot completo de todos los features en un instante."""
    features: dict[str, FeatureVariable]
    estado_combinado: EstadoCombinado
    correlaciones: list[Correlacion]
    anomalia_global: float         # 0.0 (normal) a 1.0 (muy anomalo)
    bloque_prompt: str             # texto listo para Gemini


# ---------------------------------------------------------------------------
# Matriz 3x3 de diagnostico
# ---------------------------------------------------------------------------

_MATRIZ_DIAGNOSTICO: dict[str, dict[str, Any]] = {
    "TEMP_BAJA__PRESION_BAJA": {
        "diagnostico": "Deficit de vapor generalizado. Suministro insuficiente o valvula principal cerrada.",
        "causas": ["falla suministro de vapor", "valvula Fisher V150 cerrada", "caldera fuera de servicio"],
        "severidad": "ALTA",
    },
    "TEMP_BAJA__PRESION_EN_BANDA": {
        "diagnostico": "Vapor llega con presion adecuada pero no transfiere calor. Trampa bloqueada o intercambiador con incrustaciones.",
        "causas": ["trampa TD42 bloqueada", "intercambiador incrustado", "condensado acumulado"],
        "severidad": "ALTA",
    },
    "TEMP_BAJA__PRESION_ALTA": {
        "diagnostico": "Exceso de vapor que NO transfiere energia termica. Intercambiador incrustado o trampa cerrada con condensado atrapado.",
        "causas": ["intercambiador con incrustaciones de carbonato", "trampa TD42 cerrada", "bypass de condensado abierto"],
        "severidad": "ALTA",
    },
    "TEMP_EN_BANDA__PRESION_BAJA": {
        "diagnostico": "Temperatura compensada por motor a costa de mayor corriente. Desgaste mecanico acelerado.",
        "causas": ["regulador Spirax 25P descalibrado", "valvula parcialmente cerrada", "compensacion por friccion"],
        "severidad": "MEDIA",
    },
    "TEMP_EN_BANDA__PRESION_EN_BANDA": {
        "diagnostico": "Operacion dentro de parametros normales.",
        "causas": [],
        "severidad": "BAJA",
    },
    "TEMP_EN_BANDA__PRESION_ALTA": {
        "diagnostico": "Vapor en exceso pero temperatura controlada. Regulador Spirax 25P descalibrado por encima.",
        "causas": ["regulador descalibrado", "valvula de alivio no actua"],
        "severidad": "MEDIA",
    },
    "TEMP_ALTA__PRESION_BAJA": {
        "diagnostico": "Sin vapor pero sobrecalentando. Friccion mecanica excesiva en dados o rodillos.",
        "causas": ["dado taponado parcialmente", "rodillos desalineados", "materia prima compactada"],
        "severidad": "CRITICA",
    },
    "TEMP_ALTA__PRESION_EN_BANDA": {
        "diagnostico": "Sobrecarga termica con vapor normal. Exceso de carga o materia prima con alto contenido energetico.",
        "causas": ["exceso de alimentacion", "formula incorrecta", "materia prima fuera de especificacion"],
        "severidad": "ALTA",
    },
    "TEMP_ALTA__PRESION_ALTA": {
        "diagnostico": "Exceso total de energia termica. Valvula de vapor abierta de mas y/o regulador desbocado.",
        "causas": ["valvula Fisher V150 abierta al 100%", "regulador Spirax 25P desbocado", "falla de control automatico"],
        "severidad": "CRITICA",
    },
}

# Correlaciones esperadas en condiciones normales
_CORRELACIONES_NORMALES = {
    ("temp_acond", "presion_vapor"): {"valor_normal": 0.85, "umbral_anomalia": 0.50},
    ("temp_acond", "corriente"):     {"valor_normal": 0.60, "umbral_anomalia": 0.25},
    ("presion_vapor", "corriente"):  {"valor_normal": 0.40, "umbral_anomalia": 0.10},
}

# Umbrales de tasa de cambio para clasificacion
_TASA_LABELS = {
    "temp_acond":     {"rapido": 3.0, "lento": 0.5},   # °C/min
    "presion_vapor":  {"rapido": 1.5, "lento": 0.3},   # PSI/min
    "corriente":      {"rapido": 20.0, "lento": 5.0},   # A/min
}


# ---------------------------------------------------------------------------
# Feature Store
# ---------------------------------------------------------------------------

class FeatureStore:
    """Almacen de features derivados en tiempo real.

    Mantiene un buffer circular de lecturas y recalcula features
    incrementalmente con cada nueva lectura.
    """

    def __init__(self, ventana: int = 30):
        self._ventana = ventana
        self._buffer: deque[dict[str, Any]] = deque(maxlen=ventana)
        self._timestamps: deque[float] = deque(maxlen=ventana)

        # Limites de la formula actual (se actualizan dinamicamente)
        self._t_min: float = 80.0
        self._t_max: float = 280.0
        self._p_min: float = 8.0
        self._p_max: float = 25.0
        self._capacidad_nominal: float = 500.0

        # Tracking de cuadrante para tiempo en estado
        self._cuadrante_actual: Optional[str] = None
        self._ts_inicio_cuadrante: float = 0.0

        # Tracking de tiempo fuera de banda por variable
        self._ts_fuera_banda: dict[str, float] = {}

        logger.info(
            "[FEATURE_STORE] Iniciado — ventana=%d lecturas",
            ventana,
        )

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    def actualizar_limites(
        self,
        t_min: float, t_max: float,
        p_min: float, p_max: float,
        capacidad_nominal: float = 500.0,
    ) -> None:
        """Actualiza los limites de banda cuando cambia la formula."""
        self._t_min = t_min
        self._t_max = t_max
        self._p_min = p_min
        self._p_max = p_max
        self._capacidad_nominal = capacidad_nominal

    def agregar_lectura(self, lectura: dict[str, Any]) -> None:
        """Agrega una lectura al buffer y actualiza tracking."""
        self._buffer.append(lectura)
        self._timestamps.append(time.time())

        # Actualizar limites desde la lectura si vienen incluidos
        if 't_min' in lectura:
            self.actualizar_limites(
                t_min=float(lectura['t_min']),
                t_max=float(lectura['t_max']),
                p_min=float(lectura['p_min']),
                p_max=float(lectura['p_max']),
                capacidad_nominal=float(lectura.get('capacidad_nominal', self._capacidad_nominal)),
            )

        # Actualizar tracking de fuera de banda
        self._actualizar_tracking_fuera_banda(lectura)

    def calcular(self) -> Optional[FeatureStoreSnapshot]:
        """Calcula el snapshot completo de features.

        Retorna None si no hay suficientes datos (minimo 3 lecturas).
        """
        if len(self._buffer) < 3:
            return None

        # Capa 1: Features individuales
        features = {}
        for var_name, var_key, unidad, lim_min, lim_max in [
            ("Temperatura", "temp_ema", "C",   self._t_min, self._t_max),
            ("Presion",     "presion_ema", "PSI", self._p_min, self._p_max),
            ("Corriente",   "corriente_ema", "A",  0.0, self._capacidad_nominal),
        ]:
            feat = self._calcular_features_variable(
                var_key, var_name, unidad, lim_min, lim_max,
            )
            if feat:
                features[var_key] = feat

        if not features:
            return None

        # Capa 2: Matriz 3x3
        estado_combinado = self._calcular_estado_combinado(features)

        # Capa 3: Correlaciones
        correlaciones = self._calcular_correlaciones()

        # Anomalia global
        anomalia = self._calcular_anomalia_global(features, estado_combinado, correlaciones)

        # Capa 4: Bloque de prompt
        bloque = self._construir_bloque_prompt(features, estado_combinado, correlaciones, anomalia)

        snapshot = FeatureStoreSnapshot(
            features=features,
            estado_combinado=estado_combinado,
            correlaciones=correlaciones,
            anomalia_global=anomalia,
            bloque_prompt=bloque,
        )

        logger.debug(
            "[FEATURE_STORE] Snapshot calculado — cuadrante=%s | anomalia=%.2f | lecturas=%d",
            estado_combinado.cuadrante,
            anomalia,
            len(self._buffer),
        )

        return snapshot

    def construir_bloque_prompt(self) -> str:
        """Atajo: calcula y retorna solo el bloque de texto para el prompt."""
        snapshot = self.calcular()
        if not snapshot:
            return ""
        return snapshot.bloque_prompt

    # ------------------------------------------------------------------
    # Capa 1: Features individuales
    # ------------------------------------------------------------------

    def _calcular_features_variable(
        self,
        var_key: str,
        nombre: str,
        unidad: str,
        lim_min: float,
        lim_max: float,
    ) -> Optional[FeatureVariable]:
        """Calcula features para una variable individual."""
        valores = []
        for lectura in self._buffer:
            v = lectura.get(var_key)
            if v is not None:
                valores.append(float(v))

        if len(valores) < 3:
            return None

        arr = np.array(valores)
        valor_actual = arr[-1]
        n = len(arr)

        # Estado de banda
        if valor_actual < lim_min:
            estado_banda = "BAJO"
        elif valor_actual > lim_max:
            estado_banda = "ALTO"
        else:
            estado_banda = "EN_BANDA"

        # Tasa de cambio (unidad/min) usando ultimas 5 lecturas
        tasa = self._calcular_tasa_cambio(var_key)

        # Label de tasa
        umbrales = _TASA_LABELS.get(var_key, {"rapido": 5.0, "lento": 1.0})
        abs_tasa = abs(tasa)
        if abs_tasa > umbrales["rapido"]:
            tasa_label = "CAYENDO RAPIDO" if tasa < 0 else "SUBIENDO RAPIDO"
        elif abs_tasa > umbrales["lento"]:
            tasa_label = "CAYENDO" if tasa < 0 else "SUBIENDO"
        else:
            tasa_label = "ESTABLE"

        # Tendencia (ultimas 10 lecturas)
        tendencia = self._calcular_tendencia(arr[-min(10, n):])

        # Estadisticas de ventana
        media = float(np.mean(arr))
        std = float(np.std(arr)) if n > 1 else 0.0

        # Desviacion sigma respecto al centro de banda
        centro_banda = (lim_min + lim_max) / 2.0
        rango_banda = (lim_max - lim_min) / 2.0
        if rango_banda > 0:
            desviacion_sigma = (valor_actual - centro_banda) / rango_banda * 2.0
        else:
            desviacion_sigma = 0.0

        # Tiempo fuera de banda
        tiempo_fuera = 0.0
        if estado_banda != "EN_BANDA" and var_key in self._ts_fuera_banda:
            tiempo_fuera = time.time() - self._ts_fuera_banda[var_key]

        return FeatureVariable(
            nombre=nombre,
            valor_actual=valor_actual,
            unidad=unidad,
            estado_banda=estado_banda,
            limite_min=lim_min,
            limite_max=lim_max,
            tasa_cambio=tasa,
            tasa_cambio_label=tasa_label,
            tendencia=tendencia,
            media_ventana=media,
            min_ventana=float(np.min(arr)),
            max_ventana=float(np.max(arr)),
            std_ventana=std,
            desviacion_sigma=desviacion_sigma,
            tiempo_fuera_banda_seg=tiempo_fuera,
            n_lecturas=n,
        )

    def _calcular_tasa_cambio(self, var_key: str) -> float:
        """Calcula tasa de cambio en unidad/min usando regresion lineal."""
        valores = []
        tiempos = []
        for lec, ts in zip(self._buffer, self._timestamps):
            v = lec.get(var_key)
            if v is not None:
                valores.append(float(v))
                tiempos.append(ts)

        if len(valores) < 3:
            return 0.0

        # Usar ultimas 5 para tasa reciente
        n_recientes = min(5, len(valores))
        vals = np.array(valores[-n_recientes:])
        ts = np.array(tiempos[-n_recientes:])

        # Regresion lineal: pendiente en unidad/segundo → convertir a /minuto
        dt = ts - ts[0]
        if dt[-1] == 0:
            return 0.0

        try:
            pendiente = np.polyfit(dt, vals, 1)[0]
            return float(pendiente * 60.0)  # unidad/minuto
        except (np.linalg.LinAlgError, ValueError):
            return 0.0

    def _calcular_tendencia(self, arr: np.ndarray) -> str:
        """Clasifica la tendencia de un array de valores."""
        if len(arr) < 3:
            return "INSUFICIENTE"

        # Calcular cambios consecutivos
        diffs = np.diff(arr)
        positivos = np.sum(diffs > 0)
        negativos = np.sum(diffs < 0)
        total = len(diffs)

        if total == 0:
            return "ESTABLE"

        ratio_pos = positivos / total
        ratio_neg = negativos / total

        # Detectar oscilacion: muchos cambios de signo
        cambios_signo = np.sum(np.diff(np.sign(diffs)) != 0)
        if total > 3 and cambios_signo / (total - 1) > 0.6:
            return "OSCILANDO"

        if ratio_neg > 0.65:
            return "DESCENDENTE"
        elif ratio_pos > 0.65:
            return "ASCENDENTE"
        else:
            return "ESTABLE"

    # ------------------------------------------------------------------
    # Capa 2: Matriz 3x3
    # ------------------------------------------------------------------

    def _calcular_estado_combinado(
        self, features: dict[str, FeatureVariable],
    ) -> EstadoCombinado:
        """Determina el cuadrante de la matriz 3x3."""
        f_temp = features.get("temp_ema")
        f_pres = features.get("presion_ema")

        if not f_temp or not f_pres:
            return EstadoCombinado(
                cuadrante="INDETERMINADO",
                diagnostico="Datos insuficientes para determinar estado combinado.",
                causas_probables=[],
                severidad="BAJA",
                tiempo_en_cuadrante_seg=0.0,
            )

        # Construir clave de cuadrante
        mapa_estado = {"BAJO": "BAJA", "EN_BANDA": "EN_BANDA", "ALTO": "ALTA"}
        estado_t = mapa_estado.get(f_temp.estado_banda, "EN_BANDA")
        estado_p = mapa_estado.get(f_pres.estado_banda, "EN_BANDA")

        clave = f"TEMP_{estado_t}__PRESION_{estado_p}"

        # Buscar en la matriz
        info = _MATRIZ_DIAGNOSTICO.get(clave)
        if not info:
            # Fallback por si la clave no coincide exactamente
            clave_normalizada = f"TEMP_{f_temp.estado_banda}__PRESION_{f_pres.estado_banda}"
            info = _MATRIZ_DIAGNOSTICO.get(clave_normalizada, {
                "diagnostico": f"Estado combinado: temperatura {f_temp.estado_banda}, presion {f_pres.estado_banda}.",
                "causas": [],
                "severidad": "MEDIA",
            })

        # Tiempo en este cuadrante
        ahora = time.time()
        if clave != self._cuadrante_actual:
            self._cuadrante_actual = clave
            self._ts_inicio_cuadrante = ahora

        tiempo_en_cuadrante = ahora - self._ts_inicio_cuadrante

        return EstadoCombinado(
            cuadrante=clave,
            diagnostico=info["diagnostico"],
            causas_probables=info["causas"],
            severidad=info["severidad"],
            tiempo_en_cuadrante_seg=tiempo_en_cuadrante,
        )

    # ------------------------------------------------------------------
    # Capa 3: Correlaciones
    # ------------------------------------------------------------------

    def _calcular_correlaciones(self) -> list[Correlacion]:
        """Calcula correlaciones cruzadas entre variables."""
        correlaciones = []

        for (var_a, var_b), info in _CORRELACIONES_NORMALES.items():
            valores_a = []
            valores_b = []

            for lectura in self._buffer:
                va = lectura.get(var_a)
                vb = lectura.get(var_b)
                if va is not None and vb is not None:
                    valores_a.append(float(va))
                    valores_b.append(float(vb))

            if len(valores_a) < 5:
                continue

            arr_a = np.array(valores_a)
            arr_b = np.array(valores_b)

            # Coeficiente de Pearson
            try:
                std_a = np.std(arr_a)
                std_b = np.std(arr_b)
                if std_a < 1e-10 or std_b < 1e-10:
                    coef = 0.0
                else:
                    coef = float(np.corrcoef(arr_a, arr_b)[0, 1])
                    if np.isnan(coef):
                        coef = 0.0
            except (ValueError, FloatingPointError):
                coef = 0.0

            valor_normal = info["valor_normal"]
            umbral = info["umbral_anomalia"]

            es_anomala = abs(coef - valor_normal) > (valor_normal - umbral)

            # Interpretacion contextual
            nombre_a = "temperatura" if "temp" in var_a else "presion" if "pres" in var_a else "corriente"
            nombre_b = "temperatura" if "temp" in var_b else "presion" if "pres" in var_b else "corriente"

            if es_anomala:
                if coef < 0 and valor_normal > 0:
                    interp = f"{nombre_a} y {nombre_b} se mueven en direcciones opuestas (esperado: misma direccion)."
                elif abs(coef) < 0.2 and valor_normal > 0.5:
                    interp = f"{nombre_a} y {nombre_b} estan desacopladas (esperado: correlacion {valor_normal:.2f})."
                else:
                    interp = f"Correlacion {nombre_a}-{nombre_b} anomala: {coef:.2f} vs esperado {valor_normal:.2f}."
            else:
                interp = f"Correlacion {nombre_a}-{nombre_b} dentro de rango normal."

            correlaciones.append(Correlacion(
                variable_a=var_a,
                variable_b=var_b,
                valor=coef,
                valor_normal=valor_normal,
                estado="ANOMALA" if es_anomala else "NORMAL",
                interpretacion=interp,
            ))

        return correlaciones

    # ------------------------------------------------------------------
    # Anomalia global
    # ------------------------------------------------------------------

    def _calcular_anomalia_global(
        self,
        features: dict[str, FeatureVariable],
        estado: EstadoCombinado,
        correlaciones: list[Correlacion],
    ) -> float:
        """Score de anomalia global de 0.0 (normal) a 1.0 (muy anomalo)."""
        scores = []

        # Score por variables fuera de banda
        for feat in features.values():
            if feat.estado_banda == "EN_BANDA":
                scores.append(0.0)
            else:
                # Mas lejos del limite = mas anomalo
                sigma_score = min(abs(feat.desviacion_sigma) / 4.0, 1.0)
                scores.append(sigma_score)

        # Score por severidad del cuadrante
        sev_map = {"BAJA": 0.0, "MEDIA": 0.3, "ALTA": 0.7, "CRITICA": 1.0}
        scores.append(sev_map.get(estado.severidad, 0.0))

        # Score por correlaciones anomalas
        n_anomalas = sum(1 for c in correlaciones if c.estado == "ANOMALA")
        n_total = max(len(correlaciones), 1)
        scores.append(n_anomalas / n_total)

        if not scores:
            return 0.0

        # Promedio ponderado (severidad cuadrante pesa mas)
        return float(np.clip(np.mean(scores), 0.0, 1.0))

    # ------------------------------------------------------------------
    # Tracking auxiliar
    # ------------------------------------------------------------------

    def _actualizar_tracking_fuera_banda(self, lectura: dict[str, Any]) -> None:
        """Actualiza timestamps de cuando cada variable salio de banda."""
        ahora = time.time()

        for var_key, lim_min, lim_max in [
            ("temp_ema",     self._t_min, self._t_max),
            ("presion_ema",  self._p_min, self._p_max),
        ]:
            valor = lectura.get(var_key)
            if valor is None:
                continue

            valor = float(valor)
            fuera = valor < lim_min or valor > lim_max

            if fuera and var_key not in self._ts_fuera_banda:
                self._ts_fuera_banda[var_key] = ahora
            elif not fuera and var_key in self._ts_fuera_banda:
                del self._ts_fuera_banda[var_key]

    # ------------------------------------------------------------------
    # Capa 4: Generacion de prompt
    # ------------------------------------------------------------------

    def _construir_bloque_prompt(
        self,
        features: dict[str, FeatureVariable],
        estado: EstadoCombinado,
        correlaciones: list[Correlacion],
        anomalia: float,
    ) -> str:
        """Genera el bloque de texto enriquecido para inyectar en el prompt."""
        lineas = []
        lineas.append("=== ANALISIS DE FEATURES (Feature Store) ===")
        lineas.append("")

        # Estado combinado
        tiempo_cuad = self._formatear_tiempo(estado.tiempo_en_cuadrante_seg)
        lineas.append(f"ESTADO COMBINADO: {estado.cuadrante} ({tiempo_cuad} en este estado)")
        lineas.append(f"Diagnostico diferencial: {estado.diagnostico}")
        if estado.causas_probables:
            lineas.append(f"Causas probables: {', '.join(estado.causas_probables)}.")
        lineas.append(f"Severidad calculada: {estado.severidad}")
        lineas.append("")

        # Features por variable
        for var_key in ["temp_ema", "presion_ema", "corriente_ema"]:
            feat = features.get(var_key)
            if not feat:
                continue

            tiempo_fuera = ""
            if feat.tiempo_fuera_banda_seg > 0:
                tiempo_fuera = f" | Fuera de banda hace: {self._formatear_tiempo(feat.tiempo_fuera_banda_seg)}"

            lineas.append(
                f"{feat.nombre.upper()}: {feat.valor_actual:.1f} {feat.unidad} [{feat.estado_banda}]"
                f" (banda: {feat.limite_min:.1f}-{feat.limite_max:.1f})"
            )
            lineas.append(
                f"  Tasa: {feat.tasa_cambio:+.2f} {feat.unidad}/min ({feat.tasa_cambio_label})"
                f" | Tendencia: {feat.tendencia}"
            )
            lineas.append(
                f"  Ventana: min={feat.min_ventana:.1f} | max={feat.max_ventana:.1f}"
                f" | media={feat.media_ventana:.1f} | sigma={feat.desviacion_sigma:+.1f}"
                f"{tiempo_fuera}"
            )
            lineas.append("")

        # Correlaciones
        anomalas = [c for c in correlaciones if c.estado == "ANOMALA"]
        normales = [c for c in correlaciones if c.estado == "NORMAL"]

        if anomalas:
            lineas.append("CORRELACIONES ANOMALAS:")
            for c in anomalas:
                lineas.append(
                    f"  {c.variable_a} <-> {c.variable_b}: {c.valor:.2f}"
                    f" (esperado: {c.valor_normal:.2f}) — {c.interpretacion}"
                )
            lineas.append("")

        if normales:
            lineas.append("CORRELACIONES NORMALES:")
            for c in normales:
                lineas.append(
                    f"  {c.variable_a} <-> {c.variable_b}: {c.valor:.2f} (OK)"
                )
            lineas.append("")

        # Anomalia global
        nivel = "NORMAL" if anomalia < 0.25 else "ELEVADA" if anomalia < 0.5 else "ALTA" if anomalia < 0.75 else "MUY ANOMALO"
        lineas.append(f"ANOMALIA GLOBAL: {anomalia:.2f}/1.00 — {nivel}")
        lineas.append("=" * 50)

        return "\n".join(lineas)

    @staticmethod
    def _formatear_tiempo(segundos: float) -> str:
        """Formatea segundos a formato legible."""
        if segundos < 60:
            return f"{segundos:.0f} seg"
        minutos = int(segundos // 60)
        seg = int(segundos % 60)
        if minutos < 60:
            return f"{minutos} min {seg} seg"
        horas = int(minutos // 60)
        mins = int(minutos % 60)
        return f"{horas}h {mins}min"
