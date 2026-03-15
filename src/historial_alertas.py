"""
Historial de Alertas
=====================
Gestiona la persistencia del historial de alertas y prescripciones
en un archivo CSV dedicado.

Este historial es la "Fuente de Verdad" (Data Source) para:
- El módulo de generación de reportes PDF
- El análisis de efectividad del modelo LLM
- La trazabilidad operativa del sistema
"""

import logging
import csv
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class HistorialAlertas:
    """
    Gestiona la lectura y escritura del historial de alertas.
    
    Cada alerta se registra con su prescripción IA y el feedback
    del operario para evaluar la efectividad del modelo.
    
    Columnas:
        id, timestamp, id_planta, id_maquina, id_formula,
        variable, tipo_alerta, valor_suavizado, limite_violado,
        prescripcion_ia, feedback_operario, timestamp_feedback
    """

    COLUMNS = [
        'id', 'timestamp', 'id_planta', 'id_maquina', 'id_formula',
        'codigo_producto', 'variable', 'tipo_alerta', 'valor_crudo',
        'valor_suavizado', 'limite_violado', 'limite_min', 'limite_max',
        'porcentaje_carga', 'prescripcion_ia', 'feedback_operario',
        'timestamp_feedback',
    ]

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()
        self.ruta_archivo = self.config.data_dir / 'historial_alertas.csv'
        self._contador_id: int = 0

        # Crear archivo con headers si no existe
        self._inicializar_archivo()

    def _inicializar_archivo(self) -> None:
        """Crea el archivo CSV con encabezados si no existe."""
        if not self.ruta_archivo.exists():
            with open(self.ruta_archivo, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self.COLUMNS)
            logger.info(
                "Historial de alertas creado: %s", self.ruta_archivo
            )
        else:
            # Cargar último ID para continuar secuencia
            try:
                df = pd.read_csv(self.ruta_archivo)
                if not df.empty and 'id' in df.columns:
                    self._contador_id = int(df['id'].max())
            except Exception:
                self._contador_id = 0
            logger.info(
                "Historial existente cargado: %s (último ID: %d)",
                self.ruta_archivo, self._contador_id
            )

    def registrar_alerta(
        self,
        timestamp: datetime,
        id_planta: str,
        id_maquina: str,
        id_formula: str,
        codigo_producto: str,
        variable: str,
        tipo_alerta: str,
        valor_crudo: float,
        valor_suavizado: float,
        limite_violado: float,
        limite_min: float,
        limite_max: float,
        porcentaje_carga: float,
        prescripcion_ia: str,
    ) -> int:
        """
        Registra una nueva alerta en el historial.
        
        Args:
            Datos de la alerta y la prescripción generada por el LLM.
            
        Returns:
            ID único de la alerta registrada.
        """
        self._contador_id += 1
        alerta_id = self._contador_id

        fila = [
            alerta_id,
            timestamp.isoformat(),
            id_planta,
            id_maquina,
            id_formula,
            codigo_producto,
            variable,
            tipo_alerta,
            round(valor_crudo, 4),
            round(valor_suavizado, 4),
            round(limite_violado, 2),
            round(limite_min, 2),
            round(limite_max, 2),
            round(porcentaje_carga, 1),
            prescripcion_ia.replace('\n', ' ').strip(),
            '',  # feedback_operario (vacío hasta que responda)
            '',  # timestamp_feedback (vacío)
        ]

        try:
            with open(self.ruta_archivo, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(fila)
            logger.info(
                "Alerta registrada ID=%d: %s en máquina %s-%s",
                alerta_id, tipo_alerta, id_planta, id_maquina
            )
        except Exception as e:
            logger.error("Error registrando alerta: %s", e)

        return alerta_id

    def registrar_feedback(
        self,
        alerta_id: int,
        feedback: str,
    ) -> bool:
        """
        Registra el feedback del operario para una alerta.
        
        Args:
            alerta_id: ID de la alerta.
            feedback: Tipo de feedback ('UTIL', 'FALSO_POSITIVO', 'FALLA_MECANICA').
            
        Returns:
            True si se actualizó correctamente.
        """
        try:
            df = pd.read_csv(self.ruta_archivo)
            mascara = df['id'] == alerta_id

            if not mascara.any():
                logger.warning("Alerta ID=%d no encontrada para feedback.", alerta_id)
                return False

            df.loc[mascara, 'feedback_operario'] = feedback
            df.loc[mascara, 'timestamp_feedback'] = datetime.now().isoformat()

            df.to_csv(self.ruta_archivo, index=False)
            logger.info(
                "Feedback registrado para alerta ID=%d: %s",
                alerta_id, feedback
            )
            return True

        except Exception as e:
            logger.error("Error registrando feedback: %s", e)
            return False

    def consultar_periodo(
        self,
        fecha_inicio: str,
        fecha_fin: str,
    ) -> pd.DataFrame:
        """
        Consulta alertas en un período de tiempo.
        
        Args:
            fecha_inicio: Fecha inicio (ISO format).
            fecha_fin: Fecha fin (ISO format).
            
        Returns:
            DataFrame filtrado por período.
        """
        try:
            df = pd.read_csv(
                self.ruta_archivo,
                parse_dates=['timestamp']
            )
            if df.empty:
                return df

            inicio = pd.Timestamp(fecha_inicio)
            fin = pd.Timestamp(fecha_fin)

            mascara = (df['timestamp'] >= inicio) & (df['timestamp'] <= fin)
            resultado = df[mascara].copy()

            logger.info(
                "Consulta historial: %d alertas en período %s - %s",
                len(resultado), fecha_inicio, fecha_fin
            )
            return resultado

        except Exception as e:
            logger.error("Error consultando historial: %s", e)
            return pd.DataFrame(columns=self.COLUMNS)

    def obtener_estadisticas(self) -> dict:
        """
        Genera estadísticas básicas del historial.
        
        Returns:
            Diccionario con métricas clave.
        """
        try:
            df = pd.read_csv(self.ruta_archivo)
            if df.empty:
                return {'total_alertas': 0}

            stats = {
                'total_alertas': len(df),
                'alertas_por_tipo': df['tipo_alerta'].value_counts().to_dict(),
                'alertas_por_maquina': df.groupby(
                    ['id_planta', 'id_maquina']
                ).size().to_dict(),
                'con_feedback': df['feedback_operario'].fillna('').astype(str).str.strip().ne('').sum(),
                'sin_feedback': df['feedback_operario'].fillna('').astype(str).str.strip().eq('').sum(),
            }

            # Calcular efectividad si hay feedback
            if stats['con_feedback'] > 0:
                feedback_df = df[df['feedback_operario'].fillna('').astype(str).str.strip().ne('')]
                stats['feedback_por_tipo'] = feedback_df['feedback_operario'].value_counts().to_dict()
                stats['porcentaje_utiles'] = (
                    (feedback_df['feedback_operario'] == 'UTIL').sum()
                    / len(feedback_df) * 100
                )
                stats['porcentaje_falsos_positivos'] = (
                    (feedback_df['feedback_operario'] == 'FALSO_POSITIVO').sum()
                    / len(feedback_df) * 100
                )
                stats['porcentaje_mantenimiento'] = (
                    (feedback_df['feedback_operario'] == 'FALLA_MECANICA').sum()
                    / len(feedback_df) * 100
                )
            else:
                stats['feedback_por_tipo'] = {}
                stats['porcentaje_utiles'] = 0.0
                stats['porcentaje_falsos_positivos'] = 0.0
                stats['porcentaje_mantenimiento'] = 0.0

            return stats

        except Exception as e:
            logger.error("Error obteniendo estadísticas: %s", e)
            return {'total_alertas': 0, 'error': str(e)}

    def cargar_dataframe(self) -> pd.DataFrame:
        """Carga el historial completo como DataFrame."""
        try:
            return pd.read_csv(self.ruta_archivo)
        except Exception as e:
            logger.error("Error cargando historial como dataframe: %s", e)
            return pd.DataFrame(columns=self.COLUMNS)
