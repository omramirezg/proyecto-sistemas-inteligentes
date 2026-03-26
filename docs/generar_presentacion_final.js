const PptxGenJS = require("pptxgenjs");
const fs = require("fs");

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_16x9";
pptx.author = "Omar Ramirez";

// ─── Design System ───
const C = {
  navy: "1E2761",
  ice: "CADCFC",
  white: "FFFFFF",
  dark: "0D1B2A",
  accent: "2E75B6",
  gray: "666666",
  lightGray: "F2F6FC",
  green: "28A745",
  orange: "FF8C00",
  red: "DC3545",
};

const FONT_TITLE = "Arial Black";
const FONT_BODY = "Arial";

// Helper: add footer to every slide
function addFooter(slide) {
  slide.addText("Universidad Nacional de Colombia | Facultad de Minas | Sistemas Inteligentes", {
    x: 0.5, y: 7.0, w: 9.0, h: 0.3,
    fontSize: 8, color: C.gray, fontFace: FONT_BODY,
  });
}

// Helper: dark title slide
function darkSlide(pptx) {
  const s = pptx.addSlide();
  s.background = { color: C.dark };
  return s;
}
// Helper: light content slide
function lightSlide(pptx) {
  const s = pptx.addSlide();
  s.background = { color: C.white };
  // Top bar
  s.addShape(pptx.ShapeType.rect, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: C.navy } });
  return s;
}

// ─── Images ───
const imgDir = "C:\\Users\\USUARIO\\Desktop\\Maestria\\sistemasinteligentes\\proyecto\\";
const img1 = fs.existsSync(imgDir + "sis1.jpg") ? fs.readFileSync(imgDir + "sis1.jpg").toString("base64") : null;
const img2 = fs.existsSync(imgDir + "sis2.jpg") ? fs.readFileSync(imgDir + "sis2.jpg").toString("base64") : null;
const img3 = fs.existsSync(imgDir + "sis3.jpg") ? fs.readFileSync(imgDir + "sis3.jpg").toString("base64") : null;
const img4 = fs.existsSync(imgDir + "sis4.jpg") ? fs.readFileSync(imgDir + "sis4.jpg").toString("base64") : null;
const img5 = fs.existsSync(imgDir + "sis5.jpg") ? fs.readFileSync(imgDir + "sis5.jpg").toString("base64") : null;

// ═══════════════════════════════════════════════════════
// SLIDE 1 — PORTADA
// ═══════════════════════════════════════════════════════
let s = darkSlide(pptx);
s.addText("SISTEMAS INTELIGENTES", { x: 0.8, y: 0.6, w: 8.4, h: 0.4, fontSize: 14, color: C.ice, fontFace: FONT_BODY, letterSpacing: 5 });
s.addText("Sistema de Monitoreo de\nPeletizacion con LLM Multimodal", {
  x: 0.8, y: 1.3, w: 8.4, h: 1.6, fontSize: 36, color: C.white, fontFace: FONT_TITLE, bold: true, lineSpacing: 44,
});
s.addText("Prescripciones inteligentes en tiempo real mediante\nGemini 2.5 Flash, RAG con ChromaDB, Agentic AI y Tool Use", {
  x: 0.8, y: 3.1, w: 8.4, h: 0.8, fontSize: 16, color: C.ice, fontFace: FONT_BODY, italic: true,
});
// Stats row
const stats = [
  { n: "11,451", l: "lineas de codigo" },
  { n: "26", l: "modulos Python" },
  { n: "5", l: "APIs Google Cloud" },
  { n: "18/20", l: "conceptos del curso" },
];
stats.forEach((st, i) => {
  const xBase = 0.8 + i * 2.2;
  s.addText(st.n, { x: xBase, y: 4.4, w: 2.0, h: 0.5, fontSize: 28, color: C.white, fontFace: FONT_TITLE, bold: true });
  s.addText(st.l, { x: xBase, y: 4.9, w: 2.0, h: 0.3, fontSize: 11, color: C.ice, fontFace: FONT_BODY });
});
s.addText("Brian | Omar | Isabela", { x: 0.8, y: 5.8, w: 4, h: 0.3, fontSize: 14, color: C.ice, fontFace: FONT_BODY });
s.addText("Marzo 2026", { x: 0.8, y: 6.2, w: 4, h: 0.3, fontSize: 12, color: C.gray, fontFace: FONT_BODY });
s.addText("Universidad Nacional de Colombia | Facultad de Minas", {
  x: 0.8, y: 7.0, w: 8.4, h: 0.3, fontSize: 9, color: C.gray, fontFace: FONT_BODY,
});

