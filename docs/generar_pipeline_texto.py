"""
Pipeline completo en formato texto/ASCII - exportado a PDF.
"""
from fpdf import FPDF
import os

class PipelinePDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 5, 'Universidad Nacional de Colombia | Facultad de Minas | Sistemas Inteligentes', align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'Pagina {self.page_no()}', align='C')

pdf = PipelinePDF('P', 'mm', 'Letter')
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_page()

# ─── Helpers ───
def titulo(texto):
    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_text_color(30, 39, 65)
    pdf.cell(0, 10, texto, align='C', new_x='LMARGIN', new_y='NEXT')

def subtitulo(texto):
    pdf.set_font('Helvetica', '', 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, texto, align='C', new_x='LMARGIN', new_y='NEXT')

def seccion(num, texto):
    pdf.ln(4)
    pdf.set_font('Courier', 'B', 11)
    pdf.set_text_color(30, 39, 65)
    linea = f'{"="*78}'
    pdf.cell(0, 5, linea, new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Courier', 'B', 12)
    pdf.cell(0, 6, f'  [{num}] {texto}', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Courier', 'B', 11)
    pdf.cell(0, 5, linea, new_x='LMARGIN', new_y='NEXT')
    pdf.ln(1)

def linea(texto, indent=0):
    pdf.set_font('Courier', '', 9)
    pdf.set_text_color(50, 50, 50)
    prefix = '  ' * indent
    pdf.cell(0, 4.5, f'{prefix}{texto}', new_x='LMARGIN', new_y='NEXT')

def linea_bold(texto, indent=0):
    pdf.set_font('Courier', 'B', 9)
    pdf.set_text_color(30, 39, 65)
    prefix = '  ' * indent
    pdf.cell(0, 4.5, f'{prefix}{texto}', new_x='LMARGIN', new_y='NEXT')

def flecha():
    pdf.set_font('Courier', '', 9)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 4, '                              |', new_x='LMARGIN', new_y='NEXT')
    pdf.cell(0, 4, '                              v', new_x='LMARGIN', new_y='NEXT')

def separador():
    pdf.set_font('Courier', '', 8)
    pdf.set_text_color(200, 200, 200)
    pdf.cell(0, 3, f'  {"- "*39}', new_x='LMARGIN', new_y='NEXT')

# ═══════════════════════════════════════════════════════
# CONTENIDO
# ═══════════════════════════════════════════════════════

titulo('Pipeline Completo del Sistema')
subtitulo('Sistema de Monitoreo de Peletizacion con LLM Multimodal')
pdf.ln(3)

# ─── 1. TELEMETRIA ───
seccion(1, 'TELEMETRIA (Fuente de datos)')
linea('+--------------------------+     +---------------------------+')
linea('|     CSV Planta           |     |     Datos Maestros        |')
linea('| telemetria_planta_001    |     | maestro_formulas.csv      |')
linea('| polling cada 60 seg      |     | maestro_equipos.csv       |')
linea('|                          |     | maestro_personal.csv      |')
linea('+-----------+--------------+     +-------------+-------------+')
linea('            |                                   |')
linea('            +----------------+------------------+')
linea('                             |')

flecha()

# ─── 2. MOTOR DE REGLAS ───
seccion(2, 'MOTOR DE REGLAS DETERMINISTA (ISA-18.2)')
linea('+------------+    +------------+    +------------+    +----------+    +--------+')
linea('|    EMA     | -> | Maquina de | -> | Histeresis | -> | Anti-    | -> | ALERTA |')
linea('| alpha=0.3  |    |  Estados   |    | 2 lecturas |    |  spam    |    | CONFIR |')
linea('| Suaviza    |    | NORMAL     |    | de confir- |    | Max N    |    | MADA   |')
linea('| ruido del  |    | BAJA       |    | macion     |    | alertas  |    |        |')
linea('| sensor     |    | ALTA       |    | antes de   |    | por      |    |        |')
linea('|            |    |            |    | disparar   |    | ventana  |    |        |')
linea('+------------+    +------------+    +------------+    +----------+    +--------+')
linea('')
linea_bold('  Por que ISA-18.2: Evita alarm flooding, chattering y alarm fatigue.')
linea_bold('  La seguridad de disparo es DETERMINISTA, no depende del LLM.')

flecha()

# ─── 3. FEATURE STORE ───
seccion(3, 'FEATURE STORE (Analisis numerico para el LLM)')
linea('+--------------------+  +------------------+  +-----------------+  +----------------+')
linea('| Capa 1: Tasa de    |  | Capa 2: Matriz   |  | Capa 3: Corre-  |  | Capa 4: Score  |')
linea('| cambio por variable|  | diagnostica 3x3  |  | laciones Pearson|  | anomalia global|')
linea('|                    |  |                  |  |                 |  |                |')
linea('| -2.3 C/min         |  | Temp x Presion   |  | temp-pres: 0.85 |  | 0.0 = normal   |')
linea('| DESCENDENTE        |  | 9 estados posib. |  | temp-corr: 0.60 |  | 1.0 = critico  |')
linea('| -2.8 sigma         |  | Solo 1 es normal |  | Detecta anomal. |  | Combina todo   |')
linea('| 4:30 fuera banda   |  |                  |  |                 |  |                |')
linea('+--------------------+  +------------------+  +-----------------+  +----------------+')
linea('')
linea_bold('  Transforma datos crudos en SEMANTICA que el LLM puede razonar.')
linea_bold('  Sin esto, Gemini solo ve "temp=56". Con esto ve "cayendo rapido, anomala".')

flecha()

# ─── 4. RAG ───
seccion(4, 'RAG con ChromaDB (Retrieval-Augmented Generation)')
linea('+--------------------------------------+  +------------------------------------+')
linea('| ChromaDB (Vector Store)              |  | Embeddings                         |')
linea('| Coleccion: fallas_planta             |  | all-MiniLM-L6-v2                   |')
linea('| Coleccion: incidentes_historicos     |  | 384 dimensiones                    |')
linea('| Persistencia local en disco          |  | sentence-transformers (local)      |')
linea('+--------------------------------------+  +------------------------------------+')
linea('')
linea_bold('  BUSQUEDA SEMANTICA por similitud vectorial:')
linea('    - Top 3 fallas mas similares a la alerta actual')
linea('    - Top 2 incidentes historicos relevantes')
linea('    - Resultado inyectado en el prompt de Gemini')
linea('')
linea_bold('  INDEXACION AUTOMATICA:')
linea('    - Al cerrar incidente, la conversacion se indexa en ChromaDB')
linea('    - Proximas alertas similares recuperan ese conocimiento')
linea('    - El sistema APRENDE de cada incidente resuelto')
linea('')
linea_bold('  NO entrenamos el modelo. El conocimiento se RECUPERA semanticamente')
linea_bold('  y se INYECTA en el prompt. ChromaDB reemplaza busqueda por keyword.')

flecha()

# ─── 5. HUMAN-IN-THE-LOOP ───
seccion(5, 'HUMAN-IN-THE-LOOP FEEDBACK CON PROMPT OPTIMIZATION')
linea('+-------------------------------+      +-------------------------------+')
linea('|  FEEDBACK IMPLICITO           |      |  FEW-SHOT INJECTION           |')
linea('|  Analisis de la conversacion  |      |  Mejores prescripciones       |')
linea('|  completa al cerrar incidente |      |  se inyectan como ejemplos    |')
linea('|  Auto-rating: score 0.0-1.0  |      |  en el prompt de Gemini       |')
linea('|  Sin botones de calificacion  |      |  Antipatrones como "NO hagas" |')
linea('+-------------------------------+      +-------------------------------+')
linea('')
linea_bold('  IMPORTANTE: Esto NO es RLHF (no hay reward model ni fine-tuning).')
linea_bold('  Es PROMPT OPTIMIZATION con feedback humano implicito:')
linea('    - Al cerrar incidente, se analiza la conversacion completa')
linea('    - Se auto-califica la prescripcion (score 0.0 a 1.0)')
linea('    - Las mejores se inyectan como few-shot en proximos prompts')
linea('    - Si FP > 30% en 14 dias -> detecta DERIVA y alerta')
linea('')
linea_bold('  El sistema MEJORA con cada interaccion sin reentrenamiento.')
linea_bold('  No se modifica el modelo - se mejora el CONTEXTO del prompt.')

flecha()

pdf.add_page()

# ─── 6. LLM MULTIMODAL ───
seccion(6, 'LLM MULTIMODAL + LOOP AGENTICO (Gemini 2.5 Flash)')
linea('')
linea_bold('  Gemini recibe en UNA sola llamada:')
linea('  +----------+  +----------+  +----------+  +----------+  +----------+')
linea('  | Prompt   |  | Imagen   |  | GIF      |  | Audio    |  | Foto     |')
linea('  | RAG +    |  | PNG del  |  | animado  |  | del      |  | del      |')
linea('  | Features |  | panel de |  | 30s de   |  | operario |  | equipo   |')
linea('  |+few-shot |  | tendencia|  | evolucion|  | (STT)    |  | (vision) |')
linea('  +----------+  +----------+  +----------+  +----------+  +----------+')
linea('')
linea_bold('  LOOP AGENTICO (patron ReAct - max 5 iteraciones):')
linea('')
linea('  Iteracion 1: Gemini ANALIZA alerta + features + imagen + GIF')
linea('  Iteracion 2: Gemini DECIDE -> "necesito historial" -> llama herramienta')
linea('  Iteracion 3: Gemini RECIBE resultado -> RAZONA de nuevo')
linea('  Iteracion 4: Gemini DECIDE -> "ya tengo suficiente" -> genera prescripcion')
linea('')
linea_bold('  7 HERRAMIENTAS (Gemini elige cuales usar via Function Calling):')
linea('')
linea('  +---------------------+  +---------------------+  +---------------------+')
linea('  | consultar_historial |  | obtener_formula     |  | obtener_operario    |')
linea('  | Alertas pasadas     |  | Limites T/P activos |  | Quien esta de turno |')
linea('  +---------------------+  +---------------------+  +---------------------+')
linea('  +---------------------+  +---------------------+  +---------------------+')
linea('  | ajustar_umbral      |  | escalar_supervisor  |  | registrar_accion    |')
linea('  | Con limites seguros |  | Cola thread-safe    |  | Persiste en CSV     |')
linea('  +---------------------+  +---------------------+  +---------------------+')
linea('  +---------------------+')
linea('  | analizar_feedback   |')
linea('  | Tasa FP + deriva    |')
linea('  +---------------------+')
linea('')
linea_bold('  Es un agente REAL: Gemini DECIDE que herramientas usar,')
linea_bold('  en que orden, y cuando tiene suficiente info. No hay if/else.')

flecha()

linea('  +============================================+')
linea('  |        PRESCRIPCION INTELIGENTE            |')
linea('  |  "La temp cae a 2.3 C/min pero la presion |')
linea('  |   esta estable. Vapor llega pero no        |')
linea('  |   transfiere. Revise trampa TD42."         |')
linea('  +============================================+')

separador()
linea_bold('  [OPCIONAL] Shadow Mode / A/B Testing:')
linea('  Variante A (control) vs Variante B (challenger) en paralelo')
linea('  ThreadPoolExecutor(max_workers=2) - operario no espera el doble')

flecha()

pdf.add_page()

# ─── 7. TELEGRAM ───
seccion(7, 'COMUNICACION MULTIMODAL (Telegram)')
linea('')
linea_bold('  SISTEMA -> OPERARIO (mensajes limpios):')
linea('  +----------+  +----------+  +----------+')
linea('  | Texto    |  | Imagen   |  | PDF      |')
linea('  | alerta   |  | panel    |  | reporte  |')
linea('  | limpio   |  | PNG      |  | ejecutivo|')
linea('  +----------+  +----------+  +----------+')
linea('')
linea_bold('  Mensajes simplificados:')
linea('    - Sin mensajes de estado ni texto de ayuda')
linea('    - "Posible causa" en lugar de "Causa" (mas honesto)')
linea('    - Sin botones de calificacion (feedback implicito)')
linea('')
linea_bold('  OPERARIO -> SISTEMA:')
linea('  +----------+  +----------+  +----------+')
linea('  | Audio    |  | Texto    |  | Foto     |')
linea('  | nota de  |  | libre    |  | del      |')
linea('  | voz      |  | teclado  |  | equipo   |')
linea('  | (STT)    |  |          |  | (vision) |')
linea('  +----------+  +----------+  +----------+')
linea('')
linea('  +======================================================================+')
linea('  | MEMORIA DE CONVERSACION                                              |')
linea('  | Maria recuerda TODO lo dicho en el incidente.                        |')
linea('  | La ultima foto se persiste y se incluye en llamadas futuras.         |')
linea('  | Al cerrar, la conversacion se indexa en ChromaDB para RAG futuro.    |')
linea('  +======================================================================+')

flecha()

# ─── 8. NANOBANANA ───
seccion(8, 'NANOBANANA (Generacion de fichas visuales con IA)')
linea('+-------------------------------+      +-------------------------------+')
linea('|  Gemini Image Generation      | ---> |  Ficha Visual PNG             |')
linea('|  response_modalities=         |      |  - Ficha de cierre            |')
linea('|    [TEXT, IMAGE]              |      |  - Ficha operario             |')
linea('|                               |      |  - Ficha gerencial            |')
linea('|  Input: panel proceso + prompt|      |  IMAGEN GENERADA POR IA       |')
linea('+-------------------------------+      +-------------------------------+')
linea('')
linea_bold('  NanoBanana no recorta ni copia - GENERA imagenes nuevas con IA.')
linea_bold('  Es Generative AI aplicada a comunicacion industrial.')

flecha()

# ─── 9. EMAIL ───
seccion(9, 'EMAIL AL SUPERVISOR (SMTP)')
linea('+-------------------------------+      +-------------------------------+')
linea('|  EmailService                 | ---> |  Supervisor recibe:           |')
linea('|  SMTP + TLS                   |      |  - Ficha PNG adjunta          |')
linea('|  Configurable via .env        |      |  - Resumen HTML del incidente |')
linea('|                               |      |  - Datos de la lectura        |')
linea('|  Se envia automaticamente     |      |  - Registro auditable         |')
linea('|  al cerrar un incidente       |      |                               |')
linea('+-------------------------------+      +-------------------------------+')

pdf.ln(3)
separador()

# ─── FLUJO DE CIERRE ───
seccion('', 'FLUJO COMPLETO DE CIERRE DE INCIDENTE')
linea('')
linea(' Operario      NanoBanana     Telegram       Email SMTP     Persistir      Reanudar')
linea(' dice algo     genera         envia          al             conversacion   monitoreo')
linea(' como "listo"  ficha visual   ficha a chat   supervisor     a ChromaDB     automatico')
linea(' o "resuelto"                                               + CSV')
linea('     |              |              |              |              |              |')
linea('     +-------> -----+-------> -----+-------> -----+-------> -----+-------> -----+')
linea('')
linea_bold('  CIERRE NATURAL (sin botones):')
linea('    El operario cierra diciendo "solucionado", "listo", "resuelto", etc.')
linea('    Gemini detecta la intencion de cierre en lenguaje natural.')
linea('    No hay botones de cierre - la conversacion fluye naturalmente.')

separador()
pdf.add_page()

# ─── RESILIENCIA ───
seccion(10, 'RESILIENCIA (Circuit Breaker + Gemma 2B)')
linea('')
linea('  +============+   3 fallos   +=============+   5 min    +===============+')
linea('  |  CERRADO   | -----------> |   ABIERTO   | --------> | SEMI-ABIERTO  |')
linea('  |  Gemini OK |              | Gemma 2B    |           | Prueba Gemini |')
linea('  |            | <----------- |  local CPU  |           |    1 vez      |')
linea('  +============+    exito     +=============+           +===============+')
linea('')
linea_bold('  Gemma 2B (Knowledge Distillation de Gemini):')
linea('    - 1.5 GB RAM (no necesita GPU)')
linea('    - ~800ms latencia en CPU')
linea('    - Espanol nativo')
linea('    - Corre via Ollama (localhost:11434)')
linea('    - Prompt comprimido (~500 tokens vs ~3000 de Gemini)')
linea('')
linea_bold('  Retry con backoff exponencial: 4s -> 8s -> 16s antes de abrir circuito.')
linea('')
linea_bold('  Comandos de prueba para testing:')
linea('    /fallback  - Fuerza apertura del circuito (usa Gemma 2B)')
linea('    /gemini    - Fuerza cierre del circuito (vuelve a Gemini)')

pdf.ln(3)
separador()

# ─── SEGURIDAD ───
seccion(11, 'SEGURIDAD')
linea('')
linea('  +---------------------------------------+  +--------------------------------+')
linea('  | Anti Prompt-Injection                  |  | Limites Hardcodeados           |')
linea('  |                                        |  |                                |')
linea('  | Mensajes fuera de tema -> rechaza      |  | Presion:     2 - 45 PSI        |')
linea('  | y redirige al incidente activo.        |  | Temperatura: 40 - 120 C        |')
linea('  |                                        |  | Corriente:   0 - 490 A         |')
linea('  | Con incidente: "Sigamos con el         |  |                                |')
linea('  |   diagnostico de la 301..."            |  | Sin acceso a shell ni          |')
linea('  | Sin incidente: "Estoy para ayudarte    |  | filesystem.                    |')
linea('  |   con la operacion de la planta."      |  | Credenciales fuera del prompt. |')
linea('  +---------------------------------------+  +--------------------------------+')

pdf.ln(3)
separador()

# ─── FEEDBACK LOOP ───
seccion('', 'CICLO DE MEJORA CONTINUA (Prompt Optimization)')
linea('')
linea('  Operario       Analisis de      Few-shot +      Se inyecta en     Deteccion')
linea('  cierra          conversacion    Antipatrones    proximo prompt    de deriva')
linea('  incidente      Auto-rating      generados       de Gemini         >30% FP')
linea('  naturalmente   score 0.0-1.0   automaticamente automaticamente   en 14 dias')
linea('')
linea('     |               |                |               |               |')
linea('     +--------> -----+--------> ------+--------> -----+--------> -----+')
linea('')
linea_bold('  El sistema MEJORA con cada interaccion del operario.')
linea_bold('  No se modifica el modelo - se mejora el CONTEXTO del prompt.')
linea_bold('  Feedback IMPLICITO, no botones. Se analiza la conversacion.')

pdf.ln(3)
separador()

# ─── PERSISTENCIA ───
seccion('', 'PERSISTENCIA (CSV)')
linea('')
linea('  +----------------------+  +-------------------------+  +---------------------------+')
linea('  | historial_alertas    |  | historial_incidentes    |  | historial_conversaciones  |')
linea('  | Alertas + feedback   |  | Apertura/cierre         |  | Dialogo completo op-Maria |')
linea('  +----------------------+  +-------------------------+  +---------------------------+')
linea('  +----------------------+  +-------------------------+  +---------------------------+')
linea('  | historial_audio      |  | historial_eventos       |  | shadow_log                |')
linea('  | Transcripciones voz  |  | Cada accion en incid.   |  | A/B testing resultados    |')
linea('  +----------------------+  +-------------------------+  +---------------------------+')

pdf.ln(5)

# ─── STATS ───
pdf.set_font('Courier', 'B', 11)
pdf.set_text_color(30, 39, 65)
pdf.cell(0, 6, '=' * 78, align='C', new_x='LMARGIN', new_y='NEXT')
pdf.cell(0, 7, '11,451 lineas | 26 modulos | 5 APIs Google Cloud | 7 herramientas | 18/20 conceptos', align='C', new_x='LMARGIN', new_y='NEXT')
pdf.cell(0, 6, '=' * 78, align='C', new_x='LMARGIN', new_y='NEXT')

# ─── GUARDAR ───
out = r'C:\Users\USUARIO\Desktop\Maestria\sistemasinteligentes\proyecto\docs\Pipeline_Completo.pdf'
pdf.output(out)
print(f'PDF generado: {out} ({os.path.getsize(out)/1024:.0f} KB)')
