"""
Generador de Video de Serie Temporal
======================================
Convierte el buffer rolling de lecturas en un GIF animado para
input multimodal a Gemini, mostrando la evolución temporal de los
parámetros críticos de la peletizadora.

Por qué video en lugar de imagen estática
------------------------------------------
Una imagen fija muestra el ESTADO puntual: "temperatura = 78°C".
Un GIF animado muestra la DINÁMICA: "temperatura subió 15°C en 90
segundos con pendiente exponencial" — firma inequívoca de fallo térmico.

Gemini extrae todos los frames del GIF (image/gif) y puede detectar:
    - Pendientes exponenciales  → fallo mecánico inminente
    - Oscilaciones periódicas   → resonancia o cavitación
    - Saltos abruptos           → sensor defectuoso vs evento real
    - Tendencias sostenidas     → desgaste progresivo vs pico puntual

Variables animadas (3 subplots):
    temp_acond    → Temperatura del acondicionador (°C)  — rojo
    presion_vapor → Presión de vapor (PSI)               — azul
    corriente     → Corriente del motor (A)              — verde

Implementación: matplotlib + Pillow (sin ffmpeg, sin opencv).
Genera N keyframes progresivos donde el frame i muestra todos los
datos hasta el punto i — la curva crece de izquierda a derecha.

Parámetros por defecto:
    ventana_lecturas = 30  → ~2.5 minutos a 5s/lectura
    n_frames         = 10  → 10 keyframes × 200ms = 2s de animación
    dpi              = 72  → ~100-150 KB GIF resultante
"""

import io
import logging
import threading
from collections import deque
from typing import Optional

import matplotlib
matplotlib.use('Agg')   # Backend sin pantalla — imprescindible en servidores
import matplotlib.pyplot as plt
from PIL import Image

logger = logging.getLogger(__name__)

# Variables a incluir en el GIF: (clave_dict, etiqueta_eje, color)
_VARIABLES: list[tuple[str, str, str]] = [
    ("temp_acond",    "Temp. Acond. (°C)",  "#E74C3C"),
    ("presion_vapor", "Presión Vapor (PSI)", "#3498DB"),
    ("corriente",     "Corriente (A)",       "#27AE60"),
]

# Claves alternativas si los valores EMA están disponibles
_CLAVES_ALTERNATIVAS: dict[str, str] = {
    "temp_acond":    "temp_ema",
    "presion_vapor": "presion_ema",
    "corriente":     "corriente_ema",
}