// ═══════════════════════════════════════════════════════
// SLIDE 2 — PROBLEMA
// ═══════════════════════════════════════════════════════
s = lightSlide(pptx);
s.addText("1", { x: 0.5, y: 0.3, w: 0.5, h: 0.5, fontSize: 24, color: C.white, fontFace: FONT_TITLE, fill: { color: C.navy }, align: "center", valign: "middle", rectRadius: 0.1 });
s.addText("El Problema Industrial", { x: 1.2, y: 0.3, w: 6, h: 0.5, fontSize: 28, color: C.navy, fontFace: FONT_TITLE, bold: true });

// Before/After
s.addShape(pptx.ShapeType.rect, { x: 0.5, y: 1.2, w: 4.2, h: 2.8, fill: { color: "FFF0F0" }, rectRadius: 0.1 });
s.addText("ANTES", { x: 0.7, y: 1.3, w: 2, h: 0.35, fontSize: 14, color: C.red, fontFace: FONT_TITLE, bold: true });
s.addText(
  "Alertas genericas inutiles:\n\"Temperatura baja, revise el equipo\"\n\n" +
  "El operario no sabe:\n  - Que revisar primero\n  - Cual es la causa probable\n  - Que tan urgente es\n\n" +
  "Resultado: fatiga de alarmas,\nproducto fuera de especificacion",
  { x: 0.7, y: 1.7, w: 3.8, h: 2.2, fontSize: 12, color: "333333", fontFace: FONT_BODY, lineSpacing: 16 }
);

s.addShape(pptx.ShapeType.rect, { x: 5.3, y: 1.2, w: 4.2, h: 2.8, fill: { color: "F0FFF0" }, rectRadius: 0.1 });
s.addText("DESPUES (nuestro sistema)", { x: 5.5, y: 1.3, w: 3.8, h: 0.35, fontSize: 14, color: C.green, fontFace: FONT_TITLE, bold: true });
s.addText(
  "Prescripciones inteligentes:\n\"La temp cae a 2.3 C/min pero la\npresion esta estable en 18 PSI.\nVapor llega pero no transfiere.\nRevise trampa TD42, purgue\ncondensado por valvula inferior.\"\n\n" +
  "El operario sabe EXACTAMENTE\nque hacer y por que.",
  { x: 5.5, y: 1.7, w: 3.8, h: 2.2, fontSize: 12, color: "333333", fontFace: FONT_BODY, lineSpacing: 16 }
);

// Key message
s.addShape(pptx.ShapeType.rect, { x: 0.5, y: 4.3, w: 9.0, h: 0.6, fill: { color: C.lightGray }, rectRadius: 0.08 });
s.addText("Objetivo: Convertir telemetria cruda en prescripciones accionables mediante LLM multimodal + RAG (ChromaDB) + Human-in-the-Loop Feedback + Agentic AI", {
  x: 0.7, y: 4.35, w: 8.6, h: 0.5, fontSize: 13, color: C.navy, fontFace: FONT_BODY, bold: true,
});

// Tech stack mini
s.addText("Stack tecnologico:", { x: 0.5, y: 5.2, w: 9, h: 0.3, fontSize: 12, color: C.navy, fontFace: FONT_BODY, bold: true });
const techs = ["Gemini 2.5 Flash", "Vertex AI", "Pub/Sub", "Telegram", "Gemma 2B", "NanoBanana", "SMTP", "Python 3.11"];
techs.forEach((t, i) => {
  s.addShape(pptx.ShapeType.rect, { x: 0.5 + i * 1.15, y: 5.55, w: 1.1, h: 0.35, fill: { color: C.navy }, rectRadius: 0.05 });
  s.addText(t, { x: 0.5 + i * 1.15, y: 5.55, w: 1.1, h: 0.35, fontSize: 8, color: C.white, fontFace: FONT_BODY, align: "center", valign: "middle" });
});
addFooter(s);

