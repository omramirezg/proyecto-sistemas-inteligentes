"""
Módulo de Carga de Datos
========================
Gestiona la lectura dinámica de tablas maestras (Slow Data)
y telemetría transaccional (Fast Data) desde archivos CSV.

Principio: Desacoplamiento Lógico — el motor consulta las tablas
en cada ciclo de forma dinámica, sin valores quemados en código.
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class DataLoader:
    """
    Carga y gestiona los datos maestros y de telemetría.
    
    Implementa dos velocidades de procesamiento:
    - Fast Data: Telemetría transaccional (lectura cada ciclo)
    - Slow Data: Tablas maestras (recarga periódica cada N ciclos)
    
    Attributes:
        equipos: DataFrame con especificaciones de equipos.
        formulas: DataFrame con fórmulas y límites operativos.
        personal: DataFrame con personal, turnos y preferencias.
    """

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()
        self.data_dir: Path = self.config.data_dir

        # DataFrames maestros (Slow Data) — se recargan periódicamente
        self.equipos: Optional[pd.DataFrame] = None
        self.formulas: Optional[pd.DataFrame] = None
        self.personal: Optional[pd.DataFrame] = None

        # Control de recarga de datos maestros
        self._ciclos_desde_recarga: int = 0
        self._intervalo_recarga_maestros: int = 300  # Cada 300 ciclos (~5 min)

        logger.info("DataLoader inicializado. Directorio de datos: %s", self.data_dir)

    # =====================================================
    # Carga de Tablas Maestras (Slow Data)
    # =====================================================

    def cargar_maestro_equipos(self) -> pd.DataFrame:
        """
        Carga la tabla maestra de equipos desde CSV.
        
        Contiene: id_planta, id_maquina, capacidad_nominal,
                  corriente_vacio, corriente_carga_minima
        
        Returns:
            DataFrame con especificaciones de equipos.
        """
        ruta = self.data_dir / 'maestro_equipos.csv'
        try:
            df = pd.read_csv(ruta, dtype={'id_planta': str, 'id_maquina': str})
            # Normalizar IDs a 3 dígitos con ceros a la izquierda
            df['id_planta'] = df['id_planta'].str.strip().str.zfill(3)
            df['id_maquina'] = df['id_maquina'].str.strip().str.zfill(3)
            self.equipos = df
            logger.info(
                "Maestro equipos cargado: %d registros desde %s",
                len(df), ruta
            )
            return df
        except FileNotFoundError:
            logger.error("Archivo no encontrado: %s", ruta)
            raise
        except Exception as e:
            logger.error("Error cargando maestro_equipos: %s", e)
            raise

    def cargar_maestro_formulas(self) -> pd.DataFrame:
        """
        Carga la tabla maestra de fórmulas desde CSV.
        
        Contiene: id_planta, id_formula, codigo_producto,
                  t_min, t_max, p_min, p_max, pqf,
                  humedad_objetivo, durabilidad_objetivo
        
        Returns:
            DataFrame con fórmulas y límites operativos.
        """
        ruta = self.data_dir / 'maestro_formulas.csv'
        try:
            df = pd.read_csv(ruta, dtype={'id_planta': str, 'id_formula': str})
            df['id_planta'] = df['id_planta'].str.strip().str.zfill(3)
            self.formulas = df
            logger.info(
                "Maestro fórmulas cargado: %d registros desde %s",
                len(df), ruta
            )
            return df
        except FileNotFoundError:
            logger.error("Archivo no encontrado: %s", ruta)
            raise
        except Exception as e:
            logger.error("Error cargando maestro_formulas: %s", e)
            raise

    def cargar_maestro_personal(self) -> pd.DataFrame:
        """
        Carga la tabla maestra de personal desde CSV.
        
        Contiene: id_empleado, nombre_completo, id_planta, rol,
                  id_maquina_asignada, dias_laborales, hora_inicio_turno,
                  hora_fin_turno, numero_celular, recibe_alertas,
                  recibe_prescriptivo, recibe_pdf
        
        Returns:
            DataFrame con personal y preferencias de notificación.
        """
        ruta = self.data_dir / 'maestro_personal.csv'
        try:
            df = pd.read_csv(ruta, dtype={'id_planta': str})
            df['id_planta'] = df['id_planta'].str.strip().str.zfill(3)
            # Convertir flags de notificación a booleanos
            for col in ['recibe_alertas', 'recibe_prescriptivo', 'recibe_pdf']:
                df[col] = df[col].astype(bool)
            self.personal = df
            logger.info(
                "Maestro personal cargado: %d registros desde %s",
                len(df), ruta
            )
            return df
        except FileNotFoundError:
            logger.error("Archivo no encontrado: %s", ruta)
            raise
        except Exception as e:
            logger.error("Error cargando maestro_personal: %s", e)
            raise

    def cargar_todos_los_maestros(self) -> None:
        """Carga todas las tablas maestras de una sola vez."""
        self.cargar_maestro_equipos()
        self.cargar_maestro_formulas()
        self.cargar_maestro_personal()
        self._ciclos_desde_recarga = 0
        logger.info("Todas las tablas maestras cargadas correctamente.")

    def verificar_recarga_maestros(self) -> None:
        """
        Verifica si es momento de recargar las tablas maestras.
        
        Las tablas maestras son Slow Data y no necesitan
        recargarse en cada ciclo del worker.
        """
        self._ciclos_desde_recarga += 1
        if self._ciclos_desde_recarga >= self._intervalo_recarga_maestros:
            logger.info("Recargando tablas maestras (ciclo %d)...",
                        self._ciclos_desde_recarga)
            self.cargar_todos_los_maestros()

    # =====================================================
    # Carga de Telemetría (Fast Data)
    # =====================================================

    def cargar_telemetria(self, id_planta: str) -> pd.DataFrame:
        """
        Carga la telemetría completa de una planta desde CSV.
        
        En producción, esta función consultaría un Datalake (Snowflake).
        En el prototipo, lee un CSV estático que simula datos en tiempo real.
        
        Args:
            id_planta: Identificador de la planta ('001' o '002').
            
        Returns:
            DataFrame con telemetría ordenada cronológicamente.
        """
        planta_limpia = id_planta.strip().zfill(3)
        ruta = self.data_dir / f'telemetria_planta_{planta_limpia}.csv'

        if not ruta.exists():
            # Intentar con el archivo de ejemplos como fallback
            ruta_ejemplos = self.data_dir / 'telemetria_planta_ejemplos.csv'
            if ruta_ejemplos.exists():
                logger.warning(
                    "Telemetría planta %s no encontrada. "
                    "Usando archivo de ejemplos: %s",
                    planta_limpia, ruta_ejemplos
                )
                ruta = ruta_ejemplos
            else:
                raise FileNotFoundError(
                    f"No se encontró telemetría para planta {planta_limpia}"
                )

        try:
            df = pd.read_csv(
                ruta,
                dtype={'id_planta': str, 'id_maquina': str, 'id_formula': str},
                parse_dates=['fecha_registro']
            )
            # Normalizar IDs
            df['id_planta'] = df['id_planta'].str.strip().str.zfill(3)
            df['id_maquina'] = df['id_maquina'].str.strip().str.zfill(3)
            df['id_formula'] = df['id_formula'].str.strip()

            # Ordenar cronológicamente
            df = df.sort_values('fecha_registro').reset_index(drop=True)

            # ─── Simular tiempo real ───
            # Generar fechas de simulacion IoT:
            # la primera fila arranca en "ahora" y cada lectura avanza 1 minuto
            ahora = pd.Timestamp.now().floor('s')
            n_rows = len(df)
            df['fecha_registro'] = [
                ahora + pd.Timedelta(minutes=i) for i in range(n_rows)
            ]
            logger.info(
                "Telemetria planta %s: simulacion IoT regenerada desde %s hasta %s",
                planta_limpia,
                df['fecha_registro'].min().strftime('%Y-%m-%d %H:%M:%S'),
                df['fecha_registro'].max().strftime('%Y-%m-%d %H:%M:%S')
            )

            logger.info(
                "Telemetría planta %s cargada: %d registros (%s — %s)",
                planta_limpia,
                len(df),
                df['fecha_registro'].min(),
                df['fecha_registro'].max()
            )
            return df
        except Exception as e:
            logger.error(
                "Error cargando telemetría planta %s: %s",
                planta_limpia, e
            )
            raise

    # =====================================================
    # Consultas de Datos Maestros
    # =====================================================

    def obtener_limites_formula(
        self, id_planta: str, id_formula: str
    ) -> Optional[pd.Series]:
        """
        Obtiene los límites operativos de una fórmula específica.
        
        Args:
            id_planta: Identificador de la planta.
            id_formula: Identificador de la fórmula.
            
        Returns:
            Serie con t_min, t_max, p_min, p_max, etc., o None si no existe.
        """
        if self.formulas is None:
            self.cargar_maestro_formulas()

        planta = id_planta.strip().zfill(3)
        formula = id_formula.strip()

        mascara = (
            (self.formulas['id_planta'] == planta) &
            (self.formulas['id_formula'] == formula)
        )
        resultado = self.formulas[mascara]

        if resultado.empty:
            logger.warning(
                "Fórmula no encontrada: planta=%s, formula=%s",
                planta, formula
            )
            return None
        return resultado.iloc[0]

    def obtener_specs_equipo(
        self, id_planta: str, id_maquina: str
    ) -> Optional[pd.Series]:
        """
        Obtiene las especificaciones de un equipo específico.
        
        Args:
            id_planta: Identificador de la planta.
            id_maquina: Identificador de la máquina.
            
        Returns:
            Serie con capacidad_nominal, corriente_vacio, etc., o None.
        """
        if self.equipos is None:
            self.cargar_maestro_equipos()

        planta = id_planta.strip().zfill(3)
        maquina = id_maquina.strip().zfill(3)

        mascara = (
            (self.equipos['id_planta'] == planta) &
            (self.equipos['id_maquina'] == maquina)
        )
        resultado = self.equipos[mascara]

        if resultado.empty:
            logger.warning(
                "Equipo no encontrado: planta=%s, maquina=%s",
                planta, maquina
            )
            return None
        return resultado.iloc[0]

    def obtener_personal_en_turno(
        self,
        id_planta: str,
        id_maquina: str,
        hora_actual: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Obtiene el personal que debe recibir notificaciones en este momento.
        
        Filtra por planta, máquina asignada (o TODAS) y turno vigente.
        
        Args:
            id_planta: Identificador de la planta.
            id_maquina: Identificador de la máquina.
            hora_actual: Hora actual en formato 'HH:MM:SS'. Si None, usa la hora del sistema.
            
        Returns:
            DataFrame con el personal filtrado.
        """
        if self.personal is None:
            self.cargar_maestro_personal()

        from datetime import datetime

        planta = id_planta.strip().zfill(3)
        maquina = id_maquina.strip().zfill(3)

        if hora_actual is None:
            hora_actual = datetime.now().strftime('%H:%M:%S')

        # Filtrar por planta
        df = self.personal[self.personal['id_planta'] == planta].copy()

        # Filtrar por máquina asignada (o TODAS)
        df = df[
            (df['id_maquina_asignada'].str.strip() == maquina) |
            (df['id_maquina_asignada'].str.strip().str.upper() == 'TODAS')
        ]

        # Filtrar por turno vigente
        hora_dt = datetime.strptime(hora_actual, '%H:%M:%S').time()
        personal_en_turno = []

        for _, persona in df.iterrows():
            inicio = datetime.strptime(
                str(persona['hora_inicio_turno']).strip(), '%H:%M:%S'
            ).time()
            fin = datetime.strptime(
                str(persona['hora_fin_turno']).strip(), '%H:%M:%S'
            ).time()

            # Manejar turnos que cruzan medianoche (ej: 22:00 - 06:00)
            if inicio <= fin:
                en_turno = inicio <= hora_dt <= fin
            else:
                en_turno = hora_dt >= inicio or hora_dt <= fin

            if en_turno:
                personal_en_turno.append(persona)

        resultado = pd.DataFrame(personal_en_turno)
        logger.debug(
            "Personal en turno para planta=%s, maquina=%s: %d personas",
            planta, maquina, len(resultado)
        )
        return resultado
