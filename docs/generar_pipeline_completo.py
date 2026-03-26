"""
Genera el diagrama completo del pipeline del sistema de monitoreo
de peletizacion con LLM multimodal.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# ─── Configuracion ───
fig, ax = plt.subplots(1, 1, figsize=(22, 30))
ax.set_xlim(0, 22)
ax.set_ylim(0, 30)
ax.axis('off')
fig.patch.set_facecolor('#FAFBFE')

# ─── Colores ───
C_NAVY = '#1E2761'
C_BLUE = '#2E75B6'
C_ICE = '#CADCFC'
C_GREEN = '#2C5F2D'
C_GREEN_LIGHT = '#E8F4E8'
C_ORANGE = '#FF8C00'
C_ORANGE_LIGHT = '#FFF3E0'
C_RED = '#DC3545'
C_RED_LIGHT = '#FFF0F0'
C_PURPLE = '#7B2D8E'
C_PURPLE_LIGHT = '#F3E8F9'
C_TEAL = '#065A82'
C_TEAL_LIGHT = '#E0F2F7'
C_GRAY = '#666666'
C_LIGHT_GRAY = '#F2F6FC'
C_DARK = '#0D1B2A'
C_TERRA = '#B85042'
C_TERRA_LIGHT = '#FCEAE7'
C_CYAN = '#028090'
C_CYAN_LIGHT = '#E0F7FA'
C_WHITE = '#FFFFFF'

def draw_box(x, y, w, h, color, text, fontsize=11, text_color='white', alpha=1.0, border_color=None, radius=0.3):
    """Dibuja un recuadro redondeado con texto centrado."""
    bc = border_color or color
    box = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.1,rounding_size={radius}",
                          facecolor=color, edgecolor=bc, linewidth=1.5, alpha=alpha, zorder=2)
    ax.add_patch(box)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=fontsize,
            color=text_color, fontweight='bold', zorder=3, wrap=True,
            fontfamily='sans-serif')

def draw_box_with_sub(x, y, w, h, color, title, subtitle, title_size=12, sub_size=9,
                       text_color='white', sub_color=None, border_color=None, radius=0.3):
    """Recuadro con titulo y subtitulo."""
    bc = border_color or color
    sc = sub_color or text_color
    box = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.1,rounding_size={radius}",
                          facecolor=color, edgecolor=bc, linewidth=1.5, zorder=2)
    ax.add_patch(box)
    ax.text(x + w/2, y + h*0.62, title, ha='center', va='center', fontsize=title_size,
            color=text_color, fontweight='bold', zorder=3, fontfamily='sans-serif')
    ax.text(x + w/2, y + h*0.28, subtitle, ha='center', va='center', fontsize=sub_size,
            color=sc, fontweight='normal', zorder=3, fontfamily='sans-serif', style='italic')

def draw_section_bg(x, y, w, h, color, label, label_color=None):
    """Fondo de seccion con label lateral."""
    lc = label_color or color
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.15,rounding_size=0.4",
                          facecolor=color, edgecolor='none', alpha=0.35, zorder=0)
    ax.add_patch(box)
    ax.text(x + 0.3, y + h - 0.3, label, ha='left', va='top', fontsize=10,
            color=lc, fontweight='bold', fontfamily='sans-serif', alpha=0.8, zorder=1)

def arrow_down(x, y1, y2, color=C_GRAY, style='->', lw=2):
    ax.annotate('', xy=(x, y2), xytext=(x, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw, connectionstyle='arc3,rad=0'),
                zorder=1)

def arrow_right(x1, y, x2, color=C_GRAY, style='->', lw=2):
    ax.annotate('', xy=(x2, y), xytext=(x1, y),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw), zorder=1)

def arrow_curved(x1, y1, x2, y2, color=C_GRAY, style='->', lw=1.5, rad=0.3):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                               connectionstyle=f'arc3,rad={rad}'), zorder=1)

# ═══════════════════════════════════════════════════════════
# TITULO
# ═══════════════════════════════════════════════════════════
ax.text(11, 29.5, 'Pipeline Completo del Sistema', ha='center', va='center',
        fontsize=24, color=C_NAVY, fontweight='bold', fontfamily='sans-serif')
ax.text(11, 29.0, 'Sistema Inteligente de Monitoreo de Planta de Peletizacion con LLM Multimodal',
        ha='center', va='center', fontsize=12, color=C_GRAY, fontfamily='sans-serif', style='italic')
ax.text(11, 28.6, 'Universidad Nacional de Colombia | Facultad de Minas | Sistemas Inteligentes',
        ha='center', va='center', fontsize=9, color=C_GRAY, fontfamily='sans-serif')

# ═══════════════════════════════════════════════════════════
# CAPA 1: FUENTES DE DATOS
# ═══════════════════════════════════════════════════════════
Y_DATA = 27.2
draw_section_bg(1, Y_DATA - 0.3, 20, 1.5, C_LIGHT_GRAY, 'CAPA 1: FUENTES DE DATOS', C_GRAY)

draw_box_with_sub(3, Y_DATA, 3.5, 1.0, C_GRAY, 'CSV Planta', 'telemetria_001.csv (polling)', sub_color='#CCCCCC')
draw_box_with_sub(8.5, Y_DATA, 4.0, 1.0, C_TEAL, 'Google Cloud Pub/Sub', 'Tiempo real (ms latencia)', sub_color=C_TEAL_LIGHT)
draw_box_with_sub(14.5, Y_DATA, 3.5, 1.0, '#555555', 'Datos Maestros', 'Formulas + Equipos + Personal', sub_color='#CCCCCC')

# Flecha hacia Motor
arrow_down(6.5, Y_DATA, Y_DATA - 1.1, C_GRAY)
arrow_down(10.5, Y_DATA, Y_DATA - 1.1, C_TEAL)

# ═══════════════════════════════════════════════════════════
# CAPA 2: MOTOR DE REGLAS
# ═══════════════════════════════════════════════════════════
Y_MOTOR = 25.0
draw_section_bg(1, Y_MOTOR - 0.3, 20, 1.8, C_GREEN_LIGHT, 'CAPA 2: MOTOR DE REGLAS DETERMINISTA (ISA-18.2)', C_GREEN)

draw_box_with_sub(2, Y_MOTOR + 0.1, 3.0, 0.9, C_GREEN, 'EMA (alpha=0.3)', 'Suavizado exponencial', sub_color=C_GREEN_LIGHT)
arrow_right(5.0, Y_MOTOR + 0.55, 5.8, C_GREEN, lw=2.5)
draw_box_with_sub(5.8, Y_MOTOR + 0.1, 3.5, 0.9, C_GREEN, 'Maquina de Estados', 'NORMAL / BAJA / ALTA', sub_color=C_GREEN_LIGHT)
arrow_right(9.3, Y_MOTOR + 0.55, 10.1, C_GREEN, lw=2.5)
draw_box_with_sub(10.1, Y_MOTOR + 0.1, 3.0, 0.9, C_GREEN, 'Histeresis (2x)', 'Confirmacion por persistencia', sub_color=C_GREEN_LIGHT)
arrow_right(13.1, Y_MOTOR + 0.55, 13.9, C_GREEN, lw=2.5)
draw_box_with_sub(13.9, Y_MOTOR + 0.1, 3.0, 0.9, C_GREEN, 'Anti-spam', 'Max N alertas/ventana', sub_color=C_GREEN_LIGHT)
arrow_right(16.9, Y_MOTOR + 0.55, 17.7, C_GREEN, lw=2.5)
draw_box(17.7, Y_MOTOR + 0.15, 2.5, 0.8, C_RED, 'ALERTA\nCONFIRMADA', fontsize=10)

# Flecha hacia Feature Store
arrow_down(11, Y_MOTOR + 0.1, Y_MOTOR - 0.8, C_BLUE)

# ═══════════════════════════════════════════════════════════
# CAPA 3: FEATURE STORE
# ═══════════════════════════════════════════════════════════
Y_FS = 22.8
draw_section_bg(1, Y_FS - 0.3, 20, 2.0, C_TEAL_LIGHT, 'CAPA 3: FEATURE STORE (4 capas de analisis)', C_BLUE)

draw_box_with_sub(2, Y_FS + 0.2, 4.0, 0.8, C_BLUE, 'Capa 1: Features Variable', 'Tasa cambio, tendencia, sigma, fuera de banda', sub_color=C_ICE, title_size=10, sub_size=8)
draw_box_with_sub(6.5, Y_FS + 0.2, 4.0, 0.8, C_BLUE, 'Capa 2: Matriz 3x3', 'Temp(B/N/A) x Presion(B/N/A) = 9 estados', sub_color=C_ICE, title_size=10, sub_size=8)
draw_box_with_sub(11, Y_FS + 0.2, 4.0, 0.8, C_BLUE, 'Capa 3: Correlaciones', 'Pearson temp-pres (normal: 0.85)', sub_color=C_ICE, title_size=10, sub_size=8)
draw_box_with_sub(15.5, Y_FS + 0.2, 4.5, 0.8, C_BLUE, 'Capa 4: Anomalia Global', 'Score 0.0 (normal) a 1.0 (critico)', sub_color=C_ICE, title_size=10, sub_size=8)

# Flecha hacia RAG+RLHF
arrow_down(11, Y_FS + 0.2, Y_FS - 0.7, C_PURPLE)

# ═══════════════════════════════════════════════════════════
# CAPA 4 + 5: RAG y RLHF (lado a lado)
# ═══════════════════════════════════════════════════════════
Y_RAG = 20.5
draw_section_bg(1, Y_RAG - 0.3, 9.5, 2.0, C_PURPLE_LIGHT, 'CAPA 4: RAG', C_PURPLE)
draw_section_bg(11.5, Y_RAG - 0.3, 9.5, 2.0, C_ORANGE_LIGHT, 'CAPA 5: RLHF LIVIANO', C_ORANGE)

# RAG sources
draw_box_with_sub(1.5, Y_RAG + 0.15, 4.0, 0.8, C_PURPLE, 'base_conocimiento.yaml', '20 fallas + 8 SOPs + 5 equipos', sub_color='#E0D0F0', title_size=9, sub_size=8)
draw_box_with_sub(6, Y_RAG + 0.15, 4.0, 0.8, C_PURPLE, 'Datos Maestros CSV', 'Formulas + Equipos + Personal', sub_color='#E0D0F0', title_size=9, sub_size=8)

# RLHF
draw_box_with_sub(12, Y_RAG + 0.15, 4.0, 0.8, C_ORANGE, 'Few-shot Positivos', 'Prescripciones calificadas UTIL', sub_color='#FFE0B2', title_size=9, sub_size=8)
draw_box_with_sub(16.5, Y_RAG + 0.15, 4.0, 0.8, C_ORANGE, 'Antipatrones', 'FALSO_POSITIVO -> "NO hacer esto"', sub_color='#FFE0B2', title_size=9, sub_size=8)

# Flechas hacia LLM
arrow_down(5.5, Y_RAG + 0.15, Y_RAG - 1.0, C_PURPLE)
arrow_down(16.5, Y_RAG + 0.15, Y_RAG - 1.0, C_ORANGE)

# ═══════════════════════════════════════════════════════════
# CAPA 6: LLM MULTIMODAL + LOOP AGENTICO (zona grande)
# ═══════════════════════════════════════════════════════════
Y_LLM = 16.5
draw_section_bg(1, Y_LLM - 0.3, 20, 3.5, C_RED_LIGHT, 'CAPA 6: LLM MULTIMODAL — LOOP AGENTICO (Gemini 2.5 Flash)', C_RED)

# Inputs al LLM
draw_box(2, Y_LLM + 1.8, 2.8, 0.7, C_NAVY, 'Prompt\n(RAG + Features + RLHF)', fontsize=8, text_color=C_WHITE)
draw_box(5.2, Y_LLM + 1.8, 2.5, 0.7, '#28A745', 'Imagen PNG\nPanel proceso', fontsize=8)
draw_box(8.1, Y_LLM + 1.8, 2.5, 0.7, '#17A2B8', 'GIF Animado\n30s temporal', fontsize=8)

# Central: Gemini
draw_box(2, Y_LLM + 0.4, 8.5, 1.2, C_RED, 'GEMINI 2.5 FLASH\nLoop Agentico (max 5 iteraciones)\nDecide autonomamente que herramientas usar', fontsize=11)

# 7 herramientas
herramientas = [
    ('consultar\nhistorial', C_TEAL),
    ('obtener\nformula', C_TEAL),
    ('obtener\noperario', C_TEAL),
    ('ajustar\numbral', C_ORANGE),
    ('escalar\nsupervisor', C_RED),
    ('registrar\naccion', C_GREEN),
    ('analizar\nfeedback', C_PURPLE),
]
for i, (nombre, color) in enumerate(herramientas):
    x = 11.5 + (i % 4) * 2.5
    y = Y_LLM + 1.5 - (i // 4) * 1.1
    draw_box(x, y, 2.2, 0.85, color, nombre, fontsize=8)

ax.text(14.5, Y_LLM + 2.7, '7 HERRAMIENTAS DEL AGENTE', ha='center', fontsize=10,
        color=C_RED, fontweight='bold', fontfamily='sans-serif')

# Flecha de Gemini a herramientas
arrow_right(10.5, Y_LLM + 1.0, 11.3, C_RED, lw=2.5)
ax.text(10.9, Y_LLM + 1.2, 'Tool\nUse', ha='center', fontsize=7, color=C_RED, fontfamily='sans-serif')

# Salida
arrow_down(6, Y_LLM + 0.4, Y_LLM - 0.5, C_RED, lw=2.5)
draw_box(4, Y_LLM - 1.1, 4.5, 0.6, C_DARK, 'PRESCRIPCION INTELIGENTE', fontsize=10)

# ═══════════════════════════════════════════════════════════
# CAPA 7: SHADOW MODE (lateral)
# ═══════════════════════════════════════════════════════════
Y_SHADOW = 15.0
draw_section_bg(12, Y_SHADOW - 0.1, 9, 1.3, C_LIGHT_GRAY, 'CAPA 7: SHADOW MODE / A/B', '#555555')
draw_box_with_sub(12.5, Y_SHADOW, 3.5, 0.9, '#555555', 'Variante A (control)', 'Gemini 2.5 Flash', sub_color='#CCCCCC', title_size=9, sub_size=8)
draw_box_with_sub(16.5, Y_SHADOW, 3.5, 0.9, '#555555', 'Variante B (challenger)', 'ThreadPoolExecutor paralelo', sub_color='#CCCCCC', title_size=9, sub_size=8)
ax.text(16.25, Y_SHADOW + 0.45, 'vs', ha='center', fontsize=12, color='#555555', fontweight='bold')

# Flecha de prescripcion hacia Telegram
arrow_down(6, Y_LLM - 1.1, Y_LLM - 2.0, C_NAVY, lw=2.5)

# ═══════════════════════════════════════════════════════════
# CAPA 8: TELEGRAM (bidireccional)
# ═══════════════════════════════════════════════════════════
Y_TEL = 12.0
draw_section_bg(1, Y_TEL - 0.3, 20, 2.8, C_ICE, 'CAPA 8: COMUNICACION MULTIMODAL (Telegram)', C_NAVY)

# Sistema -> Operario
ax.text(5.5, Y_TEL + 1.9, 'SISTEMA -> OPERARIO', ha='center', fontsize=10,
        color=C_NAVY, fontweight='bold', fontfamily='sans-serif')
outputs = [
    ('Texto\nAlerta HTML', C_NAVY, 1.5),
    ('Imagen\nPanel PNG', C_GREEN, 4.0),
    ('PDF\nReporte', C_PURPLE, 6.5),
    ('Botones\nFeedback', C_ORANGE, 9.0),
]
for nombre, color, x in outputs:
    draw_box(x, Y_TEL + 0.9, 2.2, 0.8, color, nombre, fontsize=8)

# Operario -> Sistema
ax.text(16.5, Y_TEL + 1.9, 'OPERARIO -> SISTEMA', ha='center', fontsize=10,
        color=C_NAVY, fontweight='bold', fontfamily='sans-serif')
inputs_op = [
    ('Audio\n(voz -> STT)', '#E91E63', 12.5),
    ('Texto\nlibre', C_BLUE, 15.0),
    ('Foto\nequipo', C_TEAL, 17.5),
]
for nombre, color, x in inputs_op:
    draw_box(x, Y_TEL + 0.9, 2.2, 0.8, color, nombre, fontsize=8)

# Memoria de conversacion
draw_box(5, Y_TEL, 12, 0.6, C_DARK, 'MEMORIA DE CONVERSACION — Maria recuerda todo el incidente (historial inyectado en cada llamada)', fontsize=9)

# ═══════════════════════════════════════════════════════════
# CAPA 9: NANOBANANA (Fichas IA)
# ═══════════════════════════════════════════════════════════
Y_NB = 9.8
draw_section_bg(1, Y_NB - 0.3, 9.5, 2.0, C_TERRA_LIGHT, 'CAPA 9: NANOBANANA — Fichas Visuales con IA', C_TERRA)

draw_box_with_sub(1.5, Y_NB + 0.2, 4.2, 0.8, C_TERRA, 'Gemini Image Generation', 'response_modalities=[TEXT, IMAGE]', sub_color='#F5D5CF', title_size=10, sub_size=8)
arrow_right(5.7, Y_NB + 0.6, 6.3, C_TERRA, lw=2)
draw_box_with_sub(6.3, Y_NB + 0.2, 3.7, 0.8, C_TERRA, 'Ficha Visual PNG', 'Cierre + Operario + Gerencial', sub_color='#F5D5CF', title_size=10, sub_size=8)

# ═══════════════════════════════════════════════════════════
# CAPA 10: EMAIL
# ═══════════════════════════════════════════════════════════
draw_section_bg(11.5, Y_NB - 0.3, 9.5, 2.0, C_CYAN_LIGHT, 'CAPA 10: EMAIL AL SUPERVISOR', C_CYAN)

draw_box_with_sub(12, Y_NB + 0.2, 4.0, 0.8, C_CYAN, 'EmailService (SMTP)', 'TLS + adjunto PNG + HTML', sub_color='#B2EBF2', title_size=10, sub_size=8)
arrow_right(16.0, Y_NB + 0.6, 16.6, C_CYAN, lw=2)
draw_box_with_sub(16.6, Y_NB + 0.2, 3.8, 0.8, C_CYAN, 'Supervisor recibe', 'Ficha + resumen en correo', sub_color='#B2EBF2', title_size=10, sub_size=8)

# Flecha NanoBanana -> Email
arrow_right(10, Y_NB + 0.6, 12, C_TERRA, lw=1.5, style='->')

# ═══════════════════════════════════════════════════════════
# FLUJO DE CIERRE DE INCIDENTE
# ═══════════════════════════════════════════════════════════
Y_CIERRE = 7.8
draw_section_bg(1, Y_CIERRE - 0.1, 20, 1.5, '#E8F5E9', 'FLUJO DE CIERRE DE INCIDENTE', C_GREEN)

pasos_cierre = [
    ('1. Operario:\n"Si, solucionado"', C_GREEN),
    ('2. NanoBanana\ngenera ficha', C_TERRA),
    ('3. Telegram\nenvia ficha', C_NAVY),
    ('4. Email SMTP\nal supervisor', C_CYAN),
    ('5. Persistir\nconversacion', C_PURPLE),
    ('6. Reanudar\nmonitoreo', C_GREEN),
]
for i, (texto, color) in enumerate(pasos_cierre):
    x = 1.5 + i * 3.3
    draw_box(x, Y_CIERRE + 0.1, 2.8, 0.8, color, texto, fontsize=8)
    if i < len(pasos_cierre) - 1:
        arrow_right(x + 2.8, Y_CIERRE + 0.5, x + 3.3, color, lw=2)

# ═══════════════════════════════════════════════════════════
# RESILIENCIA (Circuit Breaker)
# ═══════════════════════════════════════════════════════════
Y_RES = 5.5
draw_section_bg(1, Y_RES - 0.3, 12, 2.2, C_RED_LIGHT, 'RESILIENCIA: CIRCUIT BREAKER', C_RED)

draw_box(1.5, Y_RES + 0.5, 3.0, 0.8, C_GREEN, 'CERRADO\nGemini OK', fontsize=9)
arrow_right(4.5, Y_RES + 0.9, 5.5, C_RED, lw=2)
ax.text(5.0, Y_RES + 1.15, '3 fallos', ha='center', fontsize=7, color=C_RED)
draw_box(5.5, Y_RES + 0.5, 3.0, 0.8, C_RED, 'ABIERTO\nGemma 2B local', fontsize=9)
arrow_right(8.5, Y_RES + 0.9, 9.5, C_ORANGE, lw=2)
ax.text(9.0, Y_RES + 1.15, '5 min', ha='center', fontsize=7, color=C_ORANGE)
draw_box(9.5, Y_RES + 0.5, 3.0, 0.8, C_ORANGE, 'SEMI-ABIERTO\nPrueba 1 vez', fontsize=9)

# Arrow back
arrow_curved(11, Y_RES + 0.5, 3.0, Y_RES + 0.5, C_GREEN, lw=1.5, rad=-0.4)
ax.text(7, Y_RES + 0.1, 'exito -> vuelve a Gemini', ha='center', fontsize=7, color=C_GREEN)

# Gemma specs
draw_box_with_sub(2, Y_RES - 0.1, 4.5, 0.5, C_DARK, 'Gemma 2B: 1.5 GB RAM | ~800ms CPU | Espanol nativo | Knowledge Distillation de Gemini', '',
                   title_size=7, sub_size=7)

# ═══════════════════════════════════════════════════════════
# SEGURIDAD
# ═══════════════════════════════════════════════════════════
draw_section_bg(13.5, Y_RES - 0.3, 7.5, 2.2, C_ORANGE_LIGHT, 'SEGURIDAD', C_ORANGE)

draw_box_with_sub(14, Y_RES + 0.5, 3.2, 0.8, C_ORANGE, 'Anti Prompt-Injection', 'Rechaza off-topic, redirige', sub_color='#FFE0B2', title_size=9, sub_size=8)
draw_box_with_sub(17.5, Y_RES + 0.5, 3.0, 0.8, C_ORANGE, 'Limites Hardcoded', 'P:2-45 T:40-120 I:0-490', sub_color='#FFE0B2', title_size=9, sub_size=8)

# ═══════════════════════════════════════════════════════════
# RLHF LOOP (retroalimentacion)
# ═══════════════════════════════════════════════════════════
Y_LOOP = 3.5
draw_section_bg(1, Y_LOOP - 0.3, 20, 1.8, C_ORANGE_LIGHT, 'CICLO DE MEJORA CONTINUA (RLHF)', C_ORANGE)

pasos_rlhf = [
    ('Operario califica\n[Util] [FP] [Mant]', C_ORANGE),
    ('historial_alertas.csv\nScore: 1.0 / 0.5 / 0.0', C_PURPLE),
    ('Few-shot positivos\n+ Antipatrones', C_ORANGE),
    ('Se inyectan en\nproximo prompt', C_RED),
    ('Deteccion de deriva\n>30% FP en 14 dias', C_RED),
]
for i, (texto, color) in enumerate(pasos_rlhf):
    x = 1.2 + i * 4.0
    draw_box(x, Y_LOOP, 3.5, 0.8, color, texto, fontsize=8)
    if i < len(pasos_rlhf) - 1:
        arrow_right(x + 3.5, Y_LOOP + 0.4, x + 4.0, color, lw=1.5)

# ═══════════════════════════════════════════════════════════
# PERSISTENCIA
# ═══════════════════════════════════════════════════════════
Y_PERSIST = 1.5
draw_section_bg(1, Y_PERSIST - 0.3, 20, 1.5, C_LIGHT_GRAY, 'PERSISTENCIA (CSV)', C_GRAY)

csvs = [
    'historial_alertas.csv',
    'historial_incidentes.csv',
    'historial_eventos.csv',
    'historial_audio.csv',
    'historial_conversaciones.csv',
    'shadow_log.csv',
]
for i, nombre in enumerate(csvs):
    x = 1.5 + i * 3.3
    draw_box(x, Y_PERSIST, 3.0, 0.6, C_GRAY, nombre, fontsize=7, text_color=C_WHITE)

# ═══════════════════════════════════════════════════════════
# STATS FINALES
# ═══════════════════════════════════════════════════════════
stats_text = '11,451 lineas | 26 modulos | 31 commits | 5 APIs Google Cloud | 7 herramientas | 18/20 conceptos del curso'
ax.text(11, 0.6, stats_text, ha='center', va='center', fontsize=10, color=C_NAVY,
        fontweight='bold', fontfamily='sans-serif',
        bbox=dict(boxstyle='round,pad=0.3', facecolor=C_ICE, edgecolor=C_NAVY, linewidth=1.5))

# ═══════════════════════════════════════════════════════════
# GUARDAR
# ═══════════════════════════════════════════════════════════
plt.tight_layout(pad=0.5)
out_path = r'C:\Users\USUARIO\Desktop\Maestria\sistemasinteligentes\proyecto\docs\Pipeline_Completo_Sistema.png'
fig.savefig(out_path, dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor())
plt.close()

# Tambien PDF
out_pdf = r'C:\Users\USUARIO\Desktop\Maestria\sistemasinteligentes\proyecto\docs\Pipeline_Completo_Sistema.pdf'
fig2, ax2 = plt.subplots(1, 1, figsize=(22, 30))
ax2.axis('off')
plt.close()

# Usar el PNG para el PDF via pillow
from PIL import Image as PILImage
img = PILImage.open(out_path)
img.save(out_pdf, 'PDF', resolution=200)

print(f'PNG: {out_path}')
print(f'PDF: {out_pdf}')

import os
png_size = os.path.getsize(out_path)
pdf_size = os.path.getsize(out_pdf)
print(f'PNG: {png_size/1024:.0f} KB | PDF: {pdf_size/1024:.0f} KB')
