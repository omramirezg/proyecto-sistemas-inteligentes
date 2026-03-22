"""
Historial de interacciones del operario por audio.
"""

import csv
import logging
from datetime import datetime
from typing import Optional

import pandas as pd

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class HistorialOperario:
    """Persistencia simple para audios, transcripciones e intenciones detectadas."""

    COLUMNS = [
        'id',
        'timestamp',
        'chat_id',
        'tipo_entrada',
        'mime_type',
        'duracion_seg',
        'audio_file_id',
        'id_planta',
        'id_maquina',
        'id_formula',
        'codigo_producto',
        'transcripcion',
        'intencion',
        'accion_detectada',
        'resumen_operario',
        'nivel_urgencia',
    ]

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()
        self.ruta_archivo = self.config.data_dir / 'historial_operario_audio.csv'
        self._contador_id = 0
        self._inicializar_archivo()

    def _inicializar_archivo(self) -> None:
        if not self.ruta_archivo.exists():
            with open(self.ruta_archivo, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(self.COLUMNS)
            logger.info("Historial de operario creado: %s", self.ruta_archivo)
            return

        try:
            df = pd.read_csv(self.ruta_archivo)
            if not df.empty and 'id' in df.columns:
                self._contador_id = int(df['id'].max())
        except Exception:
            self._contador_id = 0

    def registrar_interaccion(
        self,
        *,
        chat_id: int,
        tipo_entrada: str,
        mime_type: str,
        duracion_seg: float,
        audio_file_id: str,
        id_planta: str,
        id_maquina: str,
        id_formula: str,
        codigo_producto: str,
        transcripcion: str,
        intencion: str,
        accion_detectada: str,
        resumen_operario: str,
        nivel_urgencia: str,
    ) -> int:
        self._contador_id += 1
        registro_id = self._contador_id

        fila = [
            registro_id,
            datetime.now().isoformat(),
            chat_id,
            tipo_entrada,
            mime_type,
            round(float(duracion_seg), 2),
            audio_file_id,
            id_planta,
            id_maquina,
            id_formula,
            codigo_producto,
            (transcripcion or '').replace('\n', ' ').strip(),
            (intencion or '').strip(),
            (accion_detectada or '').replace('\n', ' ').strip(),
            (resumen_operario or '').replace('\n', ' ').strip(),
            (nivel_urgencia or '').strip(),
        ]

        with open(self.ruta_archivo, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(fila)

        logger.info(
            "Interaccion de operario registrada ID=%d chat_id=%d intencion=%s",
            registro_id,
            chat_id,
            intencion,
        )
        return registro_id