// ═══════════════════════════════════════════════════════
// SLIDE 3 — ARQUITECTURA
// ═══════════════════════════════════════════════════════
s = lightSlide(pptx);
s.addText("2", { x: 0.5, y: 0.3, w: 0.5, h: 0.5, fontSize: 24, color: C.white, fontFace: FONT_TITLE, fill: { color: C.navy }, align: "center", valign: "middle", rectRadius: 0.1 });
s.addText("Arquitectura del Pipeline (10 capas)", { x: 1.2, y: 0.3, w: 7, h: 0.5, fontSize: 26, color: C.navy, fontFace: FONT_TITLE, bold: true });

const layers = [
  { n: "1", t: "Telemetria", d: "CSV / Pub/Sub", c: C.gray },
  { n: "2", t: "Motor Reglas", d: "ISA-18.2 + EMA", c: "2C5F2D" },
  { n: "3", t: "Feature Store", d: "Matriz 3x3 + Pearson", c: C.accent },
  { n: "4", t: "RAG", d: "YAML + CSV + Maestros", c: "7B2D8E" },
  { n: "5", t: "Feedback", d: "Few-shot adaptativo", c: C.orange },
  { n: "6", t: "LLM Agentico", d: "Gemini + 7 tools", c: C.red },
  { n: "7", t: "Shadow Mode", d: "A/B testing paralelo", c: "555555" },
  { n: "8", t: "Telegram", d: "Audio+texto+foto+PDF", c: C.navy },
  { n: "9", t: "NanoBanana", d: "Fichas visuales con IA", c: "B85042" },
  { n: "10", t: "Email Supervisor", d: "Correo SMTP de cierre", c: "065A82" },
];
layers.forEach((l, i) => {
  const yBase = 1.1 + i * 0.52;
  // Number circle
  s.addShape(pptx.ShapeType.ellipse, { x: 0.6, y: yBase + 0.05, w: 0.4, h: 0.4, fill: { color: l.c } });
  s.addText(l.n, { x: 0.6, y: yBase + 0.05, w: 0.4, h: 0.4, fontSize: 14, color: C.white, fontFace: FONT_TITLE, align: "center", valign: "middle" });
  // Bar
  s.addShape(pptx.ShapeType.rect, { x: 1.2, y: yBase, w: 5.0, h: 0.5, fill: { color: C.lightGray }, rectRadius: 0.05, line: { color: l.c, width: 1 } });
  s.addText(l.t, { x: 1.4, y: yBase, w: 2.2, h: 0.5, fontSize: 13, color: l.c, fontFace: FONT_BODY, bold: true, valign: "middle" });
  s.addText(l.d, { x: 3.6, y: yBase, w: 2.4, h: 0.5, fontSize: 11, color: C.gray, fontFace: FONT_BODY, valign: "middle" });
  // Arrow
  if (i < layers.length - 1) {
    s.addText("\u25BC", { x: 0.65, y: yBase + 0.45, w: 0.3, h: 0.2, fontSize: 10, color: C.gray, fontFace: FONT_BODY, align: "center" });
  }
});

// Right side: key insight
s.addShape(pptx.ShapeType.rect, { x: 6.5, y: 1.1, w: 3.2, h: 5.0, fill: { color: C.lightGray }, rectRadius: 0.1 });
s.addText("Diseno modular", { x: 6.7, y: 1.2, w: 2.8, h: 0.4, fontSize: 16, color: C.navy, fontFace: FONT_TITLE, bold: true });
s.addText(
  "Cada capa es independiente.\n\n" +
  "Si el LLM falla, el motor de reglas sigue operando.\n\n" +
  "Si el Feature Store falla, Gemini recibe datos basicos.\n\n" +
  "Si Gemini falla, Gemma 2B local toma el control.\n\n" +
  "Degradacion graceful: el sistema NUNCA se cae completamente.",
  { x: 6.7, y: 1.7, w: 2.8, h: 4.2, fontSize: 11, color: "333333", fontFace: FONT_BODY, lineSpacing: 15 }
);
addFooter(s);

// ═══════════════════════════════════════════════════════
// SLIDE 4 — RAG + FEEDBACK + FEATURE STORE
// ═══════════════════════════════════════════════════════
s = lightSlide(pptx);
s.addText("3", { x: 0.5, y: 0.3, w: 0.5, h: 0.5, fontSize: 24, color: C.white, fontFace: FONT_TITLE, fill: { color: C.navy }, align: "center", valign: "middle", rectRadius: 0.1 });
s.addText("RAG (ChromaDB) + Human-in-the-Loop Feedback + Feature Store", { x: 1.2, y: 0.25, w: 8.3, h: 0.5, fontSize: 22, color: C.navy, fontFace: FONT_TITLE, bold: true });

