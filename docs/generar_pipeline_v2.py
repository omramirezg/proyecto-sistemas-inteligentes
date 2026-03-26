"""
Pipeline completo — version limpia y profesional.
Diseño: vertical, espaciado, legible, sin cruces.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import os

fig, ax = plt.subplots(1, 1, figsize=(20, 28))
ax.set_xlim(0, 20)
ax.set_ylim(0, 28)
ax.axis('off')
fig.patch.set_facecolor('#FFFFFF')

# ─── Paleta ───
NAVY    = '#1A2744'
BLUE    = '#2E6BA6'
TEAL    = '#1A8A7D'
GREEN   = '#2D7A3A'
ORANGE  = '#D4760A'
RED     = '#C0392B'
PURPLE  = '#6C3483'
BROWN   = '#8B4513'
CYAN    = '#117A8B'
DARK    = '#1C1C1C'
GRAY    = '#7F8C8D'
LIGHT   = '#F5F7FA'
WHITE   = '#FFFFFF'
ICE     = '#D6E4F0'

def box(x, y, w, h, color, title, sub='', ts=12, ss=9):
    """Caja limpia con titulo y subtitulo opcional."""
    b = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.08,rounding_size=0.15',
                        facecolor=color, edgecolor='none', zorder=2)
    ax.add_patch(b)
    if sub:
        ax.text(x + w/2, y + h*0.63, title, ha='center', va='center',
                fontsize=ts, color=WHITE, fontweight='bold', fontfamily='sans-serif', zorder=3)
        ax.text(x + w/2, y + h*0.3, sub, ha='center', va='center',
                fontsize=ss, color='#DDDDDD', fontfamily='sans-serif', zorder=3)
    else:
        ax.text(x + w/2, y + h/2, title, ha='center', va='center',
                fontsize=ts, color=WHITE, fontweight='bold', fontfamily='sans-serif', zorder=3)

def light_box(x, y, w, h, color, title, sub='', ts=11, ss=8):
    """Caja con fondo claro y borde de color."""
    bg = color + '15'  # no funciona, usamos LIGHT
    b = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.08,rounding_size=0.12',
                        facecolor=LIGHT, edgecolor=color, linewidth=2, zorder=2)
    ax.add_patch(b)
    if sub:
        ax.text(x + w/2, y + h*0.63, title, ha='center', va='center',
                fontsize=ts, color=color, fontweight='bold', fontfamily='sans-serif', zorder=3)
        ax.text(x + w/2, y + h*0.3, sub, ha='center', va='center',
                fontsize=ss, color=GRAY, fontfamily='sans-serif', zorder=3)
    else:
        ax.text(x + w/2, y + h/2, title, ha='center', va='center',
                fontsize=ts, color=color, fontweight='bold', fontfamily='sans-serif', zorder=3)

def section_label(x, y, num, title, color):
    """Numero en circulo + titulo de seccion."""
    circle = plt.Circle((x + 0.25, y), 0.25, color=color, zorder=3)
    ax.add_patch(circle)
    ax.text(x + 0.25, y, str(num), ha='center', va='center',
            fontsize=11, color=WHITE, fontweight='bold', fontfamily='sans-serif', zorder=4)
    ax.text(x + 0.7, y, title, ha='left', va='center',
            fontsize=13, color=color, fontweight='bold', fontfamily='sans-serif', zorder=3)

def arrow_d(x, y1, y2, color=GRAY):
    ax.annotate('', xy=(x, y2), xytext=(x, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=2), zorder=1)

def arrow_r(x1, y, x2, color=GRAY):
    ax.annotate('', xy=(x2, y), xytext=(x1, y),
                arrowprops=dict(arrowstyle='->', color=color, lw=2), zorder=1)

# ═══════════════════════════════════════════════════════
# TITULO
# ═══════════════════════════════════════════════════════
ax.text(10, 27.5, 'Pipeline Completo del Sistema', ha='center',
        fontsize=24, color=NAVY, fontweight='bold', fontfamily='sans-serif')
ax.text(10, 27.1, 'Sistema de Monitoreo de Peletizacion con LLM Multimodal',
        ha='center', fontsize=12, color=GRAY, fontfamily='sans-serif')

# ═══════════════════════════════════════════════════════
# 1. FUENTE DE DATOS
# ═══════════════════════════════════════════════════════
Y = 26.2
section_label(0.5, Y + 0.3, 1, 'TELEMETRIA (Fuente de datos)', GRAY)
box(2, Y - 0.5, 5.5, 0.7, GRAY, 'CSV Planta', 'telemetria_planta_001.csv — polling cada 60s', ts=11, ss=8)
box(8.5, Y - 0.5, 4.5, 0.7, NAVY, 'Datos Maestros', 'Formulas + Equipos + Personal (CSV)', ts=11, ss=8)
light_box(13.5, Y - 0.5, 4, 0.7, TEAL, 'Pub/Sub (opcional)', 'Para produccion real', ts=10, ss=8)

arrow_d(5, Y - 0.5, Y - 1.2, GRAY)

# ═══════════════════════════════════════════════════════
# 2. MOTOR DE REGLAS
# ═══════════════════════════════════════════════════════
Y = 24.2
section_label(0.5, Y + 0.3, 2, 'MOTOR DE REGLAS (ISA-18.2)', GREEN)

steps = [
    ('EMA\n(alpha=0.3)', 'Suaviza ruido'),
    ('Maquina de\nEstados', 'NORMAL/BAJA/ALTA'),
    ('Histeresis\n(2 lecturas)', 'Confirmacion'),
    ('Anti-spam', 'Max N/ventana'),
]
for i, (t, s) in enumerate(steps):
    x = 1 + i * 3.5
    box(x, Y - 0.6, 3.0, 0.8, GREEN, t, s, ts=10, ss=8)
    if i < len(steps) - 1:
        arrow_r(x + 3.0, Y - 0.2, x + 3.5, GREEN)

# Alerta
box(15, Y - 0.6, 2.5, 0.8, RED, 'ALERTA', 'Confirmada', ts=12, ss=9)
arrow_r(14, Y - 0.2, 15, RED)

arrow_d(9, Y - 0.6, Y - 1.4, BLUE)

# ═══════════════════════════════════════════════════════
# 3. FEATURE STORE
# ═══════════════════════════════════════════════════════
Y = 22.0
section_label(0.5, Y + 0.3, 3, 'FEATURE STORE (Analisis numerico para el LLM)', BLUE)

features = [
    ('Tasa de cambio', '-2.3 C/min'),
    ('Matriz 3x3', 'Temp x Presion'),
    ('Correlaciones', 'Pearson (0.85)'),
    ('Anomalia global', 'Score 0-1'),
]
for i, (t, s) in enumerate(features):
    x = 1 + i * 4.2
    light_box(x, Y - 0.5, 3.8, 0.7, BLUE, t, s, ts=10, ss=8)

arrow_d(9, Y - 0.5, Y - 1.2, PURPLE)

# ═══════════════════════════════════════════════════════
# 4. RAG + 5. RLHF (lado a lado)
# ═══════════════════════════════════════════════════════
Y = 20.0
section_label(0.5, Y + 0.3, 4, 'RAG', PURPLE)
section_label(9.5, Y + 0.3, 5, 'RLHF LIVIANO', ORANGE)

box(1, Y - 0.5, 3.8, 0.7, PURPLE, 'Conocimiento Planta', '20 fallas + 8 SOPs + 5 equipos', ts=10, ss=8)
box(5.2, Y - 0.5, 3.8, 0.7, PURPLE, 'Historial + Maestros', 'CSV formulas, equipos, personal', ts=10, ss=8)

box(10, Y - 0.5, 3.5, 0.7, ORANGE, 'Few-shot positivos', 'Prescripciones UTIL', ts=10, ss=8)
box(14, Y - 0.5, 3.5, 0.7, ORANGE, 'Antipatrones', 'FALSO_POSITIVO evitar', ts=10, ss=8)

arrow_d(5, Y - 0.5, Y - 1.3, RED)
arrow_d(13, Y - 0.5, Y - 1.3, RED)

# ═══════════════════════════════════════════════════════
# 6. LLM MULTIMODAL + AGENTIC
# ═══════════════════════════════════════════════════════
Y = 17.5
section_label(0.5, Y + 0.5, 6, 'LLM MULTIMODAL + LOOP AGENTICO', RED)

# Inputs
inputs_llm = [('Prompt\n(RAG+Features\n+RLHF)', NAVY), ('Imagen\nPNG', GREEN), ('GIF\nAnimado', TEAL)]
for i, (t, c) in enumerate(inputs_llm):
    x = 1 + i * 3
    box(x, Y - 0.2, 2.5, 0.8, c, t, ts=9)
    arrow_d(x + 1.25, Y - 0.2, Y - 0.8, c)

# Gemini central
box(1, Y - 1.6, 8.5, 0.7, RED, 'GEMINI 2.5 FLASH — Loop agentico (max 5 iteraciones)', ts=11)

# Tools
ax.text(13.5, Y + 0.1, '7 Herramientas', ha='center', fontsize=11,
        color=RED, fontweight='bold', fontfamily='sans-serif')

tools = [
    'consultar_historial', 'obtener_formula',
    'obtener_operario', 'ajustar_umbral',
    'escalar_supervisor', 'registrar_accion',
    'analizar_feedback',
]
for i, t in enumerate(tools):
    col = i % 2
    row = i // 2
    x = 10.5 + col * 3.5
    y = Y - 0.5 - row * 0.55
    colors = [TEAL, TEAL, TEAL, ORANGE, RED, GREEN, PURPLE]
    box(x, y, 3.2, 0.45, colors[i], t, ts=8)

arrow_r(9.5, Y - 1.25, 10.3, RED)
ax.text(9.9, Y - 1.05, 'Tool Use', ha='center', fontsize=8, color=RED, fontfamily='sans-serif')

# Prescripcion
arrow_d(5, Y - 1.6, Y - 2.3, DARK)
box(2.5, Y - 3.0, 5.5, 0.6, DARK, 'PRESCRIPCION INTELIGENTE', ts=12)

# Shadow
light_box(10.5, Y - 2.8, 7, 0.7, GRAY, 'Shadow Mode / A/B Testing', 'Variante A vs B en paralelo (ThreadPoolExecutor)', ts=10, ss=8)

arrow_d(5, Y - 3.0, Y - 3.7, NAVY)

# ═══════════════════════════════════════════════════════
# 7. TELEGRAM
# ═══════════════════════════════════════════════════════
Y = 12.5
section_label(0.5, Y + 0.5, 7, 'COMUNICACION MULTIMODAL (Telegram)', NAVY)

# Outputs
ax.text(4.5, Y + 0.1, 'Sistema -> Operario', ha='center', fontsize=10,
        color=NAVY, fontweight='bold', fontfamily='sans-serif')
outs = [('Texto\nAlerta', NAVY), ('Imagen\nPanel', GREEN), ('PDF\nReporte', PURPLE), ('Botones\nFeedback', ORANGE)]
for i, (t, c) in enumerate(outs):
    box(1 + i * 2.2, Y - 0.8, 2.0, 0.7, c, t, ts=9)

# Inputs
ax.text(14.5, Y + 0.1, 'Operario -> Sistema', ha='center', fontsize=10,
        color=NAVY, fontweight='bold', fontfamily='sans-serif')
ins = [('Audio\n(voz)', '#C0392B'), ('Texto\nlibre', BLUE), ('Foto\nequipo', TEAL)]
for i, (t, c) in enumerate(ins):
    box(11 + i * 2.3, Y - 0.8, 2.0, 0.7, c, t, ts=9)

# Memoria
box(1, Y - 1.8, 16.5, 0.5, DARK,
    'MEMORIA DE CONVERSACION — Maria recuerda todo el incidente | Foto persiste para llamadas futuras',
    ts=9)

arrow_d(5, Y - 1.8, Y - 2.5, BROWN)
arrow_d(13, Y - 1.8, Y - 2.5, CYAN)

# ═══════════════════════════════════════════════════════
# 8. NANOBANANA + 9. EMAIL
# ═══════════════════════════════════════════════════════
Y = 9.2
section_label(0.5, Y + 0.3, 8, 'NANOBANANA (Fichas IA)', BROWN)
section_label(9.5, Y + 0.3, 9, 'EMAIL AL SUPERVISOR', CYAN)

box(1, Y - 0.5, 4, 0.7, BROWN, 'Gemini Image Gen', 'response_modalities=[TEXT, IMAGE]', ts=10, ss=8)
arrow_r(5.0, Y - 0.15, 5.5, BROWN)
box(5.5, Y - 0.5, 3.5, 0.7, BROWN, 'Ficha Visual PNG', 'Cierre + Operario + Gerencial', ts=10, ss=8)

box(10, Y - 0.5, 3.8, 0.7, CYAN, 'EmailService SMTP', 'TLS + adjunto PNG + HTML', ts=10, ss=8)
arrow_r(13.8, Y - 0.15, 14.3, CYAN)
box(14.3, Y - 0.5, 3.2, 0.7, CYAN, 'Supervisor recibe', 'Correo formal auditable', ts=10, ss=8)

arrow_r(9.0, Y - 0.15, 10, BROWN)

# ═══════════════════════════════════════════════════════
# FLUJO DE CIERRE
# ═══════════════════════════════════════════════════════
Y = 7.5
section_label(0.5, Y + 0.3, '', 'FLUJO DE CIERRE DE INCIDENTE', GREEN)

pasos = [
    ('Operario:\nSolucionado', GREEN),
    ('NanoBanana\ngenera ficha', BROWN),
    ('Telegram\nenvia ficha', NAVY),
    ('Email SMTP\nsupervisor', CYAN),
    ('Persistir\nconversacion', PURPLE),
    ('Reanudar\nmonitoreo', GREEN),
]
for i, (t, c) in enumerate(pasos):
    x = 0.5 + i * 2.9
    box(x, Y - 0.5, 2.5, 0.7, c, t, ts=8)
    if i < len(pasos) - 1:
        arrow_r(x + 2.5, Y - 0.15, x + 2.9, c)

# ═══════════════════════════════════════════════════════
# RESILIENCIA
# ═══════════════════════════════════════════════════════
Y = 5.5
section_label(0.5, Y + 0.3, 10, 'RESILIENCIA (Circuit Breaker)', RED)

box(1, Y - 0.5, 3.5, 0.7, GREEN, 'CERRADO', 'Gemini funciona OK', ts=11, ss=8)
arrow_r(4.5, Y - 0.15, 5.5, RED)
ax.text(5.0, Y + 0.1, '3 fallos', ha='center', fontsize=8, color=RED)
box(5.5, Y - 0.5, 3.5, 0.7, RED, 'ABIERTO', 'Gemma 2B local (CPU)', ts=11, ss=8)
arrow_r(9.0, Y - 0.15, 10.0, ORANGE)
ax.text(9.5, Y + 0.1, '5 min', ha='center', fontsize=8, color=ORANGE)
box(10.0, Y - 0.5, 3.5, 0.7, ORANGE, 'SEMI-ABIERTO', 'Prueba Gemini 1 vez', ts=11, ss=8)
arrow_r(13.5, Y - 0.15, 14.0, GREEN)
ax.text(13.7, Y + 0.1, 'exito', ha='center', fontsize=8, color=GREEN)
box(14.0, Y - 0.5, 3.5, 0.7, GREEN, 'CERRADO', 'Vuelve a Gemini', ts=11, ss=8)

# Gemma specs
light_box(1, Y - 1.4, 8, 0.5, RED, 'Gemma 2B: 1.5 GB RAM | ~800ms CPU | Espanol nativo | Knowledge Distillation', ts=9)

# Seguridad
light_box(10, Y - 1.4, 3.8, 0.5, ORANGE, 'Anti Prompt-Injection', 'Rechaza off-topic', ts=9, ss=8)
light_box(14.2, Y - 1.4, 3.3, 0.5, ORANGE, 'Limites Hardcoded', 'P:2-45 T:40-120', ts=9, ss=8)

# ═══════════════════════════════════════════════════════
# RLHF LOOP
# ═══════════════════════════════════════════════════════
Y = 3.0
section_label(0.5, Y + 0.3, '', 'CICLO DE MEJORA CONTINUA (RLHF)', ORANGE)

rlhf = [
    ('Operario califica\n[Util][FP][Mant]', ORANGE),
    ('historial_alertas\nScore: 1.0/0.5/0.0', PURPLE),
    ('Few-shot +\nAntipatrones', ORANGE),
    ('Inyecta en\nproximo prompt', RED),
    ('Deriva >30% FP\n-> recalibrar', RED),
]
for i, (t, c) in enumerate(rlhf):
    x = 0.5 + i * 3.5
    light_box(x, Y - 0.5, 3.1, 0.7, c, t, ts=9)
    if i < len(rlhf) - 1:
        arrow_r(x + 3.1, Y - 0.15, x + 3.5, c)

# ═══════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════
stats = '11,451 lineas  |  26 modulos  |  5 APIs Google Cloud  |  7 herramientas  |  18/20 conceptos del curso'
ax.text(10, 1.0, stats, ha='center', fontsize=10, color=NAVY, fontweight='bold', fontfamily='sans-serif',
        bbox=dict(boxstyle='round,pad=0.4', facecolor=ICE, edgecolor=NAVY, lw=1.5))

# ═══════════════════════════════════════════════════════
# GUARDAR
# ═══════════════════════════════════════════════════════
plt.tight_layout(pad=0.3)
base = r'C:\Users\USUARIO\Desktop\Maestria\sistemasinteligentes\proyecto\docs'
png_path = os.path.join(base, 'Pipeline_Completo_v2.png')
pdf_path = os.path.join(base, 'Pipeline_Completo_v2.pdf')

fig.savefig(png_path, dpi=200, bbox_inches='tight', facecolor=WHITE)
fig.savefig(pdf_path, format='pdf', bbox_inches='tight', facecolor=WHITE)
plt.close()

print(f'PNG: {png_path} ({os.path.getsize(png_path)/1024:.0f} KB)')
print(f'PDF: {pdf_path} ({os.path.getsize(pdf_path)/1024:.0f} KB)')
