"""
Memoria operativa de incidentes para trazabilidad, analitica y soporte predictivo.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class MemoriaIncidentes:
    """Mantiene un historial estructurado de incidentes y sus eventos asociados."""

    COLUMNS_INCIDENTES = [
        'id_incidente',
        'chat_id',
        'inicio',
        'fin',
        'estado',
        'duracion_min',
        'id_planta',
        'id_maquina',
        'id_formula',
        'codigo_producto',
        'lectura_inicial',
        'estado_global_inicial',
        'severidad_inicial',
        'causa_probable_inicial',
        'pronostico_inicial',
        'nivel_pronostico_inicial',
        'indice_salud_inicial',
        'alerta_resumida',
        'intencion_cierre',
        'accion_reportada',
        'resumen_operario',
        'respuesta_asistente',
        'ficha_generada',
        'correo_enviado',
        'monitoreo_reanudado',
    ]

    COLUMNS_EVENTOS = [
        'id_evento',
        'id_incidente',
        'timestamp',
        'tipo_evento',
        'descripcion',
        'payload_json',
    ]

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()
        self.ruta_incidentes = self.config.data_dir / 'historial_incidentes.csv'
        self.ruta_eventos = self.config.data_dir / 'historial_incidentes_eventos.csv'
        self._contador_incidente = 0
        self._contador_evento = 0
        self._inicializar_archivos()

    def _inicializar_archivos(self) -> None:
        for ruta, columnas in (
            (self.ruta_incidentes, self.COLUMNS_INCIDENTES),
            (self.ruta_eventos, self.COLUMNS_EVENTOS),
        ):
            if not ruta.exists():
                with open(ruta, 'w', newline='', encoding='utf-8') as f:
                    csv.writer(f).writerow(columnas)
            else:
                try:
                    df = pd.read_csv(ruta)
                    if not df.empty:
                        if ruta == self.ruta_incidentes and 'id_incidente' in df.columns:
                            self._contador_incidente = max(self._contador_incidente, int(df['id_incidente'].max()))
                        if ruta == self.ruta_eventos and 'id_evento' in df.columns:
                            self._contador_evento = max(self._contador_evento, int(df['id_evento'].max()))
                except Exception:
                    logger.warning("No fue posible leer %s al inicializar memoria de incidentes.", ruta)

    def abrir_incidente(
        self,
        *,
        chat_id: int,
        lectura: dict[str, Any],
        resumen_alerta: str,
    ) -> int:
        """Registra la apertura formal de un incidente."""
        self._contador_incidente += 1
        id_incidente = self._contador_incidente
        fila = [
            id_incidente,
            chat_id,
            datetime.now().isoformat(),
            '',
            'ABIERTO',
            '',
            lectura.get('id_planta', '001'),
            lectura.get('id_maquina', ''),
            lectura.get('id_formula', ''),
            lectura.get('codigo_producto', ''),
            lectura.get('numero', ''),
            lectura.get('estado_global', ''),
            lectura.get('severidad', ''),
            (lectura.get('causa_probable', '') or '').replace('\n', ' ').strip(),
            (lectura.get('pronostico', '') or '').replace('\n', ' ').strip(),
            lectura.get('pronostico_nivel', ''),
            lectura.get('indice_salud', ''),
            (resumen_alerta or '').replace('\n', ' ').strip(),
            '',
            '',
            '',
            '',
            0,
            0,
            0,
        ]
        with open(self.ruta_incidentes, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(fila)

        self.registrar_evento(
            id_incidente=id_incidente,
            tipo_evento='incidente_abierto',
            descripcion='Incidente abierto para gestion operativa.',
            payload={
                'chat_id': chat_id,
                'lectura': lectura.get('numero'),
                'maquina': lectura.get('id_maquina'),
                'severidad': lectura.get('severidad'),
            },
        )
        return id_incidente

    def registrar_evento(
        self,
        *,
        id_incidente: int,
        tipo_evento: str,
        descripcion: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> int:
        """Agrega un evento a la linea de tiempo del incidente."""
        self._contador_evento += 1
        fila = [
            self._contador_evento,
            id_incidente,
            datetime.now().isoformat(),
            tipo_evento,
            (descripcion or '').replace('\n', ' ').strip(),
            json.dumps(payload or {}, ensure_ascii=False),
        ]
        with open(self.ruta_eventos, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(fila)
        return self._contador_evento

    def cerrar_incidente(
        self,
        *,
        id_incidente: int,
        resultado_audio: dict[str, Any],
        ficha_generada: bool,
        correo_enviado: bool,
        monitoreo_reanudado: bool,
    ) -> None:
        """Actualiza el incidente con su estado final y datos de cierre."""
        if not self.ruta_incidentes.exists():
            return

        try:
            df = pd.read_csv(self.ruta_incidentes)
            if df.empty or id_incidente not in set(df['id_incidente'].astype(int)):
                return

            idx = df.index[df['id_incidente'].astype(int) == int(id_incidente)][0]
            inicio = pd.to_datetime(df.at[idx, 'inicio'], errors='coerce')
            fin = datetime.now()
            duracion = ''
            if pd.notnull(inicio):
                duracion = round((fin - inicio.to_pydatetime()).total_seconds() / 60, 2)

            df.at[idx, 'fin'] = fin.isoformat()
            df.at[idx, 'estado'] = 'CERRADO'
            df.at[idx, 'duracion_min'] = duracion
            df.at[idx, 'intencion_cierre'] = resultado_audio.get('intencion', '')
            df.at[idx, 'accion_reportada'] = (resultado_audio.get('accion_detectada', '') or '').replace('\n', ' ').strip()
            df.at[idx, 'resumen_operario'] = (resultado_audio.get('resumen_operario', '') or '').replace('\n', ' ').strip()
            df.at[idx, 'respuesta_asistente'] = (resultado_audio.get('respuesta_asistente', '') or '').replace('\n', ' ').strip()
            df.at[idx, 'ficha_generada'] = 1 if ficha_generada else 0
            df.at[idx, 'correo_enviado'] = 1 if correo_enviado else 0
            df.at[idx, 'monitoreo_reanudado'] = 1 if monitoreo_reanudado else 0
            df.to_csv(self.ruta_incidentes, index=False, encoding='utf-8')
        except Exception:
            logger.error("No fue posible cerrar incidente %s en memoria.", id_incidente, exc_info=True)

    def obtener_estadisticas(self) -> dict[str, Any]:
        """Devuelve KPIs de incidentes cerrados y abiertos."""
        try:
            df = pd.read_csv(self.ruta_incidentes)
        except Exception:
            return self._stats_vacias()

        if df.empty:
            return self._stats_vacias()

        abiertos = int((df['estado'].fillna('') == 'ABIERTO').sum())
        cerrados = int((df['estado'].fillna('') == 'CERRADO').sum())
        total = len(df)

        duraciones = pd.to_numeric(df['duracion_min'], errors='coerce').dropna()
        tiempo_prom = round(float(duraciones.mean()), 1) if not duraciones.empty else 0.0

        ficha_ok = int(pd.to_numeric(df['ficha_generada'], errors='coerce').fillna(0).sum())
        correo_ok = int(pd.to_numeric(df['correo_enviado'], errors='coerce').fillna(0).sum())

        severidades = (
            df['severidad_inicial']
            .fillna('SIN_DATO')
            .astype(str)
            .value_counts()
            .to_dict()
        )

        maquinas = (
            df['id_maquina']
            .fillna('')
            .astype(str)
            .value_counts()
            .head(3)
            .to_dict()
        )

        return {
            'total_incidentes': total,
            'incidentes_abiertos': abiertos,
            'incidentes_cerrados': cerrados,
            'tiempo_promedio_resolucion_min': tiempo_prom,
            'fichas_generadas': ficha_ok,
            'correos_enviados': correo_ok,
            'severidad_por_tipo': severidades,
            'top_maquinas': maquinas,
        }

    def obtener_contexto_predictivo(
        self,
        *,
        id_maquina: str,
        causa_probable: str,
        ventana_horas: int = 24,
    ) -> dict[str, Any]:
        """Resume recurrencia reciente para un predictor simple y explicable."""
        try:
            df = pd.read_csv(self.ruta_incidentes)
        except Exception:
            return {'recientes_maquina': 0, 'similares': 0}

        if df.empty:
            return {'recientes_maquina': 0, 'similares': 0}

        df = df.copy()
        df['inicio'] = pd.to_datetime(df['inicio'], errors='coerce')
        corte = datetime.now() - timedelta(hours=ventana_horas)
        recientes = df[df['inicio'] >= pd.Timestamp(corte)]

        recientes_maquina = recientes[recientes['id_maquina'].astype(str) == str(id_maquina)]
        causa_tokens = self._tokens_causa(causa_probable)
        similares = 0
        for _, row in recientes_maquina.iterrows():
            causa_hist = self._tokens_causa(str(row.get('causa_probable_inicial', '')))
            if causa_tokens and causa_hist and causa_tokens.intersection(causa_hist):
                similares += 1

        return {
            'recientes_maquina': int(len(recientes_maquina)),
            'similares': int(similares),
        }

    def obtener_linea_tiempo(self, id_incidente: int) -> list[dict[str, Any]]:
        """Carga la linea de tiempo de un incidente."""
        try:
            df = pd.read_csv(self.ruta_eventos)
        except Exception:
            return []
        if df.empty:
            return []
        df = df[df['id_incidente'].astype(int) == int(id_incidente)].copy()
        df = df.sort_values('id_evento')
        return df.to_dict('records')

    def _tokens_causa(self, texto: str) -> set[str]:
        base = (texto or '').lower()
        tokens = set()
        for palabra in ['vapor', 'temperatura', 'presion', 'sobrecarga', 'mantenimiento', 'valvula', 'energia', 'recuperacion']:
            if palabra in base:
                tokens.add(palabra)
        return tokens

    def _stats_vacias(self) -> dict[str, Any]:
        return {
            'total_incidentes': 0,
            'incidentes_abiertos': 0,
            'incidentes_cerrados': 0,
            'tiempo_promedio_resolucion_min': 0.0,
            'fichas_generadas': 0,
            'correos_enviados': 0,
            'severidad_por_tipo': {},
            'top_maquinas': {},
        }