// Three columns
const cols = [
  { title: "RAG + ChromaDB", sub: "(Lecture 5)", color: "7B2D8E", items: [
    "ChromaDB como vector store",
    "Embeddings all-MiniLM-L6-v2",
    "Busqueda semantica de fallas e incidentes",
    "Top 3 fallas + Top 2 incidentes por alerta",
    "Conversaciones se indexan al cerrar",
  ]},
  { title: "Feedback Implicito", sub: "(Human-in-the-Loop)", color: C.orange, items: [
    "NO es RLHF (no modifica el modelo)",
    "Auto-califica analizando conversacion",
    "Prescripciones exitosas -> few-shot",
    "Prescripciones fallidas -> antipatron",
    "Prompt optimization con feedback humano",
    ">30% FP en 14 dias -> alerta de deriva",
  ]},
  { title: "Feature Store", sub: "(Ingenieria)", color: C.accent, items: [
    "Tasa de cambio (-2.3 C/min)",
    "Tendencia (DESCENDENTE)",
    "Matriz 3x3 (temp x presion)",
    "Correlacion Pearson (anomala)",
    "Score anomalia global (0-1)",
    "Gemini razona con numeros, no solo estados",
  ]},
];
cols.forEach((col, i) => {
  const xBase = 0.5 + i * 3.15;
  s.addShape(pptx.ShapeType.rect, { x: xBase, y: 1.0, w: 3.0, h: 0.55, fill: { color: col.color }, rectRadius: 0.08 });
  s.addText(col.title + " " + col.sub, { x: xBase, y: 1.0, w: 3.0, h: 0.55, fontSize: 14, color: C.white, fontFace: FONT_TITLE, bold: true, align: "center", valign: "middle" });
  col.items.forEach((item, j) => {
    s.addText("\u2022 " + item, { x: xBase + 0.1, y: 1.7 + j * 0.42, w: 2.8, h: 0.4, fontSize: 10, color: "333333", fontFace: FONT_BODY, lineSpacing: 13 });
  });
});

// Bottom: Why not fine-tuning
s.addShape(pptx.ShapeType.rect, { x: 0.5, y: 4.5, w: 9.0, h: 1.2, fill: { color: C.lightGray }, rectRadius: 0.08 });
s.addText("Por que RAG y no Fine-tuning?", { x: 0.7, y: 4.55, w: 8.5, h: 0.35, fontSize: 14, color: C.navy, fontFace: FONT_BODY, bold: true });
s.addText(
  "1) Datos insuficientes (~50 incidentes vs miles necesarios)  |  " +
  "2) El conocimiento cambia (nuevas formulas) - RAG se actualiza sin reentrenar  |  " +
  "3) Evitamos catastrophic forgetting (Lecture 10) al no modificar pesos del modelo",
  { x: 0.7, y: 4.95, w: 8.5, h: 0.7, fontSize: 11, color: "333333", fontFace: FONT_BODY, lineSpacing: 15 }
);
addFooter(s);

// ═══════════════════════════════════════════════════════
// SLIDE 5 — AGENTIC AI
// ═══════════════════════════════════════════════════════
s = lightSlide(pptx);
s.addText("4", { x: 0.5, y: 0.3, w: 0.5, h: 0.5, fontSize: 24, color: C.white, fontFace: FONT_TITLE, fill: { color: C.navy }, align: "center", valign: "middle", rectRadius: 0.1 });
s.addText("Fundamentacion Teorica II: Agentic AI + Multimodal", { x: 1.2, y: 0.25, w: 8.3, h: 0.5, fontSize: 22, color: C.navy, fontFace: FONT_TITLE, bold: true });

// Left: Agent loop
s.addText("Loop Agentico ReAct (Lecture 7)", { x: 0.5, y: 1.0, w: 4.5, h: 0.4, fontSize: 14, color: C.navy, fontFace: FONT_BODY, bold: true });
const agentSteps = [
  "Gemini ANALIZA la alerta + features + imagen + GIF",
  "DECIDE: 'necesito el historial de esta maquina'",
  "LLAMA: consultar_historial(id_maquina=301)",
  "RECIBE resultado y RAZONA de nuevo",
  "DECIDE: 'ya tengo suficiente contexto'",
  "GENERA prescripcion final especifica",
];
agentSteps.forEach((step, i) => {
  const yBase = 1.5 + i * 0.52;
  s.addShape(pptx.ShapeType.rect, { x: 0.5, y: yBase, w: 0.35, h: 0.35, fill: { color: i < 3 ? C.accent : (i < 5 ? C.orange : C.green) }, rectRadius: 0.05 });
  s.addText(String(i + 1), { x: 0.5, y: yBase, w: 0.35, h: 0.35, fontSize: 11, color: C.white, fontFace: FONT_TITLE, align: "center", valign: "middle" });
  s.addText(step, { x: 0.95, y: yBase, w: 4.0, h: 0.4, fontSize: 10.5, color: "333333", fontFace: FONT_BODY, valign: "middle" });
});

