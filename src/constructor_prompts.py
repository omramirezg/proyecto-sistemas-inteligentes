"""Construccion centralizada de prompts para el sistema de peletizacion.

Refactoring extraido de WorkerPeletizacion (main.py). Cada metodo
devuelve el texto listo para enviar al LLM o al generador de fichas.
"""

from typing import Any, Optional


class ConstructorPrompts:
    """Fabrica de prompts operativos, fichas IA y contexto de audio."""

    @staticmethod
    def accion_sugerida_ficha(lectura: dict[str, Any]) -> str:
        """Construye una accion sugerida breve para la ficha visual IA."""
        estado_temp = lectura['estado_temperatura']
        estado_pres = lectura['estado_presion']
        carga = float(lectura['porcentaje_carga'])

        if estado_temp == 'NORMAL' and estado_pres == 'NORMAL':
            if lectura['pronostico_nivel'] == 'BAJO':
                return 'Mantener operacion y monitoreo normal del proceso.'
            return 'Continuar monitoreo reforzado y verificar tendencia de variables.'

        if estado_temp == 'BAJO' and estado_pres == 'BAJO':
            if carga >= 85:
                return 'Reducir alimentacion, revisar linea de vapor y estabilizar carga.'
            return 'Revisar suministro de vapor y corregir dosificacion termica.'

        if estado_pres == 'BAJO':
            return 'Verificar valvula y suministro de vapor antes de continuar.'

        if estado_pres == 'ALTO':
            return 'Reducir ingreso de vapor y validar control de presion del acondicionador.'

        if estado_temp == 'BAJO':
            return 'Aumentar energia termica de forma controlada y revisar acondicionamiento.'

        if estado_temp == 'ALTO':
            return 'Disminuir energia termica y evitar sobrecoccion del producto.'

        return 'Mantener seguimiento operativo y confirmar estabilidad.'

    @staticmethod
    def prompt_ficha_ia(
        lectura: dict[str, Any],
        audiencia: str,
    ) -> str:
        """Construye el prompt multimodal para Nano Banana."""
        accion_sugerida = ConstructorPrompts.accion_sugerida_ficha(lectura)
        es_operario = audiencia == 'operario'
        modo_ficha = (
            "tarjeta de continuidad operacional para operario"
            if es_operario and lectura['severidad'] == 'INFORMATIVA'
            else "ficha de intervencion operativa para operario"
            if es_operario
            else "lamina ejecutiva gerencial de continuidad operacional"
            if lectura['severidad'] == 'INFORMATIVA'
            else "lamina ejecutiva gerencial de riesgo operativo"
        )
        instruccion_audiencia = (
            "Prioriza accion inmediata, lectura rapida, alto contraste y mensajes cortos para personal en planta."
            if es_operario
            else "Prioriza impacto ejecutivo, claridad de riesgo, continuidad operacional y lectura corporativa premium."
        )
        return f"""
Genera una {modo_ficha} industrial en espanol.
Usa la imagen tecnica suministrada SOLO como referencia de contexto.
NO copies la grafica original.
NO dibujes ejes, series temporales, lineas, puntos, dashboards tecnicos ni tablas parecidas a la imagen base.
Transforma el contenido en una pieza visual nueva, tipo poster ejecutivo-operacional premium para Telegram.

Datos obligatorios:
- Planta: {lectura['id_planta']}
- Maquina: {lectura['id_maquina']}
- Formula: {lectura['id_formula']} ({lectura['codigo_producto']})
- Lectura: {lectura['numero']}
- Estado global: {lectura['estado_global']}
- Severidad: {lectura['severidad']}
- Indice de salud: {lectura['indice_salud']}/100 ({lectura['etiqueta_salud']})
- Temperatura EMA: {lectura['temp_ema']:.1f} C ({lectura['estado_temperatura']})
- Presion EMA: {lectura['presion_ema']:.1f} PSI ({lectura['estado_presion']})
- Carga: {lectura['porcentaje_carga']:.1f}%
- Tendencia temperatura: {lectura['tendencia_temp']}
- Tendencia presion: {lectura['tendencia_pres']}
- Pronostico a 5 min: {lectura['pronostico']} ({lectura['pronostico_nivel']})
- Causa probable: {lectura['causa_probable']}
- Accion sugerida: {accion_sugerida}

Instrucciones:
- Disena una lamina visual limpia, profesional y muy clara para Telegram.
- Usa SIEMPRE formato vertical tipo poster, proporcion retrato cercana a 4:5 o A4 vertical.
- Mantén SIEMPRE la misma estructura visual base y el mismo estilo grafico entre incidentes.
- Usa una reticula fija de arriba hacia abajo, centrada, con margenes amplios y composicion estable.
- Usa estilo industrial corporativo, con jerarquia fuerte y composicion centrada.
- {instruccion_audiencia}
- La salida debe parecer una ficha de incidente o una tarjeta ejecutiva, no una grafica.
- Incluye como maximo 5 bloques:
  1. encabezado con planta, maquina y formula
  2. sello grande de estado global y severidad
  3. bloque de salud del proceso
  4. bloque de causa probable
  5. bloque de accion sugerida
- Mantén esos 5 bloques siempre en el mismo orden y con la misma proporcion visual.
- NO generes versiones horizontales, apaisadas ni composiciones tipo banner.
- NO cambies el layout general entre eventos; solo cambia contenido y color de estado.
- Si el estado es estable, presenta la pieza como continuidad operacional y monitoreo.
- Si el estado es preventivo, alto o critico, presenta la pieza como alerta priorizada.
- Puedes usar iconos industriales simples, bandas de color, flechas, indicadores y sellos visuales.
- Evita saturar texto. Frases cortas y contundentes.
- Usa colores segun severidad:
  - informativa: azul profundo + verde controlado
  - preventiva: naranja industrial + azul oscuro
  - alta: rojo tecnico + gris antracita
  - critica: rojo oscuro + negro grafito
- Conserva siempre fondo, tipografia, espaciado, iconografia y estilo general; solo varia la paleta de estado.
- No inventes valores diferentes a los entregados.
- Devuelve tambien una nota textual muy corta, maximo dos frases, explicando la ficha generada.
"""

    @staticmethod
    def prompt_ficha_cierre(
        lectura: dict[str, Any],
        resultado_audio: dict[str, Any],
    ) -> str:
        """Construye un prompt de cierre ejecutivo tras la atencion del operario."""
        return f"""
Genera una ficha ejecutiva de cierre de incidente industrial en espanol.
Usa la imagen tecnica solo como referencia del contexto del proceso.
NO copies la grafica original.
NO dibujes ejes, lineas, series temporales ni dashboards tecnicos.
Transforma el contenido en una lamina premium de cierre para gerencia y supervisor.

Objetivo:
- resumir que paso
- mostrar que el operario atendio el incidente
- dejar claro que el monitoreo normal fue reanudado

Datos del cierre:
- Planta: {lectura['id_planta']}
- Maquina: {lectura['id_maquina']}
- Formula: {lectura['id_formula']} ({lectura['codigo_producto']})
- Lectura de referencia: {lectura['numero']}
- Estado global actual: {lectura['estado_global']}
- Severidad: {lectura['severidad']}
- Salud del proceso: {lectura['indice_salud']}/100 ({lectura['etiqueta_salud']})
- Temperatura EMA: {lectura['temp_ema']:.1f} C ({lectura['estado_temperatura']})
- Presion EMA: {lectura['presion_ema']:.1f} PSI ({lectura['estado_presion']})
- Carga: {lectura['porcentaje_carga']:.1f}%
- Causa probable: {lectura['causa_probable']}
- Pronostico: {lectura['pronostico']} ({lectura['pronostico_nivel']})
- Reporte del operario: {resultado_audio.get('resumen_operario', '')}
- Intencion detectada: {resultado_audio.get('intencion', 'OTRO')}
- Accion reportada: {resultado_audio.get('accion_detectada', '')}
- Respuesta de Maria: {resultado_audio.get('respuesta_asistente', '')}
- Estado final: incidente atendido y monitoreo reanudado

Instrucciones visuales:
- Diseno corporativo industrial, limpio y sobrio.
- Usa SIEMPRE formato vertical tipo poster, proporcion retrato cercana a 4:5 o A4 vertical.
- Mantén SIEMPRE el mismo layout de cierre, con composicion centrada y ordenada.
- Prioriza claridad ejecutiva, trazabilidad y cierre del evento.
- Usa 5 bloques maximo:
  1. encabezado de cierre de incidente
  2. sello de estado final: RESUELTO o ESTABILIZADO
  3. resumen del incidente y severidad inicial
  4. accion tomada por el operario
  5. cierre con estado final y reanudacion del monitoreo
- Mantén esos 5 bloques siempre en el mismo orden y con el mismo estilo visual.
- NO generes versiones horizontales, apaisadas ni banners.
- Fondo claro o muy limpio, tarjetas verticales y misma familia visual en todas las fichas.
- Paleta base elegante: azul profundo, verde controlado y acentos naranja suaves.
- Si la severidad del incidente fue mayor, usa acentos mas intensos pero sin cambiar el estilo general.
- Evita saturacion de texto. Frases cortas.
- No inventes datos ni acciones.
- Devuelve una nota textual corta de maximo 2 frases.
"""

    @staticmethod
    def prompt_llm_operativo(
        lectura: dict[str, Any],
        estado_global: str,
        severidad: str,
        estado_temperatura: str,
        estado_presion: str,
        porcentaje_carga: float,
        tendencia_temp: str,
        tendencia_pres: str,
        pronostico: str,
        pronostico_nivel: str,
        causa_probable: str,
        diagnostico_operativo: str,
    ) -> str:
        """Arma el contexto que recibe Maria para prescripcion multimodal."""
        return f"""
Modo de trabajo: prescripcion operativa multimodal en tiempo real.

Planta: {lectura['id_planta']}
Maquina: {lectura['id_maquina']}
Formula: {lectura['id_formula']} ({lectura['codigo_producto']})
Lectura: {lectura['numero']}
Temperatura EMA: {lectura['temp_ema']:.2f} C
Presion EMA: {lectura['presion_ema']:.2f} PSI
Corriente EMA: {lectura['corriente_ema']:.2f} A
Carga: {porcentaje_carga:.1f}%
Banda temperatura: {lectura['t_min']:.1f} a {lectura['t_max']:.1f} C
Banda presion: {lectura['p_min']:.1f} a {lectura['p_max']:.1f} PSI
Estado temperatura: {estado_temperatura}
Estado presion: {estado_presion}
Estado global: {estado_global}
Severidad: {severidad}
Tendencia temperatura: {tendencia_temp}
Tendencia presion: {tendencia_pres}
Pronostico a 5 minutos: {pronostico}
Nivel de pronostico: {pronostico_nivel}
Causa probable: {causa_probable}
Diagnostico determinista de respaldo: {diagnostico_operativo}

Tu tarea:
- Analiza el contexto numerico y la imagen del panel tecnico.
- Si el proceso esta estable, emite una prescripcion breve de continuidad operacional.
- Si hay riesgo o desviacion, emite una prescripcion concreta para el operario.
- Mantente fiel a la imagen y a los datos. No inventes variables ni acciones fuera del contexto.
"""

    @staticmethod
    def prompt_explicacion_evento(lectura: dict[str, Any]) -> str:
        """Construye el prompt multimodal para explicar el evento al usuario."""
        return f"""
Modo capacitacion multimodal.

Explica en espanol, de forma clara y corta, que esta pasando en esta lectura de proceso.
Usa la imagen tecnica como apoyo para mencionar tendencia visual y relacionarla con los datos.

Datos del evento:
- Planta: {lectura['id_planta']}
- Maquina: {lectura['id_maquina']}
- Formula: {lectura['id_formula']} ({lectura['codigo_producto']})
- Lectura: {lectura['numero']}
- Estado global: {lectura['estado_global']}
- Severidad: {lectura['severidad']}
- Salud del proceso: {lectura['indice_salud']}/100 ({lectura['etiqueta_salud']})
- Temperatura EMA: {lectura['temp_ema']:.1f} C ({lectura['estado_temperatura']})
- Presion EMA: {lectura['presion_ema']:.1f} PSI ({lectura['estado_presion']})
- Carga: {lectura['porcentaje_carga']:.1f}%
- Tendencia temperatura: {lectura['tendencia_temp']}
- Tendencia presion: {lectura['tendencia_pres']}
- Pronostico a 5 min: {lectura['pronostico']} ({lectura['pronostico_nivel']})
- Causa probable: {lectura['causa_probable']}

Responde con maximo 3 oraciones:
1. que variable o condicion destaca
2. que patron visual/tendencia se observa
3. por que importa operativamente
"""

    @staticmethod
    def contexto_audio_operario(lectura: Optional[dict[str, Any]] = None) -> str:
        """Arma el contexto operativo que acompana el audio del operario."""
        if not lectura:
            return (
                "No hay una lectura de proceso reciente asociada. "
                "Interpreta el audio como observacion operativa general del operario."
            )

        return (
            f"Contexto actual:\n"
            f"Planta {lectura.get('id_planta', '001')} | Maquina {lectura.get('id_maquina', '')} | "
            f"Formula {lectura.get('id_formula', '')}\n"
            f"Estado {lectura.get('estado_global', '')} | Severidad {lectura.get('severidad', '')}\n"
            f"Temp {lectura.get('temp_ema', 0):.1f} C ({lectura.get('estado_temperatura', '')}) | "
            f"Pres {lectura.get('presion_ema', 0):.1f} PSI ({lectura.get('estado_presion', '')})\n"
            f"Causa probable: {lectura.get('causa_probable', '')}\n"
            "El audio puede confirmar solucion, reportar que la falla continua o pedir recomendacion puntual."
        )
