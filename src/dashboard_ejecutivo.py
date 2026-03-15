"""
Dashboard ejecutivo local en HTML para sustentacion y seguimiento operativo.
"""

from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class DashboardEjecutivo:
    """Genera un dashboard HTML local a partir de la ultima lectura procesada."""

    def __init__(self, config: ConfigLoader | None = None) -> None:
        self.config = config or ConfigLoader()
        self.ruta_dashboard: Path = self.config.logs_dir / 'dashboard_ejecutivo.html'

    def actualizar_dashboard(
        self,
        lectura: dict[str, Any],
        estado_global: str,
        severidad: str,
        indice_salud: int,
        etiqueta_salud: str,
        estado_temperatura: str,
        estado_presion: str,
        porcentaje_carga: float,
        tendencia_temp: str,
        tendencia_pres: str,
        pronostico: str,
        pronostico_nivel: str,
        causa_probable: str,
        alertas_confirmadas: list[Any],
        estadisticas_feedback: dict[str, Any],
    ) -> None:
        """Escribe el dashboard HTML con la ultima lectura y el contexto ejecutivo."""
        alertas_html = self._render_alertas(alertas_confirmadas)
        feedback_html = self._render_feedback(estadisticas_feedback)
        historial = lectura.get('historial_reciente', [])
        tendencia_html = self._render_tendencias(historial)

        color_severidad = {
            'INFORMATIVA': '#1d4ed8',
            'PREVENTIVA': '#b45309',
            'ALTA': '#b91c1c',
            'CRITICA': '#7f1d1d',
        }.get(severidad, '#334155')

        contenido = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="5">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dashboard Ejecutivo IA</title>
  <style>
    :root {{
      --fondo: #f5efe5;
      --panel: #fffdf8;
      --borde: #e7dcc8;
      --texto: #172033;
      --muted: #5b6578;
      --accent: {color_severidad};
      --ok: #047857;
      --warn: #b45309;
      --danger: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background: linear-gradient(180deg, #f6f1e8 0%, #efe5d7 100%);
      color: var(--texto);
    }}
    .wrap {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 28px;
    }}
    .hero {{
      background: linear-gradient(135deg, #172033 0%, #243b67 100%);
      color: white;
      border-radius: 24px;
      padding: 24px 28px;
      box-shadow: 0 18px 40px rgba(23, 32, 51, 0.18);
      margin-bottom: 22px;
    }}
    .hero h1 {{
      margin: 0 0 8px 0;
      font-size: 32px;
    }}
    .hero p {{
      margin: 0;
      color: #dbeafe;
      font-size: 15px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--borde);
      border-radius: 20px;
      padding: 18px;
      box-shadow: 0 10px 30px rgba(111, 92, 63, 0.08);
    }}
    .metric {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 10px;
      font-weight: 700;
    }}
    .value {{
      font-size: 28px;
      font-weight: 800;
    }}
    .accent {{
      color: var(--accent);
    }}
    .section {{
      display: grid;
      grid-template-columns: 1.25fr 0.95fr;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .title {{
      margin: 0 0 14px 0;
      font-size: 18px;
      font-weight: 800;
    }}
    .pill {{
      display: inline-block;
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: #eef2ff;
      color: #3730a3;
      margin-right: 8px;
      margin-bottom: 8px;
    }}
    .list {{
      margin: 0;
      padding-left: 18px;
      line-height: 1.6;
    }}
    .mini-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .trend-line {{
      font-size: 14px;
      padding: 10px 0;
      border-bottom: 1px dashed #e5e7eb;
    }}
    .table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    .table th, .table td {{
      border-bottom: 1px solid #ede7db;
      text-align: left;
      padding: 10px 6px;
    }}
    .table th {{
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    @media (max-width: 980px) {{
      .grid, .section, .mini-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>Dashboard Ejecutivo IA</h1>
      <p>Planta {html.escape(str(lectura['id_planta']))} | Maquina {html.escape(str(lectura['id_maquina']))} | Formula {html.escape(str(lectura['id_formula']))} ({html.escape(str(lectura['codigo_producto']))}) | Lectura {lectura['numero']}</p>
    </div>

    <div class="grid">
      <div class="card">
        <div class="metric">Estado Global</div>
        <div class="value accent">{html.escape(estado_global)}</div>
      </div>
      <div class="card">
        <div class="metric">Severidad</div>
        <div class="value accent">{html.escape(severidad)}</div>
      </div>
      <div class="card">
        <div class="metric">Indice de Salud</div>
        <div class="value">{indice_salud}/100</div>
        <div>{html.escape(etiqueta_salud)}</div>
      </div>
      <div class="card">
        <div class="metric">Pronostico a 5 Min</div>
        <div class="value">{html.escape(pronostico_nivel)}</div>
        <div>{html.escape(pronostico)}</div>
      </div>
    </div>

    <div class="section">
      <div class="card">
        <h2 class="title">Estado Actual del Proceso</h2>
        <div class="mini-grid">
          <div>
            <div class="metric">Temperatura EMA</div>
            <div class="value">{lectura['temp_ema']:.1f} C</div>
            <div>{html.escape(estado_temperatura)}</div>
          </div>
          <div>
            <div class="metric">Presion EMA</div>
            <div class="value">{lectura['presion_ema']:.1f} PSI</div>
            <div>{html.escape(estado_presion)}</div>
          </div>
          <div>
            <div class="metric">Corriente EMA</div>
            <div class="value">{lectura['corriente_ema']:.1f} A</div>
            <div>Carga {porcentaje_carga:.1f}%</div>
          </div>
          <div>
            <div class="metric">Causa Probable</div>
            <div>{html.escape(causa_probable)}</div>
          </div>
        </div>
      </div>
      <div class="card">
        <h2 class="title">Tendencia y Riesgo</h2>
        <div class="trend-line"><strong>Temperatura:</strong> {html.escape(tendencia_temp)}</div>
        <div class="trend-line"><strong>Presion:</strong> {html.escape(tendencia_pres)}</div>
        <div class="trend-line"><strong>Pronostico:</strong> {html.escape(pronostico)}</div>
      </div>
    </div>

    <div class="section">
      <div class="card">
        <h2 class="title">Ultimas Alertas Confirmadas</h2>
        {alertas_html}
      </div>
      <div class="card">
        <h2 class="title">Feedback del Operario</h2>
        {feedback_html}
      </div>
    </div>

    <div class="card">
      <h2 class="title">Ventana Reciente de Tendencias</h2>
      {tendencia_html}
    </div>
  </div>
</body>
</html>
"""

        self.ruta_dashboard.write_text(contenido, encoding='utf-8')
        logger.info("Dashboard ejecutivo actualizado en %s", self.ruta_dashboard)

    def obtener_html(self) -> bytes:
        """Devuelve el dashboard actual como bytes para envio por Telegram."""
        if not self.ruta_dashboard.exists():
            return b""
        return self.ruta_dashboard.read_bytes()

    def _render_alertas(self, alertas_confirmadas: list[Any]) -> str:
        activas = [a for a in alertas_confirmadas if not getattr(a, 'es_retorno_normal', False)]
        if not activas:
            return "<p>No hay alertas confirmadas en esta lectura.</p>"

        filas = []
        for alerta in activas:
            filas.append(
                "<tr>"
                f"<td>{html.escape(alerta.tipo_alerta.value)}</td>"
                f"<td>{html.escape(alerta.variable)}</td>"
                f"<td>{alerta.valor_suavizado:.2f}</td>"
                f"<td>{alerta.porcentaje_carga:.1f}%</td>"
                "</tr>"
            )
        return (
            "<table class='table'>"
            "<thead><tr><th>Tipo</th><th>Variable</th><th>Valor EMA</th><th>Carga</th></tr></thead>"
            f"<tbody>{''.join(filas)}</tbody></table>"
        )

    def _render_feedback(self, estadisticas_feedback: dict[str, Any]) -> str:
        total = int(estadisticas_feedback.get('total_alertas', 0))
        utiles = float(estadisticas_feedback.get('porcentaje_utiles', 0.0))
        falsos = float(estadisticas_feedback.get('porcentaje_falsos_positivos', 0.0))
        mantenimiento = 0
        if total > 0:
            conteos = estadisticas_feedback.get('feedback_por_tipo', {})
            mantenimiento = int(conteos.get('FALLA_MECANICA', 0))

        return (
            f"<span class='pill'>Alertas registradas: {total}</span>"
            f"<span class='pill'>Utiles: {utiles:.1f}%</span>"
            f"<span class='pill'>Falsos positivos: {falsos:.1f}%</span>"
            f"<span class='pill'>Mantenimiento: {mantenimiento}</span>"
        )

    def _render_tendencias(self, historial: list[dict[str, Any]]) -> str:
        if not historial:
            return "<p>Sin historial reciente.</p>"

        filas = []
        for item in historial[-6:]:
            filas.append(
                "<tr>"
                f"<td>{html.escape(str(item.get('timestamp', '')))}</td>"
                f"<td>{float(item.get('temp_ema', item.get('temp_acond', 0.0))):.1f}</td>"
                f"<td>{float(item.get('presion_ema', item.get('presion_vapor', 0.0))):.1f}</td>"
                f"<td>{float(item.get('corriente_ema', item.get('corriente', 0.0))):.1f}</td>"
                "</tr>"
            )
        return (
            "<table class='table'>"
            "<thead><tr><th>Timestamp</th><th>Temp EMA</th><th>Presion EMA</th><th>Corriente EMA</th></tr></thead>"
            f"<tbody>{''.join(filas)}</tbody></table>"
        )