// Right: 7 tools + Multimodal
s.addText("7 Herramientas del Agente", { x: 5.3, y: 1.0, w: 4.3, h: 0.4, fontSize: 14, color: C.navy, fontFace: FONT_BODY, bold: true });
const tools = [
  "consultar_historial (alertas pasadas)",
  "obtener_formula_activa (limites T/P)",
  "obtener_operario_turno (quien opera)",
  "ajustar_umbral (con limites de seguridad)",
  "escalar_supervisor (cola thread-safe)",
  "registrar_accion (CSV persistente)",
  "analizar_feedback (tasa FP + deriva)",
];
tools.forEach((t, i) => {
  s.addText("\u2022 " + t, { x: 5.4, y: 1.45 + i * 0.36, w: 4.1, h: 0.34, fontSize: 10, color: "333333", fontFace: FONT_BODY });
});

// Multimodal box
s.addShape(pptx.ShapeType.rect, { x: 5.3, y: 4.2, w: 4.3, h: 1.5, fill: { color: C.lightGray }, rectRadius: 0.08 });
s.addText("Multimodal (Lecture 8)", { x: 5.5, y: 4.25, w: 3.9, h: 0.35, fontSize: 12, color: C.navy, fontFace: FONT_BODY, bold: true });
s.addText("Gemini recibe en UNA llamada:\nTexto (prompt 3000 tokens)\nImagen PNG (panel de tendencia)\nGIF animado (30s de evolucion)\nAudio del operario (STT integrado)\nFoto del equipo (vision por computador)", {
  x: 5.5, y: 4.6, w: 3.9, h: 1.1, fontSize: 10, color: "333333", fontFace: FONT_BODY, lineSpacing: 14,
});

// Bottom: Why it's a real agent
s.addShape(pptx.ShapeType.rect, { x: 0.5, y: 4.7, w: 4.5, h: 1.0, fill: { color: "E8F4E8" }, rectRadius: 0.08 });
s.addText("Es un agente REAL (no logica hardcodeada)", { x: 0.7, y: 4.75, w: 4.1, h: 0.3, fontSize: 11, color: C.green, fontFace: FONT_BODY, bold: true });
s.addText("Gemini DECIDE que herramientas usar, en que orden, y cuando tiene suficiente info. No hay if/else que diga 'siempre consulta historial primero'.", {
  x: 0.7, y: 5.1, w: 4.1, h: 0.55, fontSize: 10, color: "333333", fontFace: FONT_BODY, lineSpacing: 13,
});
addFooter(s);

// ═══════════════════════════════════════════════════════
// SLIDE 6 — RESILIENCIA + SEGURIDAD
// ═══════════════════════════════════════════════════════
s = lightSlide(pptx);
s.addText("5", { x: 0.5, y: 0.3, w: 0.5, h: 0.5, fontSize: 24, color: C.white, fontFace: FONT_TITLE, fill: { color: C.navy }, align: "center", valign: "middle", rectRadius: 0.1 });
s.addText("Resiliencia, Seguridad y Decisiones", { x: 1.2, y: 0.3, w: 7, h: 0.5, fontSize: 26, color: C.navy, fontFace: FONT_TITLE, bold: true });

// Circuit Breaker
s.addShape(pptx.ShapeType.rect, { x: 0.5, y: 1.0, w: 4.3, h: 2.4, fill: { color: C.lightGray }, rectRadius: 0.1 });
s.addText("Circuit Breaker (Lectures 9)", { x: 0.7, y: 1.05, w: 3.9, h: 0.35, fontSize: 13, color: C.navy, fontFace: FONT_BODY, bold: true });
s.addText(
  "CERRADO: Gemini responde OK\n" +
  "    | 3 fallos consecutivos\n" +
  "ABIERTO: Gemma 2B local (CPU)\n" +
  "    | cada 5 min prueba Gemini\n" +
  "SEMI-ABIERTO: 1 prueba\n" +
  "    | exito -> CERRADO\n\n" +
  "Gemma = Knowledge Distillation de Gemini\n" +
  "1.5 GB RAM | ~800ms | Espanol nativo",
  { x: 0.7, y: 1.45, w: 3.9, h: 1.9, fontSize: 10.5, color: "333333", fontFace: FONT_BODY, lineSpacing: 14 }
);