class GeneradorVideoTelemetria:
    """
    Mantiene un buffer rolling de lecturas y genera GIFs animados
    para input multimodal a Gemini.

    Thread-safe: agregar_lectura puede llamarse desde cualquier hilo.
    generar_gif es CPU-bound y bloquea ~200-500ms según n_frames.

    Uso típico en main.py:
        # En __init__:
        self.generador_video = GeneradorVideoTelemetria()

        # En cada ciclo (siempre, no solo en alertas):
        self.generador_video.agregar_lectura(lectura)

        # Al generar prescripción:
        video_bytes = self.generador_video.generar_gif(titulo="Máquina 301")
        prescripcion = llm.diagnosticar_con_herramientas(..., video_bytes=video_bytes)
    """

    def __init__(
        self,
        ventana_lecturas: int = 30,
        n_frames: int = 10,
    ) -> None:
        self._buffer: deque = deque(maxlen=ventana_lecturas)
        self._n_frames      = n_frames
        self._lock          = threading.Lock()
        logger.info(
            "[VIDEO] GeneradorVideoTelemetria iniciado — "
            "ventana=%d lecturas | frames=%d | ~%.0fs de datos a 5s/lectura",
            ventana_lecturas, n_frames, ventana_lecturas * 5,
        )

    # -----------------------------------------------------------------------
    # Ingesta de datos
    # -----------------------------------------------------------------------

    def agregar_lectura(self, lectura: dict) -> None:
        """
        Agrega una lectura al buffer rolling.

        Prioriza valores EMA (suavizados) sobre valores crudos para
        que la animación muestre tendencias, no ruido de sensor.
        Las lecturas más antiguas se descartan automáticamente al
        superar ventana_lecturas (deque maxlen).
        """
        punto: dict[str, float] = {}
        for clave, _, _ in _VARIABLES:
            alt = _CLAVES_ALTERNATIVAS.get(clave, clave)
            # Preferir EMA si está disponible; fallback al valor crudo
            valor = lectura.get(alt) or lectura.get(clave, 0)
            try:
                punto[clave] = float(valor)
            except (TypeError, ValueError):
                punto[clave] = 0.0

        with self._lock:
            self._buffer.append(punto)

    def hay_suficientes_datos(self, minimo: int = 10) -> bool:
        """True si el buffer tiene al menos `minimo` lecturas acumuladas."""
        with self._lock:
            return len(self._buffer) >= minimo

    # -----------------------------------------------------------------------
    # Generación del GIF
    # -----------------------------------------------------------------------

    def generar_gif(self, titulo: str = "") -> Optional[bytes]:
        """
        Genera un GIF animado con n_frames keyframes progresivos.

        Cada frame i muestra los datos desde el inicio hasta el punto i
        (curva creciente), permitiendo al LLM observar cómo evoluciona
        la serie temporal completa — no solo el estado final.

        Args:
            titulo: Texto que aparece en la parte superior del GIF.
                    Recomendado: "Máquina 301 | Últimas 30 lecturas"

        Returns:
            Bytes del GIF animado (image/gif), o None si hay insuficientes datos.
        """
        with self._lock:
            buffer = list(self._buffer)

        n = len(buffer)
        if n < 10:
            logger.debug(
                "[VIDEO] Buffer insuficiente (%d lecturas, mínimo 10). "
                "Acumulando más datos antes de generar GIF.",
                n,
            )
            return None

        # Extraer series para cada variable
        series: dict[str, list[float]] = {
            clave: [r.get(clave, 0.0) for r in buffer]
            for clave, _, _ in _VARIABLES
        }

        # Calcular cortes de keyframes (progresivos, equidistantes)
        paso   = max(1, n // self._n_frames)
        cortes = list(range(paso, n + 1, paso))
        if cortes[-1] < n:
            cortes.append(n)   # Asegurar que el último frame muestra todos los datos

        frames_pil: list[Image.Image] = []

        for corte in cortes:
            xs = list(range(corte))
            fig, axes = plt.subplots(
                len(_VARIABLES), 1,
                figsize=(7, 4.5),
                tight_layout=True,
                sharex=True,
            )

            for ax, (clave, etiqueta, color) in zip(axes, _VARIABLES):
                ys = series[clave][:corte]

                # Línea principal
                ax.plot(xs, ys, color=color, linewidth=1.8, alpha=0.9)

                # Punto actual resaltado (último dato visible en este frame)
                if ys:
                    ax.scatter([xs[-1]], [ys[-1]], color=color, s=35, zorder=5)

                ax.set_ylabel(etiqueta, fontsize=7)
                ax.tick_params(labelsize=6)
                ax.set_xlim(0, n - 1)
                ax.grid(True, alpha=0.2, linewidth=0.5)

            axes[-1].set_xlabel(f"t-{n} lecturas → ahora", fontsize=7)

            if titulo:
                fig.suptitle(titulo, fontsize=8, fontweight='bold', y=1.01)

            # Renderizar este frame en memoria como PNG
            buf_frame = io.BytesIO()
            fig.savefig(buf_frame, format='png', dpi=72, bbox_inches='tight')
            plt.close(fig)
            buf_frame.seek(0)

            # Convertir a RGB (no RGBA — GIF no soporta alpha real y produce artifacts)
            img = Image.open(buf_frame)
            frames_pil.append(img.convert('RGB'))
            img.close()

        if not frames_pil:
            return None

        # Ensamblar GIF animado
        gif_buf = io.BytesIO()
        frames_pil[0].save(
            gif_buf,
            format='GIF',
            append_images=frames_pil[1:],
            save_all=True,
            duration=200,    # ms por frame → 2 segundos para 10 frames
            loop=0,          # Repetición infinita
            optimize=True,
        )
        gif_buf.seek(0)
        gif_bytes = gif_buf.read()

        logger.info(
            "[VIDEO] GIF generado: %d frames | %d lecturas | %.1f KB",
            len(frames_pil), n, len(gif_bytes) / 1024,
        )
        return gif_bytes
