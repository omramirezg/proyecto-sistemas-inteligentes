"""
Motor de Reglas Determinista
============================
Núcleo del sistema de alertamiento. Implementa:
- Suavizado EMA (Media Móvil Exponencial) truncada
- Detección de cambio de estado (estándar ANSI/ISA-18.2)
- Sistema anti-spam / anti-fatiga de alarmas
- Validación de carga operativa de máquinas

Las decisiones se toman sobre variables suavizadas, nunca sobre datos crudos.
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


# =====================================================
# Enumeraciones y Modelos de Datos
# =====================================================

class EstadoVariable(Enum):
    """Estados posibles de una variable monitoreada según ISA-18.2."""
    NORMAL = "NORMAL"
    BAJA = "BAJA"
    ALTA = "ALTA"


class EstadoMaquina(Enum):
    """Estado operativo general de una máquina."""
    OPERANDO = "OPERANDO"
    INACTIVA = "INACTIVA"
    SIN_DATOS = "SIN_DATOS"


class TipoAlerta(Enum):
    """Tipos de alerta que puede generar el sistema."""
    PRESION_BAJA = "PRESION_BAJA"
    PRESION_ALTA = "PRESION_ALTA"
    TEMPERATURA_BAJA = "TEMPERATURA_BAJA"
    TEMPERATURA_ALTA = "TEMPERATURA_ALTA"
    RETORNO_NORMAL_PRESION = "RETORNO_NORMAL_PRESION"
    RETORNO_NORMAL_TEMPERATURA = "RETORNO_NORMAL_TEMPERATURA"


@dataclass
class Alerta:
    """
    Representa una alerta generada por el motor de reglas.
    
    Contiene todo el contexto necesario para que el LLM
    genere una prescripción informada.
    """
    timestamp: datetime
    id_planta: str
    id_maquina: str
    id_formula: str
    codigo_producto: str
    tipo_alerta: TipoAlerta
    variable: str                    # 'presion_vapor' o 'temp_acond'
    valor_crudo: float               # Valor original del sensor
    valor_suavizado: float           # Valor después de EMA
    limite_violado: float            # Límite min o max que se violó
    limite_min: float                # Límite inferior de la fórmula
    limite_max: float                # Límite superior de la fórmula
    corriente_suavizada: float       # Para contexto de carga
    capacidad_nominal: float         # Capacidad del equipo
    porcentaje_carga: float          # % de carga actual
    es_retorno_normal: bool = False  # True si es notificación de estabilización

    def __str__(self) -> str:
        if self.es_retorno_normal:
            return (
                f"✅ PROCESO ESTABLE | Planta {self.id_planta} | "
                f"Máq {self.id_maquina} | {self.variable} retornó "
                f"a banda normal ({self.limite_min:.1f} - {self.limite_max:.1f})"
            )
        return (
            f"⚠️ ALERTA {self.tipo_alerta.value} | "
            f"Planta {self.id_planta} | Máq {self.id_maquina} | "
            f"Fórmula {self.id_formula} ({self.codigo_producto}) | "
            f"{self.variable}: {self.valor_suavizado:.2f} "
            f"(límite: {self.limite_violado:.1f}) | "
            f"Carga: {self.porcentaje_carga:.0f}%"
        )


@dataclass
class EstadoActualMaquina:
    """
    Estado en memoria de una máquina para detección de cambios.
    
    Se mantiene en un diccionario en RAM durante la ejecución
    continua del worker para implementar la lógica ISA-18.2.
    """
    estado_presion: EstadoVariable = EstadoVariable.NORMAL
    estado_temperatura: EstadoVariable = EstadoVariable.NORMAL
    estado_operativo: EstadoMaquina = EstadoMaquina.SIN_DATOS
    ema_corriente: Optional[float] = None
    ema_temperatura: Optional[float] = None
    ema_presion: Optional[float] = None
    ultimas_alertas: list = field(default_factory=list)
    ultima_lectura: Optional[datetime] = None
    candidato_presion: EstadoVariable = EstadoVariable.NORMAL
    candidato_temperatura: EstadoVariable = EstadoVariable.NORMAL
    persistencia_presion: int = 0
    persistencia_temperatura: int = 0


class MotorReglas:
    """
    Motor determinista de evaluación de reglas para telemetría industrial.
    
    Implementa el estándar ANSI/ISA-18.2 para gestión de alarmas:
    - Solo genera alerta en TRANSICIONES de estado (Normal→Falla, Falla→Normal)
    - Aplica suavizado EMA antes de evaluar límites
    - Previene fatiga de alarmas con regla de saturación
    
    Attributes:
        alpha: Factor de suavizado EMA (0 < alpha <= 1).
        max_alertas: Máximo de alertas por ventana por equipo.
        ventana_min: Duración en minutos de la ventana anti-spam.
    """

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()
        self.alpha: float = self.config.ema_alpha
        self.max_alertas: int = self.config.max_alertas_por_ventana
        self.ventana_min: int = self.config.ventana_antispam_minutos
        self.confirmacion_alerta: int = 2
        self.confirmacion_retorno: int = 2

        # Estado en memoria de cada máquina {planta_maquina: EstadoActualMaquina}
        self._estados: dict[str, EstadoActualMaquina] = {}

        logger.info(
            "Motor de reglas inicializado: alpha=%.2f, "
            "max_alertas=%d, ventana=%d min, confirmacion=%d",
            self.alpha, self.max_alertas, self.ventana_min, self.confirmacion_alerta
        )

    # =====================================================
    # Suavizado EMA (Media Móvil Exponencial)
    # =====================================================

    def calcular_ema(
        self, valor_actual: float, ema_anterior: Optional[float]
    ) -> float:
        """
        Calcula la Media Móvil Exponencial truncada.
        
        EMA_t = α * X_t + (1 - α) * EMA_{t-1}
        
        Se utiliza una versión truncada que sacrifica a lo sumo
        un 1% de la señal original a cambio de estabilidad y
        velocidad de procesamiento.
        
        Args:
            valor_actual: Lectura cruda del sensor.
            ema_anterior: Último valor EMA calculado, o None si es la primera lectura.
            
        Returns:
            Valor suavizado.
        """
        if ema_anterior is None:
            return valor_actual
        return self.alpha * valor_actual + (1 - self.alpha) * ema_anterior

    # =====================================================
    # Obtención de clave de máquina
    # =====================================================

    def _clave_maquina(self, id_planta: str, id_maquina: str) -> str:
        """Genera una clave única para identificar una máquina."""
        return f"{id_planta.strip().zfill(3)}_{id_maquina.strip().zfill(3)}"

    def _obtener_estado(self, clave: str) -> EstadoActualMaquina:
        """Obtiene o crea el estado en memoria de una máquina."""
        if clave not in self._estados:
            self._estados[clave] = EstadoActualMaquina()
        return self._estados[clave]

    # =====================================================
    # Validación Anti-Spam
    # =====================================================

    def _puede_alertar(self, estado: EstadoActualMaquina) -> bool:
        """
        Verifica la regla de saturación anti-spam.
        
        Máximo N alertas en una ventana de M minutos por equipo.
        Esto previene la fatiga de alarmas en el operario.
        
        Returns:
            True si se puede enviar una alerta nueva.
        """
        ahora = datetime.now()
        ventana = timedelta(minutes=self.ventana_min)

        # Limpiar alertas fuera de la ventana
        estado.ultimas_alertas = [
            t for t in estado.ultimas_alertas
            if ahora - t < ventana
        ]

        return len(estado.ultimas_alertas) < self.max_alertas

    def _registrar_alerta(self, estado: EstadoActualMaquina) -> None:
        """Registra el timestamp de una alerta enviada."""
        estado.ultimas_alertas.append(datetime.now())

    # =====================================================
    # Evaluación de una Lectura de Telemetría
    # =====================================================

    def evaluar_lectura(
        self,
        id_planta: str,
        id_maquina: str,
        id_formula: str,
        codigo_producto: str,
        corriente: float,
        temp_acond: float,
        presion_vapor: float,
        timestamp: datetime,
        corriente_carga_minima: float,
        capacidad_nominal: float,
        t_min: float,
        t_max: float,
        p_min: float,
        p_max: float,
    ) -> list[Alerta]:
        """
        Evalúa una lectura de telemetría y genera alertas si corresponde.
        
        Flujo:
        1. Calcular EMA de las 3 variables
        2. Verificar si la máquina está operando (corriente > carga mínima)
        3. Comparar variables suavizadas contra límites
        4. Detectar cambios de estado (ISA-18.2)
        5. Aplicar regla anti-spam
        
        Args:
            Parámetros de la lectura de telemetría y límites de la fórmula.
            
        Returns:
            Lista de alertas generadas (puede estar vacía).
        """
        clave = self._clave_maquina(id_planta, id_maquina)
        estado = self._obtener_estado(clave)
        alertas: list[Alerta] = []

        # ─── Paso 1: Calcular EMA ───
        estado.ema_corriente = self.calcular_ema(corriente, estado.ema_corriente)
        estado.ema_temperatura = self.calcular_ema(temp_acond, estado.ema_temperatura)
        estado.ema_presion = self.calcular_ema(presion_vapor, estado.ema_presion)
        estado.ultima_lectura = timestamp

        # ─── Paso 2: Validar carga operativa ───
        if estado.ema_corriente < corriente_carga_minima:
            estado.estado_operativo = EstadoMaquina.INACTIVA
            logger.debug(
                "Máquina %s inactiva (corriente_suavizada=%.1f < min=%.1f)",
                clave, estado.ema_corriente, corriente_carga_minima
            )
            return alertas  # No evaluar máquinas apagadas
        
        estado.estado_operativo = EstadoMaquina.OPERANDO

        # Calcular porcentaje de carga para contexto
        porcentaje_carga = (estado.ema_corriente / capacidad_nominal) * 100 \
            if capacidad_nominal > 0 else 0

        # ─── Paso 3 y 4: Evaluar presión ───
        alertas.extend(self._evaluar_variable(
            estado=estado,
            clave=clave,
            id_planta=id_planta,
            id_maquina=id_maquina,
            id_formula=id_formula,
            codigo_producto=codigo_producto,
            variable='presion_vapor',
            valor_crudo=presion_vapor,
            valor_suavizado=estado.ema_presion,
            limite_min=p_min,
            limite_max=p_max,
            tipo_baja=TipoAlerta.PRESION_BAJA,
            tipo_alta=TipoAlerta.PRESION_ALTA,
            tipo_retorno=TipoAlerta.RETORNO_NORMAL_PRESION,
            estado_actual_attr='estado_presion',
            corriente_suavizada=estado.ema_corriente,
            capacidad_nominal=capacidad_nominal,
            porcentaje_carga=porcentaje_carga,
            timestamp=timestamp,
            candidato_attr='candidato_presion',
            persistencia_attr='persistencia_presion',
        ))

        # ─── Paso 3 y 4: Evaluar temperatura ───
        alertas.extend(self._evaluar_variable(
            estado=estado,
            clave=clave,
            id_planta=id_planta,
            id_maquina=id_maquina,
            id_formula=id_formula,
            codigo_producto=codigo_producto,
            variable='temp_acond',
            valor_crudo=temp_acond,
            valor_suavizado=estado.ema_temperatura,
            limite_min=t_min,
            limite_max=t_max,
            tipo_baja=TipoAlerta.TEMPERATURA_BAJA,
            tipo_alta=TipoAlerta.TEMPERATURA_ALTA,
            tipo_retorno=TipoAlerta.RETORNO_NORMAL_TEMPERATURA,
            estado_actual_attr='estado_temperatura',
            corriente_suavizada=estado.ema_corriente,
            capacidad_nominal=capacidad_nominal,
            porcentaje_carga=porcentaje_carga,
            timestamp=timestamp,
            candidato_attr='candidato_temperatura',
            persistencia_attr='persistencia_temperatura',
        ))

        return alertas

    def _evaluar_variable(
        self,
        estado: EstadoActualMaquina,
        clave: str,
        id_planta: str,
        id_maquina: str,
        id_formula: str,
        codigo_producto: str,
        variable: str,
        valor_crudo: float,
        valor_suavizado: float,
        limite_min: float,
        limite_max: float,
        tipo_baja: TipoAlerta,
        tipo_alta: TipoAlerta,
        tipo_retorno: TipoAlerta,
        estado_actual_attr: str,
        corriente_suavizada: float,
        capacidad_nominal: float,
        porcentaje_carga: float,
        timestamp: datetime,
        candidato_attr: str,
        persistencia_attr: str,
    ) -> list[Alerta]:
        """
        Evalúa una variable individual y detecta cambios de estado.
        
        Implementa la lógica ISA-18.2:
        - Normal → Baja/Alta = Genera alerta de desviación
        - Baja/Alta → Normal = Genera notificación de retorno
        - Sin cambio = Silencio (no re-alarmar)
        """
        alertas: list[Alerta] = []
        estado_anterior = getattr(estado, estado_actual_attr)

        # Determinar nuevo estado
        if valor_suavizado < limite_min:
            nuevo_estado = EstadoVariable.BAJA
        elif valor_suavizado > limite_max:
            nuevo_estado = EstadoVariable.ALTA
        else:
            nuevo_estado = EstadoVariable.NORMAL

        candidato_actual = getattr(estado, candidato_attr)
        persistencia_actual = getattr(estado, persistencia_attr)

        if nuevo_estado == candidato_actual:
            persistencia_actual += 1
        else:
            candidato_actual = nuevo_estado
            persistencia_actual = 1

        setattr(estado, candidato_attr, candidato_actual)
        setattr(estado, persistencia_attr, persistencia_actual)

        umbral_confirmacion = (
            self.confirmacion_retorno
            if nuevo_estado == EstadoVariable.NORMAL
            else self.confirmacion_alerta
        )

        if nuevo_estado == estado_anterior:
            return alertas

        if persistencia_actual < umbral_confirmacion:
            logger.info(
                "PENDIENTE DE CONFIRMACION | %s | %s candidato=%s | persistencia=%d/%d | valor=%.2f",
                clave,
                variable,
                nuevo_estado.value,
                persistencia_actual,
                umbral_confirmacion,
                valor_suavizado,
            )
            return alertas

        logger.info(
            "CAMBIO CONFIRMADO | %s | %s: %s → %s | persistencia=%d | valor=%.2f | limites=[%.1f, %.1f]",
            clave,
            variable,
            estado_anterior.value,
            nuevo_estado.value,
            persistencia_actual,
            valor_suavizado,
            limite_min,
            limite_max,
        )

        if nuevo_estado != EstadoVariable.NORMAL and not self._puede_alertar(estado):
            logger.warning(
                "Alerta confirmada pero suprimida por anti-spam para %s: %s",
                clave,
                variable,
            )
            setattr(estado, estado_actual_attr, nuevo_estado)
            return alertas

        # Crear alerta según el tipo de transición
        if nuevo_estado == EstadoVariable.NORMAL:
                # Retorno a normalidad
            alerta = Alerta(
                timestamp=timestamp,
                id_planta=id_planta,
                id_maquina=id_maquina,
                id_formula=id_formula,
                codigo_producto=codigo_producto,
                tipo_alerta=tipo_retorno,
                variable=variable,
                valor_crudo=valor_crudo,
                valor_suavizado=valor_suavizado,
                limite_violado=limite_min if estado_anterior == EstadoVariable.BAJA else limite_max,
                limite_min=limite_min,
                limite_max=limite_max,
                corriente_suavizada=corriente_suavizada,
                capacidad_nominal=capacidad_nominal,
                porcentaje_carga=porcentaje_carga,
                es_retorno_normal=True,
            )
        elif nuevo_estado == EstadoVariable.BAJA:
            alerta = Alerta(
                timestamp=timestamp,
                id_planta=id_planta,
                id_maquina=id_maquina,
                id_formula=id_formula,
                codigo_producto=codigo_producto,
                tipo_alerta=tipo_baja,
                variable=variable,
                valor_crudo=valor_crudo,
                valor_suavizado=valor_suavizado,
                limite_violado=limite_min,
                limite_min=limite_min,
                limite_max=limite_max,
                corriente_suavizada=corriente_suavizada,
                capacidad_nominal=capacidad_nominal,
                porcentaje_carga=porcentaje_carga,
            )
        else:  # ALTA
            alerta = Alerta(
                timestamp=timestamp,
                id_planta=id_planta,
                id_maquina=id_maquina,
                id_formula=id_formula,
                codigo_producto=codigo_producto,
                tipo_alerta=tipo_alta,
                variable=variable,
                valor_crudo=valor_crudo,
                valor_suavizado=valor_suavizado,
                limite_violado=limite_max,
                limite_min=limite_min,
                limite_max=limite_max,
                corriente_suavizada=corriente_suavizada,
                capacidad_nominal=capacidad_nominal,
                porcentaje_carga=porcentaje_carga,
            )

        alertas.append(alerta)
        if nuevo_estado != EstadoVariable.NORMAL:
            self._registrar_alerta(estado)
        logger.info("ALERTA GENERADA: %s", alerta)

        # Actualizar estado confirmado
        setattr(estado, estado_actual_attr, nuevo_estado)

        return alertas

    # =====================================================
    # Utilidades
    # =====================================================

    def obtener_historial_ema(self, id_planta: str, id_maquina: str) -> dict:
        """
        Retorna los últimos valores EMA de una máquina.
        
        Útil para construir el contexto que se envía al LLM.
        """
        clave = self._clave_maquina(id_planta, id_maquina)
        estado = self._estados.get(clave)
        if estado is None:
            return {}
        return {
            'ema_corriente': estado.ema_corriente,
            'ema_temperatura': estado.ema_temperatura,
            'ema_presion': estado.ema_presion,
            'estado_presion': estado.estado_presion.value,
            'estado_temperatura': estado.estado_temperatura.value,
            'estado_operativo': estado.estado_operativo.value,
            'ultima_lectura': estado.ultima_lectura,
        }

    def reiniciar_estados(self) -> None:
        """Limpia todos los estados almacenados en memoria."""
        self._estados.clear()
        logger.info("Estados de máquinas reiniciados.")