// Security
s.addShape(pptx.ShapeType.rect, { x: 5.3, y: 1.0, w: 4.3, h: 2.4, fill: { color: C.lightGray }, rectRadius: 0.1 });
s.addText("Seguridad (Lecture 6)", { x: 5.5, y: 1.05, w: 3.9, h: 0.35, fontSize: 13, color: C.navy, fontFace: FONT_BODY, bold: true });
s.addText(
  "Anti prompt-injection:\n" +
  "  Mensajes fuera de tema -> rechaza\n" +
  "  y redirige al incidente activo\n\n" +
  "Limites hardcodeados:\n" +
  "  Presion: 2-45 PSI\n" +
  "  Temperatura: 40-120 C\n" +
  "  Corriente: 0-490 A\n\n" +
  "Sin acceso a shell ni filesystem",
  { x: 5.5, y: 1.45, w: 3.9, h: 1.9, fontSize: 10.5, color: "333333", fontFace: FONT_BODY, lineSpacing: 14 }
);

// Decisions table
s.addText("Decisiones de Ingenieria", { x: 0.5, y: 3.6, w: 9, h: 0.4, fontSize: 14, color: C.navy, fontFace: FONT_BODY, bold: true });
const decisions = [
  ["Por que Gemini?", "Unico LLM con texto+imagen+audio+GIF en UNA llamada. Prompt caching -90% costos. Gemma como fallback compatible."],
  ["Por que RAG y no Fine-tuning?", "Datos insuficientes + conocimiento cambiante + evita catastrophic forgetting."],
  ["Por que ISA-18.2?", "Estandar industrial para alarmas. Maquinas de estado + histeresis + anti-spam evitan alarm fatigue."],
  ["Por que no Vector DB?", "Volumen pequeno (~50 incidentes). Busqueda lineal en YAML <1ms. En produccion SI migrariamos."],
];
const tableRows = [
  [{ text: "Decision", options: { bold: true, color: C.white, fill: { color: C.navy }, fontSize: 10, fontFace: FONT_BODY } },
   { text: "Justificacion", options: { bold: true, color: C.white, fill: { color: C.navy }, fontSize: 10, fontFace: FONT_BODY } }],
];
decisions.forEach(d => {
  tableRows.push([
    { text: d[0], options: { fontSize: 9, fontFace: FONT_BODY, bold: true } },
    { text: d[1], options: { fontSize: 9, fontFace: FONT_BODY } },
  ]);
});
s.addTable(tableRows, { x: 0.5, y: 4.0, w: 9.0, colW: [2.5, 6.5], border: { pt: 0.5, color: "CCCCCC" }, margin: [3, 5, 3, 5] });
addFooter(s);

// ═══════════════════════════════════════════════════════
// SLIDE 7 — DEMO: Alerta + Audio + Foto
// ═══════════════════════════════════════════════════════
s = darkSlide(pptx);
s.addText("6", { x: 0.5, y: 0.3, w: 0.5, h: 0.5, fontSize: 24, color: C.navy, fontFace: FONT_TITLE, fill: { color: C.ice }, align: "center", valign: "middle", rectRadius: 0.1 });
s.addText("Demo: Conversacion Real con el Sistema", { x: 1.2, y: 0.3, w: 7, h: 0.5, fontSize: 26, color: C.white, fontFace: FONT_TITLE, bold: true });

// Images
if (img1) s.addImage({ data: "image/jpeg;base64," + img1, x: 0.3, y: 1.0, w: 3.0, h: 5.2, rounding: true });
if (img2) s.addImage({ data: "image/jpeg;base64," + img2, x: 3.5, y: 1.0, w: 3.0, h: 5.2, rounding: true });
if (img3) s.addImage({ data: "image/jpeg;base64," + img3, x: 6.7, y: 1.0, w: 3.0, h: 5.2, rounding: true });

