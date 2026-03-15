"""
Pipeline minimo de Telegram para validar texto, imagen y audio.
"""

import sys
import signal
import asyncio
import logging
import time
import html
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import ConfigLoader
from data_loader import DataLoader
from motor_reglas import MotorReglas
from generador_graficas import GeneradorGraficas
from tts_service import GoogleTTSProvider
from telegram_bot import TelegramNotificador
from generador_pdf import GeneradorPDF
from historial_alertas import HistorialAlertas
from dashboard_ejecutivo import DashboardEjecutivo
from imagen_generativa import NanoBananaProvider
from llm_multimodal import GeminiProvider

logger = logging.getLogger(__name__)


class WorkerPeletizacion:
    """Worker minimo para depurar el envio por Telegram."""

    def __init__(self) -> None:
        self.config = ConfigLoader()
        self.config.configurar_logging()

        self.data_loader = DataLoader(self.config)
        self.motor = MotorReglas(self.config)
        self.graficas = GeneradorGraficas()
        self.tts = GoogleTTSProvider(self.config)
        self.telegram = TelegramNotificador(self.config)
        self.pdf_gen = GeneradorPDF(self.config)
        self.historial = HistorialAlertas(self.config)
        self.dashboard = DashboardEjecutivo(self.config)
        self.nano_banana = NanoBananaProvider(self.config)
        self.llm = GeminiProvider(self.config)

        self._ejecutando = True
        self._planta_objetivo = '001'
        self._indice_actual = 0
        self._lecturas_procesadas = 0
        self._telemetria: Optional[pd.DataFrame] = None
        self._historial_reciente: dict[str, list[dict[str, Any]]] = {}
        self._ventana_historial = 8
        self._ultima_lectura_publicada: Optional[dict[str, Any]] = None
        self._ultimo_panel_bytes: Optional[bytes] = None

        signal.signal(signal.SIGINT, self._manejar_shutdown)
        signal.signal(signal.SIGTERM, self._manejar_shutdown)

    def _manejar_shutdown(self, signum, frame) -> None:
        logger.info(
            "Senal de cierre recibida (%s). Cerrando gracefully...",
            signal.Signals(signum).name,
        )
        self._ejecutando = False

    def inicializar(self) -> None:
        logger.info("Cargando datos iniciales para planta 001...")
        self.data_loader.cargar_todos_los_maestros()
        self._telemetria = self.data_loader.cargar_telemetria(self._planta_objetivo)
        logger.info("Telemetria cargada: %d registros.", len(self._telemetria))

    def ejecutar(self) -> None:
        logger.info(
            "Worker minimo iniciado. Intervalo: %d segundos.",
            self.config.intervalo_simulacion,
        )

        while self._ejecutando:
            try:
                lectura = self._obtener_siguiente_lectura()
                if lectura is not None:
                    asyncio.run(self._enviar_paquete_minimo(lectura))
                asyncio.run(self._procesar_eventos_chat())
            except Exception as e:
                logger.error("Error en worker minimo: %s", e, exc_info=True)

            time.sleep(self.config.intervalo_simulacion)

        logger.info("Worker minimo detenido tras %d lecturas.", self._lecturas_procesadas)

    def _obtener_siguiente_lectura(self) -> Optional[dict[str, Any]]:
        if self._telemetria is None or self._telemetria.empty:
            logger.warning("No hay telemetria disponible.")
            return None

        if self._indice_actual >= len(self._telemetria):
            logger.info("Fin de telemetria. Reiniciando desde el inicio.")
            self._indice_actual = 0

        fila = self._telemetria.iloc[self._indice_actual]
        self._indice_actual += 1

        id_maquina = str(fila['id_maquina']).strip().zfill(3)
        id_formula = str(fila['id_formula']).strip()
        limites = self.data_loader.obtener_limites_formula(self._planta_objetivo, id_formula)
        specs = self.data_loader.obtener_specs_equipo(self._planta_objetivo, id_maquina)
        if limites is None or specs is None:
            logger.warning("Lectura omitida por datos maestros faltantes.")
            return None

        timestamp = fila['fecha_registro']
        if not isinstance(timestamp, datetime):
            timestamp = pd.Timestamp(timestamp).to_pydatetime()

        alertas_motor = self.motor.evaluar_lectura(
            id_planta=self._planta_objetivo,
            id_maquina=id_maquina,
            id_formula=id_formula,
            codigo_producto=str(limites.get('codigo_producto', '')),
            corriente=float(fila['corriente']),
            temp_acond=float(fila['temp_acond']),
            presion_vapor=float(fila['presion_vapor']),
            timestamp=timestamp,
            corriente_carga_minima=float(specs['corriente_carga_minima']),
            capacidad_nominal=float(specs['capacidad_nominal']),
            t_min=float(limites['t_min']),
            t_max=float(limites['t_max']),
            p_min=float(limites['p_min']),
            p_max=float(limites['p_max']),
        )

        clave = f"{self._planta_objetivo}_{id_maquina}"
        estado = self.motor._estados.get(clave)
        if clave not in self._historial_reciente:
            self._historial_reciente[clave] = []
        self._historial_reciente[clave].append({
            'timestamp': timestamp,
            'temp_acond': float(fila['temp_acond']),
            'presion_vapor': float(fila['presion_vapor']),
            'corriente': float(fila['corriente']),
            'temp_ema': estado.ema_temperatura if estado and estado.ema_temperatura is not None else float(fila['temp_acond']),
            'presion_ema': estado.ema_presion if estado and estado.ema_presion is not None else float(fila['presion_vapor']),
            'corriente_ema': estado.ema_corriente if estado and estado.ema_corriente is not None else float(fila['corriente']),
        })
        if len(self._historial_reciente[clave]) > self._ventana_historial:
            self._historial_reciente[clave] = self._historial_reciente[clave][-self._ventana_historial:]
        self._lecturas_procesadas += 1

        return {
            'numero': self._lecturas_procesadas,
            'timestamp': timestamp,
            'id_planta': self._planta_objetivo,
            'id_maquina': id_maquina,
            'id_formula': id_formula,
            'codigo_producto': str(limites.get('codigo_producto', '')),
            'temp_ema': estado.ema_temperatura if estado and estado.ema_temperatura is not None else float(fila['temp_acond']),
            'presion_ema': estado.ema_presion if estado and estado.ema_presion is not None else float(fila['presion_vapor']),
            'corriente_ema': estado.ema_corriente if estado and estado.ema_corriente is not None else float(fila['corriente']),
            't_min': float(limites['t_min']),
            't_max': float(limites['t_max']),
            'p_min': float(limites['p_min']),
            'p_max': float(limites['p_max']),
            'capacidad_nominal': float(specs['capacidad_nominal']),
            'historial_reciente': list(self._historial_reciente[clave]),
            'alertas_confirmadas': alertas_motor,
        }

    async def _enviar_paquete_minimo(self, lectura: dict[str, Any]) -> None:
        chats = self._obtener_chats_destino(lectura['id_maquina'])
        if not chats:
            logger.warning("No hay chats destino configurados.")
            return

        porcentaje_carga = (
            lectura['corriente_ema'] / lectura['capacidad_nominal'] * 100
            if lectura['capacidad_nominal'] > 0 else 0.0
        )
        estado_temperatura = self._estado_en_banda(
            lectura['temp_ema'], lectura['t_min'], lectura['t_max']
        )
        estado_presion = self._estado_en_banda(
            lectura['presion_ema'], lectura['p_min'], lectura['p_max']
        )
        diagnostico_operativo = self._construir_diagnostico_operativo(
            lectura=lectura,
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
        )
        tendencia_temp = self._analizar_tendencia(
            lectura['historial_reciente'],
            'temp_ema',
            lectura['t_min'],
            lectura['t_max'],
        )
        tendencia_pres = self._analizar_tendencia(
            lectura['historial_reciente'],
            'presion_ema',
            lectura['p_min'],
            lectura['p_max'],
        )
        pronostico = self._construir_pronostico(
            tendencia_temp=tendencia_temp,
            tendencia_pres=tendencia_pres,
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
        )
        estado_global, severidad = self._clasificar_contexto_global(
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
            pronostico_nivel=pronostico['nivel'],
        )
        causa_probable = self._inferir_causa_probable(
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
            tendencia_temp=tendencia_temp['mensaje'],
            tendencia_pres=tendencia_pres['mensaje'],
            pronostico_nivel=pronostico['nivel'],
        )
        indice_salud, etiqueta_salud = self._calcular_indice_salud(
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
            tendencia_temp=tendencia_temp['mensaje'],
            tendencia_pres=tendencia_pres['mensaje'],
            pronostico=pronostico['mensaje'],
        )
        alerta_id_feedback = self._registrar_alertas_confirmadas(
            lectura=lectura,
            diagnostico_operativo=diagnostico_operativo,
            severidad=severidad,
            causa_probable=causa_probable,
            pronostico=pronostico['mensaje'],
        )
        resumen_alerta = self._resumir_alertas_confirmadas(lectura['alertas_confirmadas'])

        texto = (
            f"<b>Paquete Multimodal | Lectura {lectura['numero']}</b>\n"
            f"Planta {lectura['id_planta']} | Maquina {lectura['id_maquina']} | "
            f"Formula {lectura['id_formula']} ({lectura['codigo_producto']})\n"
            f"Estado global: <b>{estado_global}</b> | Severidad: <b>{severidad}</b>\n"
            f"Indice de salud: <b>{indice_salud}/100</b> | Nivel: <b>{etiqueta_salud}</b>\n"
            f"Temperatura EMA: <b>{lectura['temp_ema']:.2f} C</b> | Estado: <b>{estado_temperatura}</b>\n"
            f"Presion EMA: <b>{lectura['presion_ema']:.2f} PSI</b> | Estado: <b>{estado_presion}</b>\n"
            f"Corriente EMA: <b>{lectura['corriente_ema']:.2f} A</b> | Carga: <b>{porcentaje_carga:.1f}%</b>\n"
            f"<b>Tendencia:</b> Temp {tendencia_temp['mensaje']} | Presion {tendencia_pres['mensaje']}\n"
            f"<b>Pronostico a 5 min:</b> {pronostico['mensaje']} | Nivel: <b>{pronostico['nivel']}</b>\n"
            f"<b>Causa probable:</b> {causa_probable}\n"
            f"Ventana visual: ultimas {len(lectura['historial_reciente'])} mediciones\n"
            f"<b>Criterio operativo:</b> {diagnostico_operativo}"
        )
        if resumen_alerta:
            texto += f"\n<b>Alarma confirmada:</b> {resumen_alerta}"

        imagen_bytes = self.graficas.generar_panel_multimodal_telegram(
            datos_recientes=pd.DataFrame(lectura['historial_reciente']),
            id_planta=lectura['id_planta'],
            id_maquina=lectura['id_maquina'],
            id_formula=lectura['id_formula'],
            codigo_producto=lectura['codigo_producto'],
            numero_lectura=lectura['numero'],
            temp_actual=lectura['temp_ema'],
            presion_actual=lectura['presion_ema'],
            corriente_actual=lectura['corriente_ema'],
            t_min=lectura['t_min'],
            t_max=lectura['t_max'],
            p_min=lectura['p_min'],
            p_max=lectura['p_max'],
            porcentaje_carga=porcentaje_carga,
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            estado_global=estado_global,
            severidad=severidad,
            causa_probable=causa_probable,
            tendencia_temp=tendencia_temp['mensaje'],
            tendencia_pres=tendencia_pres['mensaje'],
            pronostico=pronostico['mensaje'],
            indice_salud=indice_salud,
            etiqueta_salud=etiqueta_salud,
        )

        prescripcion_maria = self._generar_prescripcion_maria(
            lectura=lectura,
            estado_global=estado_global,
            severidad=severidad,
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
            tendencia_temp=tendencia_temp['mensaje'],
            tendencia_pres=tendencia_pres['mensaje'],
            pronostico=pronostico['mensaje'],
            pronostico_nivel=pronostico['nivel'],
            causa_probable=causa_probable,
            diagnostico_operativo=diagnostico_operativo,
            imagen_bytes=imagen_bytes,
        )
        texto += f"\n<b>Maria:</b> {html.escape(prescripcion_maria)}"

        audio_texto = prescripcion_maria
        audio_bytes = self.tts.sintetizar(audio_texto)

        self.dashboard.actualizar_dashboard(
            lectura=lectura,
            estado_global=estado_global,
            severidad=severidad,
            indice_salud=indice_salud,
            etiqueta_salud=etiqueta_salud,
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
            tendencia_temp=tendencia_temp['mensaje'],
            tendencia_pres=tendencia_pres['mensaje'],
            pronostico=pronostico['mensaje'],
            pronostico_nivel=pronostico['nivel'],
            causa_probable=causa_probable,
            alertas_confirmadas=lectura['alertas_confirmadas'],
            estadisticas_feedback=self.historial.obtener_estadisticas(),
        )
        self._ultima_lectura_publicada = {
            **lectura,
            'estado_global': estado_global,
            'severidad': severidad,
            'indice_salud': indice_salud,
            'etiqueta_salud': etiqueta_salud,
            'estado_temperatura': estado_temperatura,
            'estado_presion': estado_presion,
            'porcentaje_carga': porcentaje_carga,
            'tendencia_temp': tendencia_temp['mensaje'],
            'tendencia_pres': tendencia_pres['mensaje'],
            'pronostico': pronostico['mensaje'],
            'pronostico_nivel': pronostico['nivel'],
            'causa_probable': causa_probable,
            'prescripcion_maria': prescripcion_maria,
        }
        self._ultimo_panel_bytes = imagen_bytes

        for chat_id in chats:
            await self.telegram.enviar_mensaje_con_boton_pdf(
                chat_id,
                texto,
                alerta_id=alerta_id_feedback,
            )
            await asyncio.sleep(1)
            await self.telegram.enviar_imagen(chat_id, imagen_bytes, caption="Panel multimodal de proceso")
            await asyncio.sleep(1)
            await self.telegram.enviar_audio(chat_id, audio_bytes)
            await asyncio.sleep(1)

    async def _procesar_eventos_chat(self) -> None:
        """Atiende solicitudes de PDF y feedback hechas desde Telegram."""
        eventos = await self.telegram.obtener_eventos_chat()
        for chat_id in eventos['pdf']:
            if self._telemetria is None or self._indice_actual <= 0:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "Aun no hay suficientes lecturas procesadas para generar el PDF.",
                )
                continue

            await self.telegram.enviar_mensaje_simple(
                chat_id,
                "Generando reporte PDF bajo demanda. Un momento por favor.",
            )
            enviado = await self._enviar_pdf(chat_id)
            if enviado:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "PDF enviado correctamente al chat.",
                )
            else:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "No fue posible generar o enviar el PDF en este momento.",
                )
            await asyncio.sleep(1)

        for chat_id in eventos['dashboard']:
            enviado = await self._enviar_dashboard(chat_id)
            if enviado:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "Dashboard enviado correctamente al chat.",
                )
            else:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "No fue posible enviar el dashboard en este momento.",
                )
            await asyncio.sleep(1)

        for chat_id in eventos['ficha_operario']:
            enviado = await self._enviar_ficha_ia(chat_id, audiencia='operario')
            if not enviado:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "No fue posible generar la ficha visual IA para operacion en este momento.",
                )
            await asyncio.sleep(1)

        for chat_id in eventos['ficha_gerencial']:
            enviado = await self._enviar_ficha_ia(chat_id, audiencia='gerencial')
            if not enviado:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "No fue posible generar la ficha visual IA gerencial en este momento.",
                )
            await asyncio.sleep(1)

        for chat_id in eventos['explicar_evento']:
            enviado = await self._enviar_explicacion_evento(chat_id)
            if not enviado:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "No fue posible explicar el evento con IA en este momento.",
                )
            await asyncio.sleep(1)

        for chat_id, alerta_id, feedback in eventos['feedback']:
            ok = self.historial.registrar_feedback(alerta_id, feedback)
            if ok:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    f"Feedback registrado para la alerta {alerta_id}: {feedback}.",
                )
            else:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    f"No fue posible registrar el feedback de la alerta {alerta_id}.",
                )
            await asyncio.sleep(1)

    def _obtener_chats_destino(self, id_maquina: str) -> list[int]:
        personal = self.data_loader.obtener_personal_en_turno(self._planta_objetivo, id_maquina)
        if personal.empty and self.data_loader.personal is not None:
            personal = self.data_loader.personal[
                (self.data_loader.personal['id_planta'] == self._planta_objetivo) &
                (
                    (self.data_loader.personal['id_maquina_asignada'].str.strip() == id_maquina) |
                    (self.data_loader.personal['id_maquina_asignada'].str.strip().str.upper() == 'TODAS')
                )
            ].copy()

        chats: list[int] = []
        for _, persona in personal.iterrows():
            celular = str(persona['numero_celular']).strip()
            chat_id = self.telegram.obtener_chat_id(celular)
            if chat_id is not None and chat_id not in chats:
                chats.append(chat_id)
        return chats

    async def _enviar_pdf(self, chat_id: int) -> bool:
        if self._telemetria is None or self._indice_actual <= 0:
            logger.warning("No hay datos suficientes para generar PDF.")
            return False

        try:
            logger.info("Generando PDF tras %d lecturas.", self._lecturas_procesadas)
            df_total = self._telemetria.iloc[:self._indice_actual].copy()
            pdf_bytes = self.pdf_gen.generar_reporte_tiempo_real(
                df_telemetria=df_total,
                data_loader=self.data_loader,
                historial_alertas=self.historial,
            )
            nombre_pdf = f"Reporte_planta_001_lectura_{self._lecturas_procesadas}.pdf"
            enviado = await self.telegram.enviar_pdf(
                chat_id=chat_id,
                pdf_bytes=pdf_bytes,
                nombre=nombre_pdf,
            )
            if not enviado:
                logger.error("Telegram no confirmo el envio del PDF a chat_id=%d", chat_id)
            return enviado
        except Exception as e:
            logger.error("Fallo generando o enviando PDF para chat_id=%d: %s", chat_id, e, exc_info=True)
            return False

    async def _enviar_dashboard(self, chat_id: int) -> bool:
        """Envía el dashboard HTML actualizado al chat solicitado."""
        try:
            contenido = self.dashboard.obtener_html()
            if not contenido:
                logger.warning("No hay dashboard disponible para enviar.")
                return False
            nombre = f"dashboard_planta_001_lectura_{self._lecturas_procesadas}.html"
            return await self.telegram.enviar_documento(
                chat_id=chat_id,
                contenido=contenido,
                nombre=nombre,
                caption="Dashboard ejecutivo local de planta 001",
            )
        except Exception as e:
            logger.error("Fallo enviando dashboard para chat_id=%d: %s", chat_id, e, exc_info=True)
            return False

    async def _enviar_ficha_ia(self, chat_id: int, audiencia: str) -> bool:
        """Genera y envia una ficha visual IA adaptada a la audiencia."""
        if self._ultima_lectura_publicada is None or self._ultimo_panel_bytes is None:
            logger.warning("No hay contexto multimodal para ficha IA.")
            return False

        await self.telegram.enviar_mensaje_simple(
            chat_id,
            (
                "Generando ficha visual IA para operacion. Un momento por favor."
                if audiencia == 'operario'
                else "Generando ficha visual IA gerencial. Un momento por favor."
            ),
        )
        prompt = self._construir_prompt_ficha_ia(
            self._ultima_lectura_publicada,
            audiencia=audiencia,
        )
        imagen_ia, texto_ia = self.nano_banana.generar_ficha_visual(
            prompt_texto=prompt,
            imagen_referencia_bytes=self._ultimo_panel_bytes,
        )
        if imagen_ia is None:
            await self.telegram.enviar_mensaje_simple(chat_id, texto_ia)
            return False

        enviado = await self.telegram.enviar_imagen(
            chat_id,
            imagen_ia,
            caption=(
                "Ficha IA para operacion"
                if audiencia == 'operario'
                else "Ficha IA gerencial"
            ),
        )
        if texto_ia:
            logger.info("Resumen textual de Nano Banana: %s", texto_ia)
        return enviado

    async def _enviar_explicacion_evento(self, chat_id: int) -> bool:
        """Genera una explicacion multimodal corta para demo y capacitacion."""
        if self._ultima_lectura_publicada is None or self._ultimo_panel_bytes is None:
            logger.warning("No hay contexto disponible para explicar evento.")
            return False

        await self.telegram.enviar_mensaje_simple(
            chat_id,
            "Generando explicacion multimodal del evento. Un momento por favor.",
        )
        prompt = self._construir_prompt_explicacion_evento(self._ultima_lectura_publicada)
        explicacion = self.llm.diagnosticar(
            prompt_texto=prompt,
            imagen_bytes=self._ultimo_panel_bytes,
        )
        explicacion = self._limpiar_texto_llm(explicacion)
        return await self.telegram.enviar_mensaje_simple(
            chat_id,
            f"<b>Explicacion IA del evento:</b>\n{html.escape(explicacion)}",
        )

    def _construir_prompt_ficha_ia(
        self,
        lectura: dict[str, Any],
        audiencia: str,
    ) -> str:
        """Construye el prompt multimodal para Nano Banana."""
        accion_sugerida = self._accion_sugerida_ficha(lectura)
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
- Usa estilo industrial corporativo, con jerarquia fuerte y composicion centrada.
- {instruccion_audiencia}
- La salida debe parecer una ficha de incidente o una tarjeta ejecutiva, no una grafica.
- Incluye como maximo 5 bloques:
  1. encabezado con planta, maquina y formula
  2. sello grande de estado global y severidad
  3. bloque de salud del proceso
  4. bloque de causa probable
  5. bloque de accion sugerida
