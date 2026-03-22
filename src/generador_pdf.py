"""
Generador de reportes PDF compactos para operacion y gerencia.
"""

import logging
import os
import tempfile
from datetime import datetime, timedelta
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from fpdf import FPDF

from config_loader import ConfigLoader
from data_loader import DataLoader
from historial_alertas import HistorialAlertas
from memoria_incidentes import MemoriaIncidentes

logger = logging.getLogger(__name__)


class ReportePDF(FPDF):
    """PDF compacto con jerarquia visual clara."""

    def __init__(self, titulo: str = "Reporte Ejecutivo Operacional IA") -> None:
        super().__init__()
        self.titulo = titulo
        self.set_auto_page_break(auto=True, margin=14)

    def header(self) -> None:
        self.set_fill_color(19, 33, 68)
        self.rect(0, 0, 210, 20, style='F')
        self.set_xy(10, 5)
        self.set_font('Helvetica', 'B', 15)
        self.set_text_color(255, 255, 255)
        self.cell(0, 7, self.titulo)
        self.set_xy(10, 12)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(219, 234, 254)
        self.cell(0, 5, 'Reporte compacto para operacion y gerencia')
        self.ln(10)

    def footer(self) -> None:
        self.set_y(-10)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(120, 120, 120)
        self.cell(
            0,
            6,
            f'Pagina {self.page_no()}/{{nb}} | {datetime.now().strftime("%Y-%m-%d %H:%M")} | Confidencial',
            align='C',
        )