s.addText("Alerta con panel multimodal + Audio del operario con respuesta inteligente + Foto del equipo analizada por Gemini", {
  x: 0.3, y: 6.4, w: 9.4, h: 0.4, fontSize: 10, color: C.ice, fontFace: FONT_BODY, italic: true, align: "center",
});

// ═══════════════════════════════════════════════════════
// SLIDE 8 — DEMO: Conversacion continua + Cierre
// ═══════════════════════════════════════════════════════
s = darkSlide(pptx);
s.addText("7", { x: 0.5, y: 0.3, w: 0.5, h: 0.5, fontSize: 24, color: C.navy, fontFace: FONT_TITLE, fill: { color: C.ice }, align: "center", valign: "middle", rectRadius: 0.1 });
s.addText("Demo: Memoria + Resolucion + Cierre de Incidente", { x: 1.2, y: 0.3, w: 8, h: 0.5, fontSize: 24, color: C.white, fontFace: FONT_TITLE, bold: true });

if (img4) s.addImage({ data: "image/jpeg;base64," + img4, x: 0.5, y: 1.0, w: 3.5, h: 5.4, rounding: true });
if (img5) s.addImage({ data: "image/jpeg;base64," + img5, x: 4.2, y: 1.2, w: 3.0, h: 5.0, rounding: true });

// Annotations
s.addShape(pptx.ShapeType.rect, { x: 7.4, y: 1.2, w: 2.3, h: 5.0, fill: { color: C.navy }, rectRadius: 0.1 });
s.addText(
  "Maria recuerda TODO\nlo dicho en el incidente\n\n" +
  "Operario confirma:\n\"Solucionado\"\n\n" +
  "Sistema cierra incidente\ny reanuda monitoreo\n\n" +
  "Conversacion se\npersiste en ChromaDB\npara RAG futuro",
  { x: 7.5, y: 1.4, w: 2.1, h: 4.6, fontSize: 11, color: C.white, fontFace: FONT_BODY, lineSpacing: 16 }
);

// ═══════════════════════════════════════════════════════
// SLIDE 9 — CONCEPTOS DEL CURSO + CODIGO
// ═══════════════════════════════════════════════════════
s = lightSlide(pptx);
s.addText("8", { x: 0.5, y: 0.3, w: 0.5, h: 0.5, fontSize: 24, color: C.white, fontFace: FONT_TITLE, fill: { color: C.navy }, align: "center", valign: "middle", rectRadius: 0.1 });
s.addText("Conceptos del Curso Implementados (18/20)", { x: 1.2, y: 0.3, w: 7, h: 0.5, fontSize: 24, color: C.navy, fontFace: FONT_TITLE, bold: true });

const concepts = [
  ["Generative AI (L2)", "Gemini genera prescripciones"],
  ["Transformer (L4)", "Gemini = decoder-only"],
  ["Prompt Engineering (L5)", "Bloque fijo/variable"],
  ["Context Engineering (L5)", "Role, tono, formato JSON"],
  ["Few-shot (L4)", "Ejemplos del feedback"],
  ["RAG (L5)", "YAML + CSV inyectado"],
  ["Feedback (L5)", "Implicito -> few-shot"],
  ["Agentic AI (L7)", "Loop ReAct + 7 tools"],
  ["Tool Use (L7)", "Function Calling"],
  ["Human-in-the-loop (L7)", "Botones Telegram"],
  ["Multimodal (L8)", "Texto+img+audio+GIF"],
  ["Minimal LLMs (L9)", "Gemma 2B fallback"],
  ["K. Distillation (L4)", "Gemma = destilacion"],
  ["Quantization (L5)", "Gemma cuantizado CPU"],
  ["Prompt Injection (L6)", "Guardia anti off-topic"],
  ["Explainability (L10)", "Feature Store explicito"],
  ["Image Generation (L2,L8)", "NanoBanana fichas IA"],
];