- Si el estado es estable, presenta la pieza como continuidad operacional y monitoreo.
- Si el estado es preventivo, alto o critico, presenta la pieza como alerta priorizada.
- Puedes usar iconos industriales simples, bandas de color, flechas, indicadores y sellos visuales.
- Evita saturar texto. Frases cortas y contundentes.
- Usa colores segun severidad:
  - informativa: azul y verde
  - preventiva: amarillo/naranja
  - alta: rojo
  - critica: rojo oscuro y negro
- No inventes valores diferentes a los entregados.
- Devuelve tambien una nota textual muy corta, maximo dos frases, explicando la ficha generada.
"""

    def _construir_prompt_llm_operativo(
        self,
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

    def _construir_prompt_explicacion_evento(self, lectura: dict[str, Any]) -> str:
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

    def _generar_prescripcion_maria(
        self,
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
        imagen_bytes: bytes,
    ) -> str:
        """Obtiene la prescripcion multimodal de Maria con fallback determinista."""
        prompt = self._construir_prompt_llm_operativo(
            lectura=lectura,
            estado_global=estado_global,
            severidad=severidad,
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
            tendencia_temp=tendencia_temp,
            tendencia_pres=tendencia_pres,
            pronostico=pronostico,
            pronostico_nivel=pronostico_nivel,
            causa_probable=causa_probable,
            diagnostico_operativo=diagnostico_operativo,
        )
        try:
            prescripcion = self.llm.diagnosticar(
                prompt_texto=prompt,
                imagen_bytes=imagen_bytes,
            )
            prescripcion = self._limpiar_texto_llm(prescripcion)
            if prescripcion:
                return prescripcion
        except Exception as e:
            logger.error("Fallo obteniendo prescripcion multimodal de Maria: %s", e, exc_info=True)
        return diagnostico_operativo

    def _limpiar_texto_llm(self, texto: str) -> str:
        """Limpia marcas simples para reutilizar el texto del LLM en chat y audio."""
        texto_limpio = (texto or "").strip()
        reemplazos = ['**', '*', '[', ']', '#']
        for marca in reemplazos:
            texto_limpio = texto_limpio.replace(marca, '')
        return " ".join(texto_limpio.split())

    def _accion_sugerida_ficha(self, lectura: dict[str, Any]) -> str:
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

    def _estado_en_banda(self, valor: float, limite_min: float, limite_max: float) -> str:
        """Clasifica una variable respecto a su banda operativa."""
        if valor < limite_min:
            return 'BAJO'
        if valor > limite_max:
            return 'ALTO'
        return 'NORMAL'

    def _construir_diagnostico_operativo(
        self,
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

    def _clasificar_contexto_global(
        self,
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

    def _inferir_causa_probable(
        self,
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

    def _calcular_indice_salud(
        self,
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

    def _registrar_alertas_confirmadas(
        self,
        lectura: dict[str, Any],
        diagnostico_operativo: str,
        severidad: str,
        causa_probable: str,
        pronostico: str,
    ) -> Optional[int]:
        """Registra alertas confirmadas en historial y devuelve el primer ID para feedback."""
        alertas = lectura.get('alertas_confirmadas', [])
        primer_id: Optional[int] = None

        for alerta in alertas:
            prescripcion = (
                f"Severidad {severidad}. "
                f"Causa probable: {causa_probable}. "
                f"Pronostico a 5 min: {pronostico}. "
                f"{diagnostico_operativo}"
            )
            alerta_id = self.historial.registrar_alerta(
                timestamp=alerta.timestamp,
                id_planta=alerta.id_planta,
                id_maquina=alerta.id_maquina,
                id_formula=alerta.id_formula,
                codigo_producto=alerta.codigo_producto,
                variable=alerta.variable,
                tipo_alerta=alerta.tipo_alerta.value,
                valor_crudo=alerta.valor_crudo,
                valor_suavizado=alerta.valor_suavizado,
                limite_violado=alerta.limite_violado,
                limite_min=alerta.limite_min,
                limite_max=alerta.limite_max,
                porcentaje_carga=alerta.porcentaje_carga,
                prescripcion_ia=prescripcion,
            )
            if primer_id is None and not alerta.es_retorno_normal:
                primer_id = alerta_id

        return primer_id

    def _resumir_alertas_confirmadas(self, alertas: list[Any]) -> str:
        """Resume alertas confirmadas en una linea legible para el operario."""
        activas = [a for a in alertas if not a.es_retorno_normal]
        if not activas:
            return ''
        etiquetas = [a.tipo_alerta.value.replace('_', ' ') for a in activas]
        return ', '.join(etiquetas)

    def _analizar_tendencia(
        self,
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

    def _construir_pronostico(
        self,
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


def main() -> None:
    print(
        """
    ================================================
      MODO MINIMO TELEGRAM - PLANTA 001
      Texto + Imagen + Audio
      PDF bajo demanda desde el chat
    ================================================
    """
    )

    worker = WorkerPeletizacion()
    worker.inicializar()
    worker.ejecutar()


if __name__ == '__main__':
    main()
