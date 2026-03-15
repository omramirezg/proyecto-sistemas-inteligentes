"""
Generador de graficas para monitoreo y reportes.
"""

import io
import logging

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

plt.rcParams.update({
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.edgecolor': '#444444',
    'axes.labelcolor': '#222222',
    'axes.titlesize': 14,
    'axes.labelsize': 11,
    'xtick.color': '#333333',
    'ytick.color': '#333333',
    'text.color': '#222222',
    'grid.color': '#cccccc',
    'grid.alpha': 0.5,
    'legend.facecolor': 'white',
    'legend.edgecolor': '#cccccc',
    'legend.fontsize': 9,
    'font.family': 'sans-serif',
    'font.size': 10,
})


class GeneradorGraficas:
    """Genera graficas PNG en memoria."""

    COLOR_TEMPERATURA = '#1565c0'
    COLOR_PRESION = '#c62828'
    COLOR_PUNTO_ALERTA = '#ff6f00'

    NOMBRES_VARIABLES = {
        'presion_vapor': 'Presion de Vapor (PSI)',
        'temp_acond': 'Temperatura del Acondicionador (C)',
        'corriente': 'Corriente del Motor (A)',
    }

    def generar_panel_multimodal_telegram(
        self,
        datos_recientes: pd.DataFrame,
        id_planta: str,
        id_maquina: str,
        id_formula: str,
        codigo_producto: str,
        numero_lectura: int,
        temp_actual: float,
        presion_actual: float,
        corriente_actual: float,
        t_min: float,
        t_max: float,
        p_min: float,
        p_max: float,
        porcentaje_carga: float,
        estado_temperatura: str,
        estado_presion: str,
        estado_global: str,
        severidad: str,
        causa_probable: str,
        tendencia_temp: str,
        tendencia_pres: str,
        pronostico: str,
        indice_salud: int,
        etiqueta_salud: str,
    ) -> bytes:
        """Genera un panel visual tipo evidencia multimodal para Telegram."""
        fig = plt.figure(figsize=(12.4, 8.8), dpi=150)
        gs = fig.add_gridspec(
            2,
            2,
            height_ratios=[2.15, 1.35],
            width_ratios=[1, 1],
            hspace=0.30,
            wspace=0.22,
        )

        ax_temp = fig.add_subplot(gs[0, 0])
        ax_pres = fig.add_subplot(gs[0, 1])
        ax_kpi = fig.add_subplot(gs[1, :])

        try:
            fig.patch.set_facecolor('#f4efe6')

            x = list(range(1, len(datos_recientes) + 1))
            columna_temp = 'temp_ema' if 'temp_ema' in datos_recientes.columns else 'temp_acond'
            columna_pres = 'presion_ema' if 'presion_ema' in datos_recientes.columns else 'presion_vapor'
            temps = datos_recientes[columna_temp].astype(float).tolist()
            presiones = datos_recientes[columna_pres].astype(float).tolist()

            for ax in (ax_temp, ax_pres):
                ax.set_facecolor('#fbfaf7')
                for spine in ax.spines.values():
                    spine.set_color('#d6d3d1')
                    spine.set_linewidth(1.2)

            ax_temp.axhspan(t_min, t_max, color='#d9f99d', alpha=0.45)
            ax_temp.plot(
                x,
                temps,
                color='#1d4ed8',
                linewidth=3.0,
                marker='o',
                markersize=7.5,
                markerfacecolor='#60a5fa',
                markeredgecolor='white',
                markeredgewidth=1.5,
            )
            ax_temp.fill_between(x, temps, [min(temps)] * len(temps), color='#bfdbfe', alpha=0.18)
            ax_temp.scatter(
                [x[-1]],
                [temp_actual],
                color='#f97316',
                s=180,
                zorder=5,
                edgecolors='white',
                linewidth=1.8,
            )
            ax_temp.set_title('Tendencia Reciente de Temperatura', fontweight='bold', fontsize=15, color='#0f172a')
            ax_temp.set_xlabel('Lectura')
            ax_temp.set_ylabel('C')
            ax_temp.grid(True, linestyle='--', alpha=0.22, linewidth=0.8)
            ax_temp.text(
                0.02, 0.93,
                f'Banda: {t_min:.1f} - {t_max:.1f} C\nEstado: {estado_temperatura}',
                transform=ax_temp.transAxes,
                va='top',
                fontsize=10.5,
                fontweight='bold',
                color='#1e293b',
                bbox=dict(facecolor='#ffffff', edgecolor='#cbd5e1', boxstyle='round,pad=0.42'),
            )
            ax_temp.annotate(
                f'{temp_actual:.1f}',
                xy=(x[-1], temp_actual),
                xytext=(10, 10),
                textcoords='offset points',
                fontsize=10,
                fontweight='bold',
                color='#b45309',
                bbox=dict(facecolor='#ffedd5', edgecolor='#fdba74', boxstyle='round,pad=0.25'),
            )

            ax_pres.axhspan(p_min, p_max, color='#dcfce7', alpha=0.50)
            ax_pres.plot(
                x,
                presiones,
                color='#b91c1c',
                linewidth=3.0,
                marker='o',
                markersize=7.5,
                markerfacecolor='#f87171',
                markeredgecolor='white',
                markeredgewidth=1.5,
            )
            ax_pres.fill_between(x, presiones, [min(presiones)] * len(presiones), color='#fecaca', alpha=0.16)
            ax_pres.scatter(
                [x[-1]],
                [presion_actual],
                color='#f97316',
                s=180,
                zorder=5,
                edgecolors='white',
                linewidth=1.8,
            )
            ax_pres.set_title('Tendencia Reciente de Presion', fontweight='bold', fontsize=15, color='#0f172a')
            ax_pres.set_xlabel('Lectura')
            ax_pres.set_ylabel('PSI')
            ax_pres.grid(True, linestyle='--', alpha=0.22, linewidth=0.8)
            ax_pres.text(
                0.02, 0.93,
                f'Banda: {p_min:.1f} - {p_max:.1f} PSI\nEstado: {estado_presion}',
                transform=ax_pres.transAxes,
                va='top',
                fontsize=10.5,
                fontweight='bold',
                color='#1e293b',
                bbox=dict(facecolor='#ffffff', edgecolor='#cbd5e1', boxstyle='round,pad=0.42'),
            )
            ax_pres.annotate(
                f'{presion_actual:.1f}',
                xy=(x[-1], presion_actual),
                xytext=(10, 10),
                textcoords='offset points',
                fontsize=10,
                fontweight='bold',
                color='#b45309',
                bbox=dict(facecolor='#ffedd5', edgecolor='#fdba74', boxstyle='round,pad=0.25'),
            )

            ax_kpi.set_facecolor('#f8f5ee')
            ax_kpi.axis('off')
            color_severidad = {
                'INFORMATIVA': '#2563eb',
                'PREVENTIVA': '#d97706',
                'ALTA': '#dc2626',
                'CRITICA': '#7f1d1d',
            }.get(severidad, '#dc2626')
            color_salud = {
                'ESTABLE': '#0f766e',
                'VIGILANCIA': '#b45309',
                'RIESGO': '#dc2626',
                'CRITICO': '#7f1d1d',
            }.get(etiqueta_salud, '#0f766e')
            titulo = (
                f'PAQUETE MULTIMODAL | Lectura {numero_lectura} | '
                f'Planta {id_planta} | Maquina {id_maquina} | Formula {id_formula} ({codigo_producto})'
            )
            ax_kpi.text(
                0.5,
                0.91,
                titulo,
                color='#111827',
                fontsize=13,
                fontweight='bold',
                ha='center',
            )

            tarjetas = [
                (0.03, 0.54, 0.18, 0.22, '#1d4ed8', 'Estado global', estado_global),
                (0.24, 0.54, 0.15, 0.22, color_severidad, 'Severidad', severidad),
                (0.42, 0.54, 0.15, 0.22, color_salud, 'Salud IA', f'{indice_salud}/100 | {etiqueta_salud}'),
                (0.60, 0.54, 0.17, 0.22, '#0f766e', 'Temp / Pres', f'{temp_actual:.1f} C | {presion_actual:.1f} PSI'),
                (0.79, 0.54, 0.18, 0.22, '#7c3aed', 'Carga / Corriente', f'{porcentaje_carga:.1f}% | {corriente_actual:.1f} A'),
            ]

            for x0, y0, w, h, color, label, valor in tarjetas:
                sombra = plt.Rectangle(
                    (x0 + 0.008, y0 - 0.012),
                    w,
                    h,
                    transform=ax_kpi.transAxes,
                    color='#cbd5e1',
                    alpha=0.35,
                )
                rect = plt.Rectangle(
                    (x0, y0),
                    w,
                    h,
                    transform=ax_kpi.transAxes,
                    color=color,
                    alpha=0.96,
                )
                ax_kpi.add_patch(sombra)
                ax_kpi.add_patch(rect)
                ax_kpi.text(
                    x0 + 0.016,
                    y0 + 0.14,
                    label,
                    transform=ax_kpi.transAxes,
                    color='white',
                    fontsize=9.5,
                    fontweight='bold',
                )
                ax_kpi.text(
                    x0 + 0.016,
                    y0 + 0.052,
                    valor,
                    transform=ax_kpi.transAxes,
                    color='white',
                    fontsize=10.5,
                    fontweight='bold',
                )

            ax_kpi.text(
                0.05,
                0.31,
                f'Causa probable: {causa_probable}',
                color='#1f2937',
                fontsize=11,
                fontweight='bold',
                bbox=dict(facecolor='#ffffff', edgecolor='#d6d3d1', boxstyle='round,pad=0.42'),
            )
            ax_kpi.text(
                0.05,
                0.15,
                f'Tendencia temperatura: {tendencia_temp}',
                color='#334155',
                fontsize=10.8,
                fontweight='bold',
            )
            ax_kpi.text(
                0.05,
                0.06,
                f'Tendencia presion: {tendencia_pres} | Pronostico: {pronostico}',
                color='#334155',
                fontsize=10.8,
                fontweight='bold',
            )

            fig.subplots_adjust(left=0.055, right=0.945, top=0.95, bottom=0.06)
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
            buffer.seek(0)
            imagen_bytes = buffer.getvalue()
            logger.info(
                "Panel multimodal generado para planta %s maquina %s: %.1f KB",
                id_planta,
                id_maquina,
                len(imagen_bytes) / 1024,
            )
            return imagen_bytes
        except Exception as e:
            logger.error("Error generando panel multimodal: %s", e)
            raise
        finally:
            plt.close(fig)

    def generar_grafica_debug_telegram(
        self,
        id_planta: str,
        id_maquina: str,
        id_formula: str,
        codigo_producto: str,
        temperatura: float,
        presion: float,
        corriente: float,
        numero_lectura: int,
    ) -> bytes:
        """Genera una imagen muy simple para validar Telegram."""
        fig, ax = plt.subplots(figsize=(10, 6), dpi=140)
        fig.patch.set_facecolor('white')
        ax.set_facecolor('white')

        try:
            categorias = ['Temperatura', 'Presion', 'Corriente']
            valores = [temperatura, presion, corriente]
            colores = [self.COLOR_TEMPERATURA, self.COLOR_PRESION, '#2e7d32']

            barras = ax.bar(categorias, valores, color=colores, edgecolor='black', linewidth=1.0)
            ax.set_title(
                f'Lectura {numero_lectura} | Planta {id_planta} | Maquina {id_maquina}\n'
                f'Formula {id_formula} ({codigo_producto})',
                fontsize=15,
                fontweight='bold',
            )
            ax.set_ylabel('Valor')
            ax.grid(axis='y', linestyle='--', alpha=0.35)
            ax.set_axisbelow(True)

            for barra, valor, unidad in zip(barras, valores, ['C', 'PSI', 'A']):
                ax.text(
                    barra.get_x() + barra.get_width() / 2.0,
                    barra.get_height(),
                    f'{valor:.2f} {unidad}',
                    ha='center',
                    va='bottom',
                    fontsize=12,
                    fontweight='bold',
                    color='#111111',
                )

            ax.text(
                0.02,
                0.02,
                'Prueba minima de imagen para Telegram',
                transform=ax.transAxes,
                fontsize=11,
                color='#333333',
                bbox=dict(facecolor='#f5f5f5', edgecolor='#999999', boxstyle='round,pad=0.25'),
            )

            fig.tight_layout()
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png', bbox_inches='tight', facecolor='white')
            buffer.seek(0)
            imagen_bytes = buffer.getvalue()
            logger.info(
                "Grafica debug Telegram generada para planta %s maquina %s: %.1f KB",
                id_planta,
                id_maquina,
                len(imagen_bytes) / 1024,
            )
            return imagen_bytes
        except Exception as e:
            logger.error("Error generando grafica debug Telegram: %s", e)
            raise
        finally:
            plt.close(fig)

    def generar_grafica_monitoreo(
        self,
        datos_recientes: pd.DataFrame,
        id_planta: str,
        id_maquina: str,
        id_formula: str,
        codigo_producto: str,
        temp_actual: float,
        presion_actual: float,
        columna_tiempo: str = 'fecha_registro',
    ) -> bytes:
        """Genera una grafica visible aun con pocas muestras."""
        fig, axes = plt.subplots(2, 1, figsize=(10, 7), dpi=140)
        fig.patch.set_facecolor('white')

        try:
            columna_temp = 'temp_ema' if 'temp_ema' in datos_recientes.columns else 'temp_acond'
            columna_pres = 'presion_ema' if 'presion_ema' in datos_recientes.columns else 'presion_vapor'
            temperaturas = datos_recientes[columna_temp].astype(float).tolist()
            presiones = datos_recientes[columna_pres].astype(float).tolist()
            x = list(range(1, len(datos_recientes) + 1))
            etiquetas_x = [str(i) for i in x]

            series = [
                (axes[0], temperaturas, self.COLOR_TEMPERATURA, 'Temperatura', temp_actual, 'C'),
                (axes[1], presiones, self.COLOR_PRESION, 'Presion', presion_actual, 'PSI'),
            ]

            for ax, valores, color, titulo, valor_actual, unidad in series:
                ax.set_facecolor('white')
                ax.plot(
                    x,
                    valores,
                    color=color,
                    linewidth=3,
                    marker='o',
                    markersize=9,
                    markerfacecolor=color,
                    markeredgecolor='white',
                    markeredgewidth=1.5,
                    zorder=3,
                )
                ax.scatter(
                    [x[-1]],
                    [valor_actual],
                    color=self.COLOR_PUNTO_ALERTA,
                    s=220,
                    zorder=4,
                    edgecolors='black',
                    linewidth=1.2,
                )
                ax.grid(True, linestyle='--', linewidth=0.8, alpha=0.5)
                ax.set_title(f'{titulo} ({unidad})', fontsize=12, fontweight='bold')
                ax.set_xlabel('Lectura')
                ax.set_ylabel(unidad)
                ax.set_xticks(x)
                ax.set_xticklabels(etiquetas_x)
                ax.margins(x=0.2, y=0.3)
                ax.text(
                    0.02,
                    0.88,
                    f'Valor actual: {valor_actual:.2f} {unidad}',
                    transform=ax.transAxes,
                    fontsize=11,
                    fontweight='bold',
                    color='#111111',
                    bbox=dict(
                        facecolor='#fff3cd',
                        edgecolor='#d39e00',
                        boxstyle='round,pad=0.35',
                    ),
                )

            fig.suptitle(
                f'Monitoreo Planta {id_planta} | Maquina {id_maquina} | '
                f'Formula {id_formula} ({codigo_producto})',
                fontsize=14,
                fontweight='bold',
            )
            fig.tight_layout(rect=[0, 0, 1, 0.96])

            buffer = io.BytesIO()
            fig.savefig(buffer, format='png', bbox_inches='tight', facecolor='white')
            buffer.seek(0)
            imagen_bytes = buffer.getvalue()

            logger.info(
                "Grafica de monitoreo generada para planta %s maquina %s: %.1f KB",
                id_planta,
                id_maquina,
                len(imagen_bytes) / 1024,
            )
            return imagen_bytes
        except Exception as e:
            logger.error("Error generando grafica de monitoreo: %s", e)
            raise
        finally:
            plt.close(fig)

    def generar_grafica_alerta(
        self,
        datos_recientes: pd.DataFrame,
        variable: str,
        id_planta: str,
        id_maquina: str,
        id_formula: str,
        codigo_producto: str,
        valor_suavizado_actual: float,
        limite_min: float,
        limite_max: float,
        columna_tiempo: str = 'fecha_registro',
    ) -> bytes:
        """Compatibilidad con el modo de alertas original."""
        fig, ax = plt.subplots(figsize=(10, 5), dpi=140)
        nombre_variable = self.NOMBRES_VARIABLES.get(variable, variable)

        try:
            valores = datos_recientes[variable].astype(float).tolist()
            x = list(range(1, len(valores) + 1))

            ax.plot(
                x,
                valores,
                color=self.COLOR_TEMPERATURA,
                linewidth=2.5,
                marker='o',
                markersize=7,
            )
            ax.axhline(y=limite_min, color='green', linestyle='--', linewidth=1.5)
            ax.axhline(y=limite_max, color='green', linestyle='--', linewidth=1.5)
            ax.scatter([x[-1]], [valor_suavizado_actual], color=self.COLOR_PUNTO_ALERTA, s=180, zorder=5)
            ax.set_title(
                f'Planta {id_planta} | Maquina {id_maquina} | '
                f'Formula {id_formula} ({codigo_producto})\n{nombre_variable}',
                fontsize=13,
                fontweight='bold',
            )
            ax.set_xlabel('Lectura')
            ax.set_ylabel(nombre_variable)
            ax.grid(True, linestyle='--', alpha=0.5)
            ax.margins(x=0.2, y=0.25)

            buffer = io.BytesIO()
            fig.savefig(buffer, format='png', bbox_inches='tight', facecolor='white')
            buffer.seek(0)
            imagen_bytes = buffer.getvalue()

            logger.info(
                "Grafica generada para %s | Maq %s-%s | %.1f KB",
                variable,
                id_planta,
                id_maquina,
                len(imagen_bytes) / 1024,
            )
            return imagen_bytes
        except Exception as e:
            logger.error("Error generando grafica: %s", e)
            raise
        finally:
            plt.close(fig)

    def generar_graficas_reporte(
        self,
        historial: pd.DataFrame,
        periodo_inicio: str,
        periodo_fin: str,
    ) -> list[bytes]:
        """Genera las graficas del PDF."""
        graficas: list[bytes] = []

        if historial.empty:
            logger.warning("Historial vacio, no se generaran graficas de reporte.")
            return graficas

        try:
            graficas.append(
                self._grafica_alertas_por_maquina(historial, periodo_inicio, periodo_fin)
            )
            graficas.append(
                self._grafica_alertas_por_tipo(historial, periodo_inicio, periodo_fin)
            )
            graficas.append(
                self._grafica_tendencia_temporal(historial, periodo_inicio, periodo_fin)
            )
        except Exception as e:
            logger.error("Error generando graficas de reporte: %s", e)

        return graficas

    def _grafica_alertas_por_maquina(
        self,
        historial: pd.DataFrame,
        periodo_inicio: str,
        periodo_fin: str,
    ) -> bytes:
        fig, ax = plt.subplots(figsize=(10, 5), dpi=140)
        conteo = historial.groupby(['id_planta', 'id_maquina']).size().reset_index(name='total')
        labels = conteo.apply(lambda r: f"P{r['id_planta']}-M{r['id_maquina']}", axis=1)
        colores = plt.cm.plasma(np.linspace(0.2, 0.8, len(conteo)))
        bars = ax.bar(labels, conteo['total'], color=colores, edgecolor='white', linewidth=0.5)

        for bar in bars:
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height + 0.3,
                f'{int(height)}',
                ha='center',
                va='bottom',
                fontweight='bold',
                fontsize=10,
            )

        ax.set_title(
            f'Distribucion de Alertas por Maquina\nPeriodo: {periodo_inicio} - {periodo_fin}',
            fontweight='bold',
            pad=15,
        )
        ax.set_xlabel('Maquina')
        ax.set_ylabel('Total de Alertas')
        ax.grid(axis='y', alpha=0.3)
        fig.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        resultado = buffer.getvalue()
        plt.close(fig)
        return resultado

    def _grafica_alertas_por_tipo(
        self,
        historial: pd.DataFrame,
        periodo_inicio: str,
        periodo_fin: str,
    ) -> bytes:
        fig, ax = plt.subplots(figsize=(8, 6), dpi=140)
        conteo = historial['tipo_alerta'].value_counts()
        colores = ['#e91e63', '#ff5722', '#4fc3f7', '#4caf50', '#ffc107', '#9c27b0']

        wedges, texts, autotexts = ax.pie(
            conteo.values,
            labels=conteo.index,
            autopct='%1.1f%%',
            colors=colores[:len(conteo)],
            startangle=90,
            pctdistance=0.85,
            wedgeprops=dict(edgecolor='white', linewidth=1.5),
        )

        for autotext in autotexts:
            autotext.set_fontsize(10)
            autotext.set_fontweight('bold')

        ax.set_title(
            f'Distribucion por Tipo de Alerta\nPeriodo: {periodo_inicio} - {periodo_fin}',
            fontweight='bold',
            pad=15,
        )
        fig.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        resultado = buffer.getvalue()
        plt.close(fig)
        return resultado

    def _grafica_tendencia_temporal(
        self,
        historial: pd.DataFrame,
        periodo_inicio: str,
        periodo_fin: str,
    ) -> bytes:
        fig, ax = plt.subplots(figsize=(10, 5), dpi=140)
        historial_copia = historial.copy()

        if 'timestamp' in historial_copia.columns:
            historial_copia['fecha'] = pd.to_datetime(historial_copia['timestamp']).dt.date
            conteo_diario = historial_copia.groupby('fecha').size()
            ax.fill_between(conteo_diario.index, conteo_diario.values, alpha=0.3, color='#4fc3f7')
            ax.plot(
                conteo_diario.index,
                conteo_diario.values,
                color='#e91e63',
                linewidth=2,
                marker='o',
                markersize=5,
            )

        ax.set_title(
            f'Tendencia de Alertas en el Tiempo\nPeriodo: {periodo_inicio} - {periodo_fin}',
            fontweight='bold',
            pad=15,
        )
        ax.set_xlabel('Fecha')
        ax.set_ylabel('Cantidad de Alertas')
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45, ha='right')
        fig.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        resultado = buffer.getvalue()
        plt.close(fig)
        return resultado
