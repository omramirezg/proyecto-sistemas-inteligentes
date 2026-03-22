"""Analizador de telemetria operativa para el proceso de peletizacion.

Modulo extraido de la clase WorkerPeletizacion (src/main.py) siguiendo el
principio de Responsabilidad Unica (Single Responsibility).  Agrupa los
metodos puros de analisis, clasificacion y diagnostico que no requieren
estado interno del worker.
"""

from typing import Any


class AnalizadorTelemetria:
    """Funciones puras de analisis de telemetria extraidas de WorkerPeletizacion."""

    @staticmethod
    def limpiar_texto_llm(texto: str) -> str:
        """Limpia marcas simples para reutilizar el texto del LLM en chat y audio."""
        texto_limpio = (texto or "").strip()
        reemplazos = ['**', '*', '[', ']', '#']
        for marca in reemplazos:
            texto_limpio = texto_limpio.replace(marca, '')
        return " ".join(texto_limpio.split())

    @staticmethod
    def estado_en_banda(valor: float, limite_min: float, limite_max: float) -> str:
        """Clasifica una variable respecto a su banda operativa."""
        if valor < limite_min:
            return 'BAJO'
        if valor > limite_max:
            return 'ALTO'
        return 'NORMAL'

    @staticmethod
    def construir_diagnostico_operativo(
        lectura: dict[str, Any],
        estado_temperatura: str,
        estado_presion: str,
        porcentaje_carga: float,
    ) -> str:
        """Genera un mensaje corto con criterio operativo para texto y audio."""
        temp = lectura['temp_ema']
        pres = lectura['presion_ema']
        maquina = lectura['id_maquina']

        if estado_temperatura == 'NORMAL' and estado_presion == 'NORMAL':
            return (
                f"Proceso estable en la maquina {maquina}. "
                f"La temperatura esta normal en {temp:.1f} grados y la presion esta normal en {pres:.1f} PSI. "
                "Mantenga la operacion y continue monitoreo."
            )

        if estado_presion == 'BAJO' and estado_temperatura == 'BAJO':
            if porcentaje_carga >= 90:
                return (
                    f"Alerta de presion y temperatura bajas en la maquina {maquina}. "
                    f"La carga esta alta en {porcentaje_carga:.1f} por ciento, asi que no aumente vapor de forma brusca. "
                    "Reduzca alimentacion, verifique linea de vapor y estabilice la maquina."
                )
            return (
                f"Alerta de presion y temperatura bajas en la maquina {maquina}. "
                "Esto sugiere deficiencia de vapor o dosificacion insuficiente. "
                "Revise valvula, confirme suministro de vapor y corrija antes de continuar."
            )

        if estado_presion == 'BAJO':
            if porcentaje_carga >= 90:
                return (
                    f"Alerta de presion baja en la maquina {maquina}. "
                    f"La carga actual esta elevada en {porcentaje_carga:.1f} por ciento. "
                    "Baje alimentacion, revise la linea de vapor y evite forzar el equipo."
                )
            return (
                f"Alerta de presion baja en la maquina {maquina}. "
                f"La presion actual esta en {pres:.1f} PSI, por debajo de la banda operativa. "
                "Revise suministro de vapor y ajuste la dosificacion de forma controlada."
            )

        if estado_presion == 'ALTO':
            return (
                f"Alerta de presion alta en la maquina {maquina}. "
                f"La presion actual esta en {pres:.1f} PSI y supera la banda permitida. "
                "Modere el ingreso de vapor y verifique que no haya sobrepresion en el acondicionador."
            )

        if estado_temperatura == 'BAJO':
            return (
                f"Alerta de temperatura baja en la maquina {maquina}. "
                f"La temperatura actual esta en {temp:.1f} grados y no alcanza la banda de formula. "
                "Revise vapor, tiempo de acondicionamiento y condiciones de alimentacion."
            )

        if estado_temperatura == 'ALTO':
            return (
                f"Alerta de temperatura alta en la maquina {maquina}. "
                f"La temperatura actual esta en {temp:.1f} grados y supera la banda permitida. "
                "Disminuya energia termica, revise vapor y evite sobrecoccion del producto."
            )

        return (
            f"Lectura operativa de la maquina {maquina}. "
            f"Temperatura en {temp:.1f} grados y presion en {pres:.1f} PSI. "
            "Mantenga monitoreo del proceso."
        )

    @staticmethod
    def clasificar_contexto_global(
        estado_temperatura: str,
        estado_presion: str,
        porcentaje_carga: float,
        pronostico_nivel: str,
    ) -> tuple[str, str]:
        """Define un estado global y severidad de la lectura."""
        if estado_temperatura == 'NORMAL' and estado_presion == 'NORMAL':
            if pronostico_nivel == 'ALTO' or porcentaje_carga >= 90:
                return 'BAJO VIGILANCIA', 'PREVENTIVA'
            if pronostico_nivel == 'MEDIO':
                return 'BAJO VIGILANCIA', 'PREVENTIVA'
            return 'ESTABLE', 'INFORMATIVA'

        if (
            estado_temperatura != 'NORMAL'
            and estado_presion != 'NORMAL'
            and (porcentaje_carga >= 85 or 'ALTO' in [estado_temperatura, estado_presion])
        ):
            return 'EN RIESGO', 'CRITICA'

        if estado_temperatura != 'NORMAL' and estado_presion != 'NORMAL':
            return 'EN RIESGO', 'ALTA'

        if porcentaje_carga >= 95:
            return 'EN RIESGO', 'ALTA'

        return 'BAJO VIGILANCIA', 'PREVENTIVA'

    @staticmethod
    def inferir_causa_probable(
        estado_temperatura: str,
        estado_presion: str,
        porcentaje_carga: float,
        tendencia_temp: str,
        tendencia_pres: str,
        pronostico_nivel: str,
    ) -> str:
        """Infiere una causa probable legible para operacion."""
        if estado_temperatura == 'NORMAL' and estado_presion == 'NORMAL':
            if 'deterioro progresivo' in tendencia_temp or 'deterioro progresivo' in tendencia_pres:
                return 'recuperacion parcial tras intervencion operativa reciente'
            if porcentaje_carga >= 90:
                return 'carga operativa elevada con variables aun dentro de banda'
            if pronostico_nivel == 'MEDIO':
                return 'estabilidad aparente con tendencia de degradacion temprana'
            return 'operacion dentro de parametros de formula'

        if estado_temperatura == 'BAJO' and estado_presion == 'BAJO':
            if porcentaje_carga >= 90:
                return 'caida de suministro de vapor combinada con sobrecarga del equipo'
            return 'caida de suministro de vapor o dosificacion insuficiente de energia termica'

        if estado_presion == 'BAJO':
            if porcentaje_carga >= 90:
                return 'sobrecarga del equipo con presion insuficiente para sostener el acondicionamiento'
            if 'cayendo' in tendencia_pres or 'deterioro progresivo' in tendencia_pres:
                return 'caida de suministro de vapor o valvula con apertura insuficiente'
            return 'dosificacion insuficiente de vapor en el acondicionador'

        if estado_presion == 'ALTO':
            if estado_temperatura == 'ALTO':
                return 'exceso de ingreso de vapor con riesgo de sobrecalentamiento del producto'
            return 'sobrepresion por exceso de vapor o control agresivo de la valvula'

        if estado_temperatura == 'BAJO':
            if 'cayendo' in tendencia_temp:
                return 'perdida progresiva de energia termica o tiempo de acondicionamiento corto'
            return 'energia termica insuficiente para la formula actual'

        if estado_temperatura == 'ALTO':
            if porcentaje_carga >= 85:
                return 'sobrecalentamiento del proceso bajo alta carga operativa'
            return 'exceso de energia termica o retencion excesiva en el acondicionador'

        return 'condicion operativa en observacion'

    @staticmethod
    def calcular_indice_salud(
        estado_temperatura: str,
        estado_presion: str,
        porcentaje_carga: float,
        tendencia_temp: str,
        tendencia_pres: str,
        pronostico: str,
    ) -> tuple[int, str]:
        """Calcula un indice explicable de salud operacional del proceso."""
        score = 100

        penalizaciones = {
            'NORMAL': 0,
            'BAJO': 18,
            'ALTO': 16,
        }
        score -= penalizaciones.get(estado_temperatura, 0)
        score -= penalizaciones.get(estado_presion, 0)

        if porcentaje_carga >= 90:
            score -= 15
        elif porcentaje_carga >= 75:
            score -= 8

        if 'deterioro progresivo' in tendencia_temp or 'cayendo' in tendencia_temp:
            score -= 8
        if 'deterioro progresivo' in tendencia_pres or 'cayendo' in tendencia_pres:
            score -= 8
        if 'riesgo activo' in pronostico:
            score -= 15
        elif 'riesgo de salir de banda' in pronostico:
            score -= 10

        score = max(0, min(100, int(round(score))))
        if score >= 85:
            return score, 'ESTABLE'
        if score >= 65:
            return score, 'VIGILANCIA'
        if score >= 40:
            return score, 'RIESGO'
        return score, 'CRITICO'

    @staticmethod
    def resumir_alertas_confirmadas(alertas: list[Any]) -> str:
        """Resume alertas confirmadas en una linea legible para el operario."""
        activas = [a for a in alertas if not a.es_retorno_normal]
        if not activas:
            return ''
        etiquetas = [a.tipo_alerta.value.replace('_', ' ') for a in activas]
        return ', '.join(etiquetas)

    @staticmethod
    def analizar_tendencia(
        historial_reciente: list[dict[str, Any]],
        columna: str,
        limite_min: float,
        limite_max: float,
    ) -> dict[str, str]:
        """Analiza la tendencia reciente con una heuristica simple y explicable."""
        if len(historial_reciente) < 3:
            return {
                'mensaje': 'sin suficientes lecturas para tendencia',
                'audio': 'sin suficientes lecturas para establecer tendencia',
            }

        ventana = historial_reciente[-5:]
        valores = [float(item[columna]) for item in ventana]
        delta = valores[-1] - valores[0]
        rango = max(limite_max - limite_min, 1.0)
        pendiente_relativa = delta / rango

        if valores[-1] < limite_min:
            return {
                'mensaje': 'muestra deterioro progresivo por debajo de banda',
                'audio': 'muestra deterioro progresivo por debajo de banda',
            }
        if valores[-1] > limite_max:
            return {
                'mensaje': 'se mantiene por encima de banda operativa',
                'audio': 'se mantiene por encima de banda operativa',
            }
        if pendiente_relativa <= -0.18:
            return {
                'mensaje': 'viene cayendo en las ultimas lecturas',
                'audio': 'viene cayendo en las ultimas lecturas',
            }
        if pendiente_relativa >= 0.18:
            return {
                'mensaje': 'viene aumentando de forma sostenida',
                'audio': 'viene aumentando de forma sostenida',
            }
        return {
            'mensaje': 'permanece estable en la ventana reciente',
            'audio': 'permanece estable en la ventana reciente',
        }

    @staticmethod
    def construir_pronostico(
        tendencia_temp: dict[str, str],
        tendencia_pres: dict[str, str],
        estado_temperatura: str,
        estado_presion: str,
    ) -> dict[str, str]:
        """Construye un pronostico corto para los proximos minutos."""
        if estado_temperatura != 'NORMAL' or estado_presion != 'NORMAL':
            return {
                'nivel': 'ALTO',
                'mensaje': 'riesgo alto de continuar fuera de banda en los proximos 5 minutos',
                'audio': 'riesgo alto de continuar fuera de banda en los proximos cinco minutos',
            }

        if 'cayendo' in tendencia_pres['mensaje']:
            return {
                'nivel': 'MEDIO',
                'mensaje': 'riesgo medio de salir de banda por presion baja en los proximos 5 minutos',
                'audio': 'riesgo medio de salir de banda por presion baja en los proximos cinco minutos',
            }

        if 'deterioro progresivo' in tendencia_temp['mensaje'] or 'cayendo' in tendencia_temp['mensaje']:
            return {
                'nivel': 'MEDIO',
                'mensaje': 'riesgo medio de salir de banda por temperatura baja en los proximos 5 minutos',
                'audio': 'riesgo medio de salir de banda por temperatura baja en los proximos cinco minutos',
            }

        if 'aumentando' in tendencia_temp['mensaje']:
            return {
                'nivel': 'MEDIO',
                'mensaje': 'riesgo medio de acercamiento al limite superior de temperatura en 5 minutos',
                'audio': 'riesgo medio de acercamiento al limite superior de temperatura en cinco minutos',
            }

        if 'aumentando' in tendencia_pres['mensaje']:
            return {
                'nivel': 'MEDIO',
                'mensaje': 'riesgo medio de acercamiento al limite superior de presion en 5 minutos',
                'audio': 'riesgo medio de acercamiento al limite superior de presion en cinco minutos',
            }

        return {
            'nivel': 'BAJO',
            'mensaje': 'riesgo bajo de salir de banda en los proximos 5 minutos',
            'audio': 'riesgo bajo de salir de banda en los proximos cinco minutos',
        }

    @staticmethod
    def resumen_tendencia_corta(
        tendencia_temp: str,
        tendencia_pres: str,
        pronostico_nivel: str,
    ) -> str:
        """Comprime tendencias largas en una frase breve para el operario."""
        banderas = []
        if 'cayendo' in tendencia_temp or 'deterioro' in tendencia_temp:
            banderas.append('temperatura a la baja')
        elif 'aument' in tendencia_temp:
            banderas.append('temperatura al alza')

        if 'cayendo' in tendencia_pres or 'deterioro' in tendencia_pres:
            banderas.append('presion a la baja')
        elif 'aument' in tendencia_pres:
            banderas.append('presion al alza')

        if not banderas:
            base = 'variables estables en la ventana reciente'
        else:
            base = ', '.join(banderas)

        riesgo = {
            'BAJO': 'sin urgencia inmediata',
            'MEDIO': 'vigilar proximos minutos',
            'ALTO': 'riesgo operativo alto',
        }.get(pronostico_nivel, 'vigilar comportamiento')
        return f"{base}; {riesgo}."

    @staticmethod
    def compactar_causa_probable(causa_probable: str) -> str:
        """Acorta la causa probable para no saturar el chat del operario."""
        texto = (causa_probable or '').strip()
        if not texto:
            return 'sin causa dominante identificada'
        if len(texto) <= 70:
            return texto

        recortes = [
            ' combinada con ',
            ' con ',
            ' o ',
            ' tras ',
        ]
        for separador in recortes:
            if separador in texto:
                return texto.split(separador)[0].strip()
        return texto[:67].rstrip(' ,.;:') + '...'