const conceptRows = [
  [{ text: "Concepto", options: { bold: true, color: C.white, fill: { color: C.navy }, fontSize: 9, fontFace: FONT_BODY } },
   { text: "Implementacion", options: { bold: true, color: C.white, fill: { color: C.navy }, fontSize: 9, fontFace: FONT_BODY } },
   { text: "Concepto", options: { bold: true, color: C.white, fill: { color: C.navy }, fontSize: 9, fontFace: FONT_BODY } },
   { text: "Implementacion", options: { bold: true, color: C.white, fill: { color: C.navy }, fontSize: 9, fontFace: FONT_BODY } }],
];
for (let i = 0; i < 9; i++) {
  const left = concepts[i] || ["", ""];
  const right = concepts[i + 9] || ["", ""];
  conceptRows.push([
    { text: left[0], options: { fontSize: 8.5, fontFace: FONT_BODY, bold: true } },
    { text: left[1], options: { fontSize: 8.5, fontFace: FONT_BODY } },
    { text: right[0], options: { fontSize: 8.5, fontFace: FONT_BODY, bold: true } },
    { text: right[1], options: { fontSize: 8.5, fontFace: FONT_BODY } },
  ]);
}
s.addTable(conceptRows, { x: 0.3, y: 0.95, w: 9.4, colW: [1.8, 2.9, 1.8, 2.9], border: { pt: 0.5, color: "CCCCCC" }, margin: [2, 4, 2, 4], rowH: [0.32, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28, 0.28] });

// Code snippet
s.addShape(pptx.ShapeType.rect, { x: 0.3, y: 4.0, w: 9.4, h: 2.4, fill: { color: "1E1E1E" }, rectRadius: 0.1 });
s.addText("Codigo clave: Loop agentico con Tool Use", { x: 0.5, y: 4.05, w: 9.0, h: 0.3, fontSize: 11, color: C.green, fontFace: "Consolas", bold: true });
s.addText(
  "for iteracion in range(max_iteraciones):  # max 5\n" +
  "    response = cliente.models.generate_content(\n" +
  "        contents=[imagen, gif, prompt],\n" +
  "        tools=[types.Tool(function_declarations=herramientas)],\n" +
  "    )\n" +
  "    if response tiene function_call:\n" +
  '        resultado = herramientas.ejecutar(nombre, args)  # Gemini DECIDE\n' +
  "    else:\n" +
  "        return prescripcion_final  # Gemini termino de razonar",
  { x: 0.5, y: 4.35, w: 9.0, h: 2.0, fontSize: 10, color: C.ice, fontFace: "Consolas", lineSpacing: 15 }
);
addFooter(s);

// ═══════════════════════════════════════════════════════
// SLIDE 10 — CIERRE
// ═══════════════════════════════════════════════════════
s = darkSlide(pptx);
s.addText("Gracias", { x: 0.8, y: 1.5, w: 8.4, h: 1.2, fontSize: 52, color: C.white, fontFace: FONT_TITLE, bold: true });
s.addText("Sistema de Monitoreo de Peletizacion con LLM Multimodal", {
  x: 0.8, y: 2.8, w: 8.4, h: 0.5, fontSize: 18, color: C.ice, fontFace: FONT_BODY, italic: true,
});

// Summary chips
const chips = [
  "RAG + Feedback", "Agentic AI", "Multimodal", "NanoBanana",
  "Feature Store", "ISA-18.2", "Circuit Breaker", "Email SMTP",
];
chips.forEach((chip, i) => {
  const row = Math.floor(i / 4);
  const col = i % 4;
  s.addShape(pptx.ShapeType.rect, {
    x: 0.8 + col * 2.2, y: 3.8 + row * 0.55, w: 2.0, h: 0.4,
    fill: { color: C.navy }, rectRadius: 0.08, line: { color: C.accent, width: 1 },
  });
  s.addText(chip, {
    x: 0.8 + col * 2.2, y: 3.8 + row * 0.55, w: 2.0, h: 0.4,
    fontSize: 11, color: C.white, fontFace: FONT_BODY, align: "center", valign: "middle",
  });
});

s.addText("Preguntas y demostracion en vivo", {
  x: 0.8, y: 5.3, w: 8.4, h: 0.4, fontSize: 16, color: C.ice, fontFace: FONT_BODY,
});
s.addText("Brian | Omar | Isabela", { x: 0.8, y: 6.0, w: 4, h: 0.3, fontSize: 14, color: C.gray, fontFace: FONT_BODY });
s.addText("Universidad Nacional de Colombia | Facultad de Minas | Sistemas Inteligentes", {
  x: 0.8, y: 7.0, w: 8.4, h: 0.3, fontSize: 9, color: C.gray, fontFace: FONT_BODY,
});

// ─── SAVE ───
const outPath = process.argv[2] || "Presentacion_Final.pptx";
pptx.writeFile({ fileName: outPath }).then(() => {
  console.log("Presentacion generada: " + outPath);
});
