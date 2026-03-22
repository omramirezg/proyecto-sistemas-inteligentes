from pathlib import Path
import sys

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "presentacion_assets"
ASSETS.mkdir(exist_ok=True)

sys.path.insert(0, str((ROOT / "src").resolve()))

from generador_graficas import GeneradorGraficas


def fuente(nombre: str, tam: int):
    try:
        return ImageFont.truetype(nombre, tam)
    except Exception:
        return ImageFont.load_default()


FONT_BOLD = fuente("arialbd.ttf", 26)
FONT_SEMIBOLD = fuente("arialbd.ttf", 20)
FONT_TEXT = fuente("arial.ttf", 18)
FONT_SMALL = fuente("arial.ttf", 14)


def generar_panel():
    df = pd.read_csv(ROOT / "data" / "telemetria_planta_001.csv")
    ventana = df.iloc[:8].copy()
    ventana["temp_ema"] = ventana["temp_acond"]
    ventana["presion_ema"] = ventana["presion_vapor"]
    ventana["corriente_ema"] = ventana["corriente"]

    graficas = GeneradorGraficas()
    panel = graficas.generar_panel_multimodal_telegram(
        datos_recientes=ventana[
            [
                "fecha_registro",
                "temp_acond",
                "presion_vapor",
                "corriente",
                "temp_ema",
                "presion_ema",
                "corriente_ema",
            ]
        ],
        id_planta="001",
        id_maquina="301",
        id_formula="3360",
        codigo_producto="ZB1",
        numero_lectura=8,
        temp_actual=float(ventana.iloc[-1]["temp_acond"]),
        presion_actual=float(ventana.iloc[-1]["presion_vapor"]),
        corriente_actual=float(ventana.iloc[-1]["corriente"]),
        t_min=80.0,
        t_max=280.0,
        p_min=8.0,
        p_max=25.0,
        porcentaje_carga=67.5,
        estado_temperatura="BAJO",
        estado_presion="BAJO",
        estado_global="EN RIESGO",
        severidad="ALTA",
        causa_probable="caida de suministro de vapor o dosificacion insuficiente de energia termica",
        tendencia_temp="deterioro progresivo por debajo de banda operativa",
        tendencia_pres="deterioro progresivo por debajo de banda operativa",
        pronostico="riesgo alto de continuar fuera de banda en los proximos 5 minutos",
        indice_salud=48,
        etiqueta_salud="RIESGO",
    )
    path = ASSETS / "panel_telegram_demo.png"
    path.write_bytes(panel)
    return path


def generar_ficha_mock():
    img = Image.new("RGB", (900, 1200), "#f6f1e8")
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((50, 50, 850, 1150), radius=38, fill="#fffdf9", outline="#ddd2bf", width=3)
    draw.rounded_rectangle((80, 85, 820, 180), radius=28, fill="#8a3d30")
    draw.text((115, 108), "FICHA IA - INTERVENCION OPERATIVA", font=FONT_SEMIBOLD, fill="white")
    draw.text((115, 140), "Planta 001 | Maquina 301 | Formula 3360 (ZB1)", font=FONT_SMALL, fill="#f9ebe5")

    draw.rounded_rectangle((90, 215, 380, 330), radius=24, fill="#c44934")
    draw.text((115, 245), "Estado global", font=FONT_SMALL, fill="#ffe6df")
    draw.text((115, 275), "EN RIESGO", font=FONT_BOLD, fill="white")

    draw.rounded_rectangle((400, 215, 810, 330), radius=24, fill="#1c5d70")
    draw.text((425, 245), "Severidad / Salud", font=FONT_SMALL, fill="#d9f7ff")
    draw.text((425, 275), "ALTA | 48/100", font=FONT_BOLD, fill="white")

    draw.rounded_rectangle((90, 370, 810, 555), radius=28, fill="#f4ece0", outline="#e3d8c8", width=2)
    draw.text((120, 400), "Causa probable", font=FONT_SEMIBOLD, fill="#8a3d30")
    causa = "Caida de suministro de vapor o dosificacion insuficiente de energia termica."
    draw.multiline_text((120, 440), causa, font=FONT_TEXT, fill="#4c4c4c", spacing=6)

    draw.rounded_rectangle((90, 590, 810, 790), radius=28, fill="#18394e")
    draw.text((120, 625), "Accion sugerida", font=FONT_SEMIBOLD, fill="#dcebf4")
    accion = (
        "Revise la linea de vapor, confirme apertura de valvula y "
        "corrija la dosificacion termica antes de continuar."
    )
    draw.multiline_text((120, 670), accion, font=FONT_TEXT, fill="white", spacing=8)

    draw.rounded_rectangle((90, 825, 810, 1010), radius=28, fill="#efe7d9", outline="#e3d8c8", width=2)
    draw.text((120, 855), "Lectura sintetica", font=FONT_SEMIBOLD, fill="#1c5d70")
    resumen = "Temperatura 74.8 C | Presion 6.9 PSI | Tendencia descendente confirmada"
    draw.multiline_text((120, 900), resumen, font=FONT_TEXT, fill="#4c4c4c", spacing=8)

    draw.text((120, 1075), "Ejemplo visual tipo Nano Banana para Telegram", font=FONT_SMALL, fill="#7a746c")

    path = ASSETS / "ficha_ia_mock_demo.png"
    img.save(path)
    return path


def generar_mock_telegram(panel_path: Path, ficha_path: Path):
    base = Image.new("RGB", (1080, 1920), "#d8e9c3")
    draw = ImageDraw.Draw(base)

    draw.rounded_rectangle((40, 80, 1040, 240), radius=38, fill="white")
    texto = (
        "Paquete Multimodal | Lectura 8\\n"
        "Estado global: EN RIESGO | Severidad: ALTA\\n"
        "Maria: Reduzca alimentacion y revise suministro de vapor."
    )
    draw.multiline_text((75, 120), texto, font=FONT_TEXT, fill="#1f1f1f", spacing=8)

    panel = Image.open(panel_path).convert("RGB")
    panel.thumbnail((960, 640))
    panel_bg = Image.new("RGB", (1000, panel.height + 70), "white")
    panel_bg.paste(panel, ((1000 - panel.width) // 2, 20))
    base.paste(panel_bg, (40, 280))
    draw.text((70, 280 + panel_bg.height - 36), "Panel multimodal enviado por Telegram", font=FONT_SMALL, fill="#222")

    ficha = Image.open(ficha_path).convert("RGB")
    ficha.thumbnail((740, 980))
    ficha_bg = Image.new("RGB", (780, ficha.height + 70), "white")
    ficha_bg.paste(ficha, ((780 - ficha.width) // 2, 20))
    base.paste(ficha_bg, (40, 1020))
    draw.text((70, 1020 + ficha_bg.height - 36), "Ficha Operario generada por IA", font=FONT_SMALL, fill="#222")

    path = ASSETS / "telegram_mock_demo.png"
    base.save(path)
    return path


if __name__ == "__main__":
    panel = generar_panel()
    ficha = generar_ficha_mock()
    telegram = generar_mock_telegram(panel, ficha)
    print(panel)
    print(ficha)
    print(telegram)