class GeneradorPDF:
    """Genera un PDF claro, compacto y util para dos perfiles de usuario."""

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()

    def generar_reporte_tiempo_real(
        self,
        df_telemetria: pd.DataFrame,
        data_loader: DataLoader,
        historial_alertas: Optional[HistorialAlertas] = None,
        memoria_incidentes: Optional[MemoriaIncidentes] = None,
    ) -> bytes:
        """Genera el reporte completo en bytes."""
        logger.info("Generando PDF compacto...")

        pdf = ReportePDF()
        pdf.alias_nb_pages()

        df_operativo = self._preparar_datos(df_telemetria.copy())
        df_fatiga = self._calcular_fatiga(df_operativo, data_loader)
        df_historial = (
            historial_alertas.cargar_dataframe()
            if historial_alertas is not None
            else pd.DataFrame()
        )
        stats_incidentes = (
            memoria_incidentes.obtener_estadisticas()
            if memoria_incidentes is not None
            else {
                'total_incidentes': 0,
                'incidentes_abiertos': 0,
                'incidentes_cerrados': 0,
                'tiempo_promedio_resolucion_min': 0.0,
                'fichas_generadas': 0,
                'correos_enviados': 0,
            }
        )

        self._pagina_resumen(pdf, df_operativo, df_historial, stats_incidentes)
        self._pagina_tendencias(pdf, df_operativo)
        self._pagina_alarmas(pdf, df_fatiga, df_historial)
        self._pagina_gerencial(pdf, df_operativo, data_loader, df_historial, stats_incidentes)

        pdf_bytes = pdf.output()
        logger.info("PDF compacto generado: %.1f KB", len(pdf_bytes) / 1024)
        return bytes(pdf_bytes)

    def _preparar_datos(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df = df.copy()
        df['fecha_registro'] = pd.to_datetime(df['fecha_registro'])
        df.loc[df['temp_acond'] < 0, 'temp_acond'] = np.nan
        df.loc[df['presion_vapor'] < 0, 'presion_vapor'] = np.nan

        df['corriente_suave'] = df.groupby(['id_planta', 'id_maquina'])['corriente'].transform(
            lambda x: x.ewm(alpha=0.33, adjust=False).mean()
        )
        df['temp_suave'] = df.groupby(['id_planta', 'id_maquina'])['temp_acond'].transform(
            lambda x: x.ewm(alpha=0.33, adjust=False).mean()
        )
        df['presion_suave'] = df.groupby(['id_planta', 'id_maquina'])['presion_vapor'].transform(
            lambda x: x.ewm(alpha=0.66, adjust=False).mean()
        )
        df['hora'] = df['fecha_registro'].dt.strftime('%H:%M')
        return df[df['corriente_suave'] >= 100.0].copy()

    def _calcular_fatiga(self, df_operativo: pd.DataFrame, data_loader: DataLoader) -> pd.DataFrame:
        if df_operativo.empty:
            return pd.DataFrame()

        if data_loader.formulas is None:
            data_loader.cargar_maestro_formulas()

        formulas_dict = (
            data_loader.formulas
            .reset_index(drop=True)
            .drop_duplicates(subset=['id_formula'])
            .set_index('id_formula')
            .to_dict('index')
        )

        results = []
        for maquina, group in df_operativo.groupby('id_maquina'):
            state = 'OK'
            alarm_times = []
            for _, row in group.iterrows():
                formula = row['id_formula']
                if formula not in formulas_dict:
                    continue
                f = formulas_dict[formula]
                tmin, tmax = float(f['t_min']), float(f['t_max'])
                pmin, pmax = float(f['p_min']), float(f['p_max'])

                is_oob = False
                if pd.notnull(row['temp_suave']) and (row['temp_suave'] < tmin or row['temp_suave'] > tmax):
                    is_oob = True
                if pd.notnull(row['presion_suave']) and (row['presion_suave'] < pmin or row['presion_suave'] > pmax):
                    is_oob = True

                desvio = 1 if is_oob else 0
                alarma = 0
                now = row['fecha_registro']
                if is_oob and state == 'OK':
                    alarm_times = [t for t in alarm_times if now - t <= timedelta(minutes=10)]
                    if len(alarm_times) < 2:
                        alarma = 1
                        alarm_times.append(now)
                        state = 'ALARM'
                elif not is_oob and state == 'ALARM':
                    state = 'OK'

                results.append({
                    'id_maquina': maquina,
                    'id_formula': formula,
                    'desvio': desvio,
                    'alarma': alarma,
                })

        if not results:
            return pd.DataFrame()

        df_res = pd.DataFrame(results)
        out = df_res.groupby(['id_maquina', 'id_formula']).sum().reset_index()
        out['ruido_evitado'] = np.where(
            out['desvio'] > 0,
            ((out['desvio'] - out['alarma']) / out['desvio'] * 100).round(1),
            0,
        )
        return out.sort_values(['desvio', 'alarma'], ascending=False)

    def _save_fig(self, fig) -> str:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        temp.close()
        fig.savefig(temp.name, format='png', dpi=160, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        return temp.name

    def _section_title(self, pdf: ReportePDF, title: str, subtitle: str = "") -> None:
        pdf.set_fill_color(227, 242, 253)
        pdf.set_text_color(17, 24, 39)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 8, title, fill=True, new_x="LMARGIN", new_y="NEXT")
        if subtitle:
            pdf.set_font('Helvetica', '', 9)
            pdf.set_text_color(75, 85, 99)
            pdf.multi_cell(0, 4.5, subtitle)
        pdf.ln(1)

    def _card(self, pdf: ReportePDF, x: float, y: float, w: float, h: float, label: str, value: str, fill: tuple[int, int, int]) -> None:
        pdf.set_fill_color(*fill)
        pdf.set_draw_color(255, 255, 255)
        pdf.rect(x, y, w, h, style='F')
        pdf.set_xy(x + 3, y + 3)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(255, 255, 255)
        pdf.multi_cell(w - 6, 4, label)
        pdf.set_x(x + 3)
        pdf.set_font('Helvetica', 'B', 16)
        pdf.cell(w - 6, 8, value)

    def _small_table(self, pdf: ReportePDF, headers: list[str], rows: list[list[str]], widths: list[int]) -> None:
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_fill_color(31, 41, 55)
        pdf.set_text_color(255, 255, 255)
        for header, width in zip(headers, widths):
            pdf.cell(width, 7, header, border=1, fill=True, align='C')
        pdf.ln()
        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(17, 24, 39)
        for row in rows:
            for cell, width in zip(row, widths):
                pdf.cell(width, 6, cell, border=1, align='C')
            pdf.ln()

    def _pagina_resumen(
        self,
        pdf: ReportePDF,
        df_operativo: pd.DataFrame,
        df_historial: pd.DataFrame,
        stats_incidentes: dict,
    ) -> None:
        pdf.add_page()
        self._section_title(
            pdf,
            '1. Resumen Rapido',
            'La parte superior sirve para gerencia. La parte inferior resume lo importante para operacion.',
        )

        if df_operativo.empty:
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(0, 8, 'Sin datos operativos suficientes.', new_x="LMARGIN", new_y="NEXT")
            return

        estabilidad = round((df_operativo[df_operativo['retornando'] == 0].shape[0] / max(len(df_operativo), 1)) * 100, 1)
        temp_media = round(df_operativo['temp_suave'].mean(), 1)
        pres_media = round(df_operativo['presion_suave'].mean(), 1)
        energia = round(df_operativo['kw_h_proceso'].sum(), 1)
        maquinas = str(df_operativo['id_maquina'].nunique())
        utiles = self._porcentaje_feedback(df_historial, 'UTIL')

        self._card(pdf, 12, 38, 43, 22, 'Estabilidad', f'{estabilidad}%', (22, 101, 52))
        self._card(pdf, 60, 38, 43, 22, 'Temp media', f'{temp_media} C', (180, 83, 9))
        self._card(pdf, 108, 38, 43, 22, 'Presion media', f'{pres_media} PSI', (29, 78, 137))
        self._card(pdf, 156, 38, 43, 22, 'Energia', f'{energia} kW', (91, 33, 182))

        pdf.set_xy(12, 68)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(17, 24, 39)
        pdf.cell(92, 6, 'Lectura para Operacion', border=0)
        pdf.cell(92, 6, 'Lectura para Gerencia', border=0, new_x="LMARGIN", new_y="NEXT")

        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(55, 65, 81)
        op_text = (
            f'Maquinas activas: {maquinas}\n'
            f'Ultima ventana operativa con {len(df_operativo)} registros.\n'
            f'Revisar temperatura y presion en la pagina 2.'
        )
        ger_text = (
            f'La estabilidad global fue de {estabilidad}%.\n'
            f'La energia acumulada del periodo fue de {energia} kW.\n'
            f'Alertas utiles confirmadas por operacion: {utiles:.1f}%.\n'
            f'Incidentes cerrados: {int(stats_incidentes.get("incidentes_cerrados", 0))}.\n'
            f'Ver detalle de alarmas y ruido en pagina 3.'
        )
        pdf.set_xy(12, 76)
        pdf.multi_cell(92, 5, op_text, border=1)
        pdf.set_xy(106, 76)
        pdf.multi_cell(92, 5, ger_text, border=1)

        fig, ax = plt.subplots(figsize=(8.2, 3.1))
        recientes = df_operativo.tail(12)
        ax.plot(recientes['hora'], recientes['temp_suave'], color='#c2410c', marker='o', linewidth=2.2, label='Temp EMA')
        ax.plot(recientes['hora'], recientes['presion_suave'], color='#1d4ed8', marker='o', linewidth=2.2, label='Presion EMA')
        ax.set_title('Vista rapida de las ultimas mediciones', fontweight='bold')
        ax.grid(True, linestyle='--', alpha=0.35)
        ax.legend()
        plt.xticks(rotation=30, ha='right')
        fig.patch.set_facecolor('white')
        fig.tight_layout()
        path = self._save_fig(fig)
        pdf.image(path, x=16, y=108, w=178)
        os.remove(path)

    def _pagina_tendencias(self, pdf: ReportePDF, df_operativo: pd.DataFrame) -> None:
        pdf.add_page()
        self._section_title(
            pdf,
            '2. Tendencias Criticas',
            'Distribuye temperatura, presion y carga en una sola lectura visual para el operario.',
        )

        if df_operativo.empty:
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(0, 8, 'Sin datos para tendencias.', new_x="LMARGIN", new_y="NEXT")
            return

        resumen = (
            df_operativo.groupby('hora')
            .agg(
                temp=('temp_suave', 'mean'),
                pres=('presion_suave', 'mean'),
                carga=('corriente_suave', 'mean'),
            )
            .reset_index()
            .tail(12)
        )

        fig, axes = plt.subplots(3, 1, figsize=(8.3, 6.5), sharex=True)
        series = [
            ('temp', '#c2410c', 'Temperatura suavizada', 'C'),
            ('pres', '#1d4ed8', 'Presion suavizada', 'PSI'),
            ('carga', '#047857', 'Corriente suavizada', 'A'),
        ]
        for ax, (col, color, title, ylabel) in zip(axes, series):
            ax.plot(resumen['hora'], resumen[col], color=color, marker='o', linewidth=2.2)
            ax.set_title(title, loc='left', fontweight='bold', fontsize=10)
            ax.set_ylabel(ylabel)
            ax.grid(True, linestyle='--', alpha=0.35)
        plt.xticks(rotation=35, ha='right')
        fig.patch.set_facecolor('white')
        fig.tight_layout()
        path = self._save_fig(fig)
        pdf.image(path, x=15, y=38, w=180)
        os.remove(path)

        top_formulas = df_operativo['id_formula'].value_counts().head(5)
        rows = [[str(formula), str(int(total))] for formula, total in top_formulas.items()]
        pdf.set_xy(12, 216)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(17, 24, 39)
        pdf.cell(0, 6, 'Formulas con mayor presencia')
        pdf.ln(7)
        self._small_table(pdf, ['Formula', 'Registros'], rows, [35, 35])

    def _pagina_alarmas(self, pdf: ReportePDF, df_fatiga: pd.DataFrame, df_historial: pd.DataFrame) -> None:
        pdf.add_page()
        self._section_title(
            pdf,
            '3. Alarmas y Supresion de Ruido',
            'Esta pagina explica rapido si el sistema alerta demasiado o si esta filtrando bien el ruido.',
        )

        if df_fatiga.empty:
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(0, 8, 'Sin desviaciones registradas.', new_x="LMARGIN", new_y="NEXT")
            return

        top = df_fatiga.head(6).copy()
        labels = top.apply(lambda r: f"M{r['id_maquina']}-F{r['id_formula']}", axis=1)

        fig, ax = plt.subplots(figsize=(8.2, 3.6))
        ax.bar(labels, top['desvio'], color='#fb923c', label='Desvios')
        ax.plot(labels, top['alarma'], color='#111827', marker='o', linewidth=2.2, label='Alarmas')
        ax.set_title('Desvios vs alarmas emitidas', fontweight='bold')
        ax.grid(axis='y', linestyle='--', alpha=0.35)
        ax.legend()
        plt.xticks(rotation=30, ha='right')
        fig.patch.set_facecolor('white')
        fig.tight_layout()
        path = self._save_fig(fig)
        pdf.image(path, x=16, y=38, w=178)
        os.remove(path)

        rows = []
        for _, row in top.iterrows():
            rows.append([
                str(row['id_maquina']),
                str(row['id_formula']),
                str(int(row['desvio'])),
                str(int(row['alarma'])),
                f"{row['ruido_evitado']:.1f}%",
            ])
        pdf.set_xy(12, 138)
        self._small_table(pdf, ['Maq', 'Formula', 'Desvios', 'Alarmas', 'Ruido'], rows, [22, 34, 25, 25, 28])

        ruido_prom = round(top['ruido_evitado'].mean(), 1)
        pdf.set_xy(12, 188)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(17, 24, 39)
        pdf.set_fill_color(241, 245, 249)
        pdf.multi_cell(
            186,
            5,
            f'Lectura gerencial:\n'
            f'El sistema evito en promedio {ruido_prom}% del ruido operacional '
            f'en las desviaciones observadas.',
            border=1,
            fill=True,
        )

        if not df_historial.empty:
            feedback_df = df_historial[df_historial['feedback_operario'].fillna('').astype(str).str.strip().ne('')].copy()
            utiles = int((feedback_df['feedback_operario'] == 'UTIL').sum())
            falsos = int((feedback_df['feedback_operario'] == 'FALSO_POSITIVO').sum())
            mtto = int((feedback_df['feedback_operario'] == 'FALLA_MECANICA').sum())
            pdf.set_xy(12, 216)
            self._small_table(
                pdf,
                ['Feedback', 'Conteo'],
                [['Util', str(utiles)], ['Falso positivo', str(falsos)], ['Mantenimiento', str(mtto)]],
                [48, 28],
            )

    def _pagina_gerencial(
        self,
        pdf: ReportePDF,
        df_operativo: pd.DataFrame,
        data_loader: DataLoader,
        df_historial: pd.DataFrame,
        stats_incidentes: dict,
    ) -> None:
        pdf.add_page()
        self._section_title(
            pdf,
            '4. Lectura Gerencial y Gobernanza',
            'Cierra el reporte con energia, formulas y una conclusion clara para toma de decisiones.',
        )

        if df_operativo.empty:
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(0, 8, 'Sin datos para cierre gerencial.', new_x="LMARGIN", new_y="NEXT")
            return

        energia_total = round(df_operativo['kw_h_proceso'].sum(), 1)
        retorno_pct = round(df_operativo['retornando'].mean() * 100, 1)
        p95_corriente = round(df_operativo['corriente_suave'].quantile(0.95), 1)
        utiles = self._porcentaje_feedback(df_historial, 'UTIL')
        falsos = self._porcentaje_feedback(df_historial, 'FALSO_POSITIVO')
        mtto = self._porcentaje_feedback(df_historial, 'FALLA_MECANICA')

        self._card(pdf, 12, 38, 43, 22, 'Energia acumulada', f'{energia_total} kW', (29, 78, 137))
        self._card(pdf, 60, 38, 43, 22, 'Retorno fuera spec', f'{retorno_pct}%', (185, 28, 28))
        self._card(pdf, 108, 38, 43, 22, 'Feedback util', f'{utiles:.1f}%', (22, 101, 52))
        self._card(pdf, 156, 38, 43, 22, 'P95 corriente', f'{p95_corriente} A', (17, 94, 89))

        if data_loader.formulas is None:
            data_loader.cargar_maestro_formulas()
        formulas_presentes = df_operativo['id_formula'].dropna().astype(str).unique()
        formulas_oficiales = data_loader.formulas['id_formula'].astype(str).unique()
        formulas_huerfanas = sorted([f for f in formulas_presentes if f not in formulas_oficiales and f != 'nan'])

        fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.5))
        axes[0].boxplot(df_operativo['temp_suave'].dropna(), patch_artist=True, boxprops=dict(facecolor='#fdba74'))
        axes[0].set_title('Dispersion termica')
        axes[0].grid(True, linestyle='--', alpha=0.35)
        axes[1].boxplot(df_operativo['presion_suave'].dropna(), patch_artist=True, boxprops=dict(facecolor='#93c5fd'))
        axes[1].set_title('Dispersion de presion')
        axes[1].grid(True, linestyle='--', alpha=0.35)
        fig.patch.set_facecolor('white')
        fig.tight_layout()
        path = self._save_fig(fig)
        pdf.image(path, x=16, y=76, w=178)
        os.remove(path)

        pdf.set_xy(12, 164)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(17, 24, 39)
        pdf.cell(0, 6, 'Conclusiones ejecutivas')
        pdf.ln(7)
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(55, 65, 81)
        cierre = [
            f'Energia acumulada del periodo: {energia_total} kW.',
            f'Porcentaje medio de retorno fuera de especificacion: {retorno_pct}%.',
            f'Alertas utiles confirmadas por operacion: {utiles:.1f}%.',
            f'Falsos positivos reportados: {falsos:.1f}% | Casos de mantenimiento: {mtto:.1f}%.',
            (
                f'Incidentes totales: {int(stats_incidentes.get("total_incidentes", 0))} | '
                f'Cerrados: {int(stats_incidentes.get("incidentes_cerrados", 0))} | '
                f'Tiempo promedio de resolucion: {float(stats_incidentes.get("tiempo_promedio_resolucion_min", 0.0)):.1f} min.'
            ),
            'La dispersion termica y de presion permite ver estabilidad general de la ventana.',
        ]
        if formulas_huerfanas:
            cierre.append('Atencion: se detectaron formulas sin maestro: ' + ', '.join(formulas_huerfanas) + '.')
        else:
            cierre.append('No se detectaron formulas huerfanas en la ventana evaluada.')

        ancho_texto = 182
        for linea in cierre:
            pdf.set_x(12)
            pdf.multi_cell(ancho_texto, 5, '- ' + linea)

    def _porcentaje_feedback(self, df_historial: pd.DataFrame, categoria: str) -> float:
        """Calcula porcentaje de una categoria de feedback sobre respuestas recibidas."""
        if df_historial.empty or 'feedback_operario' not in df_historial.columns:
            return 0.0
        feedback_df = df_historial[df_historial['feedback_operario'].fillna('').astype(str).str.strip().ne('')]
        if feedback_df.empty:
            return 0.0
        return round((feedback_df['feedback_operario'] == categoria).sum() / len(feedback_df) * 100, 1)
