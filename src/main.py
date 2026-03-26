"""
Pipeline minimo de Telegram para validar texto, imagen y audio.
"""

import json
import os
import sys
import signal
import asyncio
import logging
import threading
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
# TTS removido — no se usa en el pipeline actual
from telegram_bot import TelegramNotificador
from generador_pdf import GeneradorPDF
from historial_alertas import HistorialAlertas
from historial_operario import HistorialOperario
from dashboard_ejecutivo import DashboardEjecutivo
from imagen_generativa import NanoBananaProvider
from llm_multimodal import GeminiProvider
from herramientas_agente import HerramientasAgente
from feedback_loop import FeedbackLoop
from shadow_tester import ShadowTester
from generador_video_telemetria import GeneradorVideoTelemetria
from email_service import EmailService
from memoria_incidentes import MemoriaIncidentes
from analizador_telemetria import AnalizadorTelemetria
from constructor_prompts import ConstructorPrompts
from constructor_mensajes import ConstructorMensajes
from feature_store import FeatureStore

logger = logging.getLogger(__name__)


class WorkerPeletizacion:
    """Worker minimo para depurar el envio por Telegram."""

    def __init__(self) -> None:
        self.config = ConfigLoader()
        self.config.configurar_logging()

        self.data_loader = DataLoader(self.config)
        self.motor = MotorReglas(self.config)
        self.graficas = GeneradorGraficas()
        # TTS removido — no se usa en el pipeline actual
        self.telegram = TelegramNotificador(self.config)
        self.pdf_gen = GeneradorPDF(self.config)
        self.historial = HistorialAlertas(self.config)
        self.historial_operario = HistorialOperario(self.config)
        self.dashboard = DashboardEjecutivo(self.config)
        self.nano_banana = NanoBananaProvider(self.config)
        self.llm = GeminiProvider(self.config)
        self.feedback_loop = FeedbackLoop(data_dir=self.config.data_dir)
        self.herramientas = HerramientasAgente(
            data_dir=self.config.data_dir,
            data_loader=self.data_loader,
            config=self.config,
            feedback_loop=self.feedback_loop,
        )
        self.shadow_tester    = ShadowTester(self.llm, self.config)
        self.generador_video  = GeneradorVideoTelemetria(ventana_lecturas=30, n_frames=10)
        self.feature_store    = FeatureStore(ventana=30)
        self._ciclos_sin_deriva = 0   # Contador para chequeo periódico de deriva
        self.email_service = EmailService(self.config)
        self.memoria_incidentes = MemoriaIncidentes(self.config)

        self._ejecutando = True
        self._planta_objetivo = '001'
        self._indice_actual = 0
        self._lecturas_procesadas = 0
        self._telemetria: Optional[pd.DataFrame] = None
        self._historial_reciente: dict[str, list[dict[str, Any]]] = {}
        self._ventana_historial = 8
        self._ultima_lectura_publicada: Optional[dict[str, Any]] = None
        self._ultimo_panel_bytes: Optional[bytes] = None
        self._chats_pausados_operacion: dict[int, dict[str, Any]] = {}
        self._incidentes_chat: dict[int, dict[str, Any]] = {}
        # Memoria de conversación por chat — se incluye en cada llamada a Gemini
        # para que María recuerde lo dicho dentro del mismo incidente.
        # Se limpia al cerrar el incidente (botón "Sí, solucionado").
        self._historial_conversacion: dict[int, list[dict[str, str]]] = {}
        # Última foto enviada por el operario por chat — se incluye en llamadas posteriores
        # para que María pueda referenciar la imagen en audios/textos siguientes.
        self._ultima_foto_operario: dict[int, bytes] = {}

        # Pub/Sub — cola thread-safe entre el callback del subscriber y el loop async
        import queue as _queue_mod
        self._mensajes_pubsub: _queue_mod.Queue = _queue_mod.Queue()
        # Set de message_ids ya procesados — garantiza idempotencia (at-least-once delivery)
        self._ids_procesados: set = set()
        self._subscriber_streaming = None   # Handle del streaming pull activo

        signal.signal(signal.SIGINT, self._manejar_shutdown)
        if hasattr(signal, 'SIGTERM'):
            try:
                signal.signal(signal.SIGTERM, self._manejar_shutdown)
            except OSError:
                pass  # SIGTERM no soportado en Windows

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
        """
        Punto de entrada del worker. Despacha al modo correcto según config:
            PUBSUB_HABILITADO=1 → modo evento (Pub/Sub, latencia ms)
            PUBSUB_HABILITADO=0 → modo polling (CSV cada N segundos)
        """
        if self.config.pubsub_habilitado:
            logger.info("Modo PUB/SUB habilitado — latencia de eventos en tiempo real.")
            self.ejecutar_con_pubsub()
            return

        logger.info(
            "Modo POLLING iniciado. Intervalo: %d segundos.",
            self.config.intervalo_simulacion,
        )
        siguiente_lectura_ts = time.time()

        while self._ejecutando:
            try:
                asyncio.run(self._ciclo_principal(siguiente_lectura_ts))
                ahora = time.time()
                if ahora >= siguiente_lectura_ts and not self._flujo_telemetria_bloqueado():
                    siguiente_lectura_ts = ahora + self.config.intervalo_simulacion
                    # Detección de deriva cada 100 ciclos (~8 min con intervalo 5s)
                    self._ciclos_sin_deriva += 1
                    if self._ciclos_sin_deriva >= 100:
                        self._ciclos_sin_deriva = 0
                        self._verificar_deriva_umbrales()
            except Exception as e:
                logger.error("Error en worker minimo: %s", e, exc_info=True)

            time.sleep(1)

        logger.info("Worker minimo detenido tras %d lecturas.", self._lecturas_procesadas)

    def _enriquecer_lectura_raw(self, datos: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        Enriquece una lectura cruda de sensores con datos maestros, EMA y motor de reglas.

        Acepta un dict con los valores crudos del sensor (proveniente del CSV o de un
        mensaje Pub/Sub) y retorna el dict completo listo para _enviar_paquete_minimo.
        Este método es el núcleo compartido entre el modo polling y el modo Pub/Sub.

        Args:
            datos: Dict con campos del sensor: id_maquina, id_formula, timestamp_sensor,
                   corriente, temp_acond, presion_vapor, y los demás campos del CSV.
        """
        id_maquina = str(datos.get('id_maquina', '')).strip().zfill(3)
        id_formula = str(datos.get('id_formula', '')).strip()

        limites = self.data_loader.obtener_limites_formula(self._planta_objetivo, id_formula)
        specs   = self.data_loader.obtener_specs_equipo(self._planta_objetivo, id_maquina)
        if limites is None or specs is None:
            logger.warning("Lectura omitida: datos maestros faltantes para maquina=%s formula=%s", id_maquina, id_formula)
            return None

        # Normalizar timestamp — puede venir como str (Pub/Sub) o datetime (CSV)
        timestamp_raw = datos.get('timestamp_sensor') or datos.get('fecha_registro')
        if isinstance(timestamp_raw, datetime):
            timestamp = timestamp_raw
        else:
            timestamp = pd.Timestamp(str(timestamp_raw)).to_pydatetime()

        corriente     = float(datos.get('corriente', 0))
        temp_acond    = float(datos.get('temp_acond', 0))
        presion_vapor = float(datos.get('presion_vapor', 0))

        alertas_motor = self.motor.evaluar_lectura(
            id_planta=self._planta_objetivo,
            id_maquina=id_maquina,
            id_formula=id_formula,
            codigo_producto=str(limites.get('codigo_producto', '')),
            corriente=corriente,
            temp_acond=temp_acond,
            presion_vapor=presion_vapor,
            timestamp=timestamp,
            corriente_carga_minima=float(specs['corriente_carga_minima']),
            capacidad_nominal=float(specs['capacidad_nominal']),
            t_min=float(limites['t_min']),
            t_max=float(limites['t_max']),
            p_min=float(limites['p_min']),
            p_max=float(limites['p_max']),
        )

        estado = self.motor.obtener_estado_maquina(self._planta_objetivo, id_maquina)
        clave  = f"{self._planta_objetivo}_{id_maquina}"

        if clave not in self._historial_reciente:
            self._historial_reciente[clave] = []
        self._historial_reciente[clave].append({
            'timestamp':    timestamp,
            'temp_acond':   temp_acond,
            'presion_vapor': presion_vapor,
            'corriente':    corriente,
            'temp_ema':     estado.ema_temperatura if estado and estado.ema_temperatura is not None else temp_acond,
            'presion_ema':  estado.ema_presion     if estado and estado.ema_presion     is not None else presion_vapor,
            'corriente_ema': estado.ema_corriente  if estado and estado.ema_corriente   is not None else corriente,
        })
        if len(self._historial_reciente[clave]) > self._ventana_historial:
            self._historial_reciente[clave] = self._historial_reciente[clave][-self._ventana_historial:]

        self._lecturas_procesadas += 1

        # Determinar la variable principal en alerta (para few-shot y shadow logging)
        variable_principal = ""
        for alerta in alertas_motor:
            # Alerta puede ser dataclass (motor_reglas.Alerta) o dict
            if hasattr(alerta, 'variable'):
                nombre = str(alerta.variable).upper()
            elif hasattr(alerta, 'tipo_alerta'):
                nombre = str(alerta.tipo_alerta).upper()
            elif isinstance(alerta, dict):
                nombre = str(alerta.get('nombre', '') or alerta.get('tipo', '')).upper()
            else:
                nombre = str(alerta).upper()
            if 'TEMP' in nombre:
                variable_principal = "temp_acond"
                break
            elif 'PRES' in nombre:
                variable_principal = "presion_vapor"
                break
            elif 'CORR' in nombre or 'CARGA' in nombre:
                variable_principal = "corriente"
                break

        return {
            'numero':            self._lecturas_procesadas,
            'timestamp':         timestamp,
            'id_planta':         self._planta_objetivo,
            'id_maquina':        id_maquina,
            'id_formula':        id_formula,
            'numero_orden':      str(datos.get('numero_orden', '')),
            'codigo_producto':   str(limites.get('codigo_producto', '')),
            'variable_principal': variable_principal,
            'temp_ema':          estado.ema_temperatura if estado and estado.ema_temperatura is not None else temp_acond,
            'presion_ema':       estado.ema_presion     if estado and estado.ema_presion     is not None else presion_vapor,
            'corriente_ema':     estado.ema_corriente   if estado and estado.ema_corriente   is not None else corriente,
            't_min':             float(limites['t_min']),
            't_max':             float(limites['t_max']),
            'p_min':             float(limites['p_min']),
            'p_max':             float(limites['p_max']),
            'capacidad_nominal': float(specs['capacidad_nominal']),
            'historial_reciente': list(self._historial_reciente[clave]),
            'alertas_confirmadas': alertas_motor,
        }

    def _obtener_siguiente_lectura(self) -> Optional[dict[str, Any]]:
        """Modo polling: obtiene la siguiente fila del CSV y la enriquece."""
        if self._telemetria is None or self._telemetria.empty:
            logger.warning("No hay telemetria disponible.")
            return None

        if self._indice_actual >= len(self._telemetria):
            logger.info("Fin de telemetria. Reiniciando desde el inicio.")
            self._indice_actual = 0

        fila = self._telemetria.iloc[self._indice_actual]
        self._indice_actual += 1

        # Convertir la fila a dict normalizado y delegar al enriquecedor
        datos_raw = {
            'id_maquina':      fila['id_maquina'],
            'id_formula':      fila['id_formula'],
            'timestamp_sensor': fila['fecha_registro'],
            'corriente':       fila['corriente'],
            'temp_acond':      fila['temp_acond'],
            'presion_vapor':   fila['presion_vapor'],
            'vapor':           fila.get('vapor', 0),
            'porcentaje_vapor': fila.get('porcentaje_vapor', 0),
            'tiempo_proceso':  fila.get('tiempo_proceso', 0),
            'retornando':      fila.get('retornando', 0),
            'humedad_real':    fila.get('humedad_real', 0),
            'durabilidad_real': fila.get('durabilidad_real', 0),
            'kw_h_proceso':    fila.get('kw_h_proceso', 0),
        }
        return self._enriquecer_lectura_raw(datos_raw)

    async def _enviar_paquete_minimo(self, lectura: dict[str, Any]) -> None:
        # Alimentar el buffer del video en cada lectura (no solo en alertas)
        # para que el GIF siempre tenga contexto temporal actualizado.
        self.generador_video.agregar_lectura(lectura)
        self.feature_store.agregar_lectura(lectura)

        destinatarios = self._obtener_destinatarios(lectura['id_maquina'])
        if not destinatarios:
            logger.warning("No hay chats destino configurados.")
            return

        porcentaje_carga = (
            lectura['corriente_ema'] / lectura['capacidad_nominal'] * 100
            if lectura['capacidad_nominal'] > 0 else 0.0
        )
        estado_temperatura = AnalizadorTelemetria.estado_en_banda(
            lectura['temp_ema'], lectura['t_min'], lectura['t_max']
        )
        estado_presion = AnalizadorTelemetria.estado_en_banda(
            lectura['presion_ema'], lectura['p_min'], lectura['p_max']
        )
        diagnostico_operativo = AnalizadorTelemetria.construir_diagnostico_operativo(
            lectura=lectura,
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
        )
        tendencia_temp = AnalizadorTelemetria.analizar_tendencia(
            lectura['historial_reciente'],
            'temp_ema',
            lectura['t_min'],
            lectura['t_max'],
        )
        tendencia_pres = AnalizadorTelemetria.analizar_tendencia(
            lectura['historial_reciente'],
            'presion_ema',
            lectura['p_min'],
            lectura['p_max'],
        )
        pronostico = AnalizadorTelemetria.construir_pronostico(
            tendencia_temp=tendencia_temp,
            tendencia_pres=tendencia_pres,
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
        )
        estado_global, severidad = AnalizadorTelemetria.clasificar_contexto_global(
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
            pronostico_nivel=pronostico['nivel'],
        )
        causa_probable = AnalizadorTelemetria.inferir_causa_probable(
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
            tendencia_temp=tendencia_temp['mensaje'],
            tendencia_pres=tendencia_pres['mensaje'],
            pronostico_nivel=pronostico['nivel'],
        )
        indice_salud, etiqueta_salud = AnalizadorTelemetria.calcular_indice_salud(
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
            tendencia_temp=tendencia_temp['mensaje'],
            tendencia_pres=tendencia_pres['mensaje'],
            pronostico=pronostico['mensaje'],
        )
        predictor_incidente = self._calcular_predictor_incidente(
            id_maquina=lectura['id_maquina'],
            causa_probable=causa_probable,
            severidad=severidad,
            pronostico_nivel=pronostico['nivel'],
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
        )
        alerta_id_feedback = self._registrar_alertas_confirmadas(
            lectura=lectura,
            diagnostico_operativo=diagnostico_operativo,
            severidad=severidad,
            causa_probable=causa_probable,
            pronostico=pronostico['mensaje'],
        )
        resumen_alerta = AnalizadorTelemetria.resumir_alertas_confirmadas(lectura['alertas_confirmadas'])

        texto_operario = ConstructorMensajes.mensaje_operario(
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
        )
        if resumen_alerta:
            texto_operario += f"\n<b>Alarma:</b> {resumen_alerta}"

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

        # Generar GIF animado de la serie temporal (Feature 8).
        # Solo si hay suficientes datos en el buffer (mínimo 10 lecturas).
        video_bytes: Optional[bytes] = None
        if self.generador_video.hay_suficientes_datos():
            video_bytes = self.generador_video.generar_gif(
                titulo=f"Máquina {lectura['id_maquina']} | Últimas 30 lecturas"
            )

        # Prescripción IA con loop agentico, few-shot y video temporal.
        # El shadow_tester decide si usar variante A, B o ambas (según config).
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
            video_bytes=video_bytes,
        )
        texto_operario += "\n<i>Si necesitas apoyo, enviame una nota de voz.</i>"
        texto_gerencial = ConstructorMensajes.mensaje_gerencial(
            lectura=lectura,
            estado_global=estado_global,
            severidad=severidad,
            indice_salud=indice_salud,
            etiqueta_salud=etiqueta_salud,
            estado_temperatura=estado_temperatura,
            estado_presion=estado_presion,
            porcentaje_carga=porcentaje_carga,
            pronostico=pronostico['mensaje'],
            pronostico_nivel=pronostico['nivel'],
            causa_probable=causa_probable,
            prescripcion_maria=prescripcion_maria,
            resumen_alerta=resumen_alerta,
        )

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
            estadisticas_incidentes=self.memoria_incidentes.obtener_estadisticas(),
            predictor_incidente=predictor_incidente,
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
            'predictor_incidente': predictor_incidente,
        }
        self._ultimo_panel_bytes = imagen_bytes

        for destinatario in destinatarios:
            chat_id = int(destinatario['chat_id'])
            audiencia = str(destinatario['audiencia'])
            if audiencia == 'operario' and self._chat_pausado(chat_id):
                logger.info(
                    "Envio omitido para chat_id=%d por pausa operativa activa.",
                    chat_id,
                )
                continue
            texto = texto_operario if audiencia == 'operario' else texto_gerencial
            await self.telegram.enviar_mensaje_con_boton_pdf(
                chat_id,
                texto,
                alerta_id=alerta_id_feedback,
                audiencia=audiencia,
            )
            await asyncio.sleep(1)
            await self.telegram.enviar_imagen(chat_id, imagen_bytes, caption="Panel multimodal de proceso")
            await asyncio.sleep(1)

    # -----------------------------------------------------------------------
    # Modo Pub/Sub
    # -----------------------------------------------------------------------

    def _callback_pubsub(self, message) -> None:
        """
        Callback invocado por el subscriber de Pub/Sub en un hilo separado.
        No procesa el mensaje aquí — lo encola para el loop async principal.
        Hace ACK inmediato para no bloquear el canal de Pub/Sub.

        Garantía de idempotencia: si el mismo message_id ya fue procesado
        (at-least-once delivery de Pub/Sub), se descarta silenciosamente.
        """
        try:
            datos = json.loads(message.data.decode("utf-8"))
            message_id = datos.get("message_id", message.message_id)

            if message_id in self._ids_procesados:
                logger.debug("[PUBSUB] Mensaje duplicado descartado: %s", message_id)
                message.ack()
                return

            self._ids_procesados.add(message_id)
            # Limpiar el set periódicamente para no crecer indefinidamente
            if len(self._ids_procesados) > 10_000:
                self._ids_procesados.clear()

            self._mensajes_pubsub.put(datos)
            message.ack()
            logger.debug(
                "[PUBSUB] Mensaje encolado: máquina=%s T=%.1f°C P=%.2f PSI",
                datos.get("id_maquina", "?"),
                datos.get("temp_acond", 0),
                datos.get("presion_vapor", 0),
            )
        except Exception as e:
            logger.error("[PUBSUB] Error en callback: %s", e)
            message.nack()

    def _iniciar_subscriber_pubsub(self) -> None:
        """
        Inicia el streaming pull del subscriber de Pub/Sub.
        Corre en background — el callback encola mensajes para el loop principal.
        """
        try:
            from google.cloud import pubsub_v1

            subscriber = pubsub_v1.SubscriberClient()
            subscription_path = subscriber.subscription_path(
                self.config.gcp_project,
                self.config.pubsub_subscription,
            )

            # Crear suscripción si no existe
            try:
                from google.cloud.pubsub_v1.types import pubsub as pubsub_types
                topic_path = f"projects/{self.config.gcp_project}/topics/{self.config.pubsub_topic}"
                subscriber.create_subscription(
                    request={"name": subscription_path, "topic": topic_path}
                )
                logger.info("[PUBSUB] Suscripción creada: %s", subscription_path)
            except Exception as e:
                if "AlreadyExists" in str(e) or "409" in str(e):
                    logger.debug("[PUBSUB] Suscripción ya existe: %s", subscription_path)
                else:
                    logger.warning("[PUBSUB] No se pudo crear suscripción: %s", e)

            self._subscriber_streaming = subscriber.subscribe(
                subscription_path,
                callback=self._callback_pubsub,
            )
            logger.info(
                "[PUBSUB] Subscriber iniciado. Escuchando en: %s",
                subscription_path,
            )
        except Exception as e:
            logger.error("[PUBSUB] Error iniciando subscriber: %s", e)
            raise

    def _drenar_cola_pubsub(self) -> None:
        """
        Drena todos los mensajes encolados por el callback de Pub/Sub
        y los procesa sincrónicamente en el loop principal.
        Llamado en cada ciclo del loop para mantener baja latencia.
        """
        import queue as _q
        procesados = 0
        while True:
            try:
                datos_raw = self._mensajes_pubsub.get_nowait()
            except _q.Empty:
                break

            lectura = self._enriquecer_lectura_raw(datos_raw)
            if lectura is not None:
                asyncio.run(self._enviar_paquete_minimo(lectura))
                procesados += 1

        if procesados:
            logger.info("[PUBSUB] %d lecturas procesadas en este ciclo.", procesados)

    def ejecutar_con_pubsub(self) -> None:
        """
        Modo Pub/Sub: el worker escucha mensajes en tiempo real en lugar de
        hacer polling del CSV cada N segundos.

        Flujo:
            1. Inicia el publisher en un hilo daemon (simula sensores).
            2. Inicia el subscriber en streaming pull (background).
            3. Loop principal drena la cola y procesa mensajes.
            4. El loop sigue atendiendo chat y escalaciones como siempre.

        Ventaja sobre polling:
            - Latencia de milisegundos en lugar de segundos.
            - Garantía de entrega (at-least-once) con idempotencia.
            - Publisher y subscriber completamente desacoplados.
        """
        from publisher_telemetria import PublisherTelemetria

        logger.info(
            "Worker iniciado en modo PUB/SUB. Topic: %s | Subscription: %s",
            self.config.pubsub_topic,
            self.config.pubsub_subscription,
        )

        # Iniciar publisher en hilo daemon (simula sensores de la planta)
        publisher = PublisherTelemetria(self.config)
        hilo_publisher = threading.Thread(
            target=publisher.publicar_en_loop,
            daemon=True,
            name="publisher-telemetria",
        )
        hilo_publisher.start()
        logger.info("[PUBSUB] Publisher iniciado en hilo daemon.")

        # Iniciar subscriber (streaming pull en background)
        self._iniciar_subscriber_pubsub()

        try:
            while self._ejecutando:
                try:
                    asyncio.run(self._procesar_eventos_chat())
                    asyncio.run(self._drenar_escalaciones_agente())
                    self._drenar_cola_pubsub()

                    # Detección de deriva periódica
                    self._ciclos_sin_deriva += 1
                    if self._ciclos_sin_deriva >= 100:
                        self._ciclos_sin_deriva = 0
                        self._verificar_deriva_umbrales()

                except Exception as e:
                    logger.error("[PUBSUB] Error en ciclo: %s", e, exc_info=True)

                time.sleep(0.2)   # 200ms — mucho más reactivo que el 1s del polling

        finally:
            if self._subscriber_streaming:
                self._subscriber_streaming.cancel()
                logger.info("[PUBSUB] Subscriber detenido.")
            publisher.detener()
            logger.info("[PUBSUB] Publisher detenido.")

    def _verificar_deriva_umbrales(self) -> None:
        """
        Corre detección de deriva de umbrales cada 100 ciclos del worker.
        Si detecta tasa de falsos positivos > 30% en algún par (máquina, variable),
        lo registra como warning para que el equipo de ingeniería lo revise.
        En producción, este punto puede disparar un correo automático al supervisor.
        """
        try:
            derivas = self.feedback_loop.detectar_deriva_umbrales(ventana_dias=14)
            if derivas:
                for d in derivas:
                    logger.warning(
                        "[RLHF] DERIVA DE UMBRAL — Máquina: %s | Variable: %s | "
                        "Falsos: %d%% (%d/%d alertas) | %s",
                        d["id_maquina"],
                        d["variable"],
                        int(d["tasa_falsos_positivos"] * 100),
                        d["falsos"],
                        d["alertas_evaluadas"],
                        d["recomendacion"],
                    )
        except Exception as e:
            logger.error("[RLHF] Error en verificación de deriva: %s", e)

    async def _drenar_escalaciones_agente(self) -> None:
        """
        Drena la cola de escalaciones generadas por el agente IA durante su
        loop de razonamiento. Envía cada escalación al supervisor por Telegram.
        Se llama en cada ciclo del worker para garantizar latencia mínima.
        """
        import queue as _queue
        while True:
            try:
                escalacion = self.herramientas.cola_escalaciones.get_nowait()
            except _queue.Empty:
                break

            severidad = escalacion.get("severidad", "ALTA")
            id_maquina = escalacion.get("id_maquina", "?")
            mensaje = escalacion.get("mensaje", "")
            timestamp = escalacion.get("timestamp", "")

            texto = (
                f"🚨 <b>ESCALACIÓN AGENTE IA — Severidad {severidad}</b>\n"
                f"Máquina: <code>{id_maquina}</code>\n"
                f"Hora: {timestamp[:19]}\n\n"
                f"{mensaje}"
            )

            # Notificar a todos los supervisores con Telegram
            try:
                await self.telegram.notificar_supervisores(texto)
                logger.warning(
                    "Escalación de agente enviada a supervisores — Máquina: %s | Severidad: %s",
                    id_maquina, severidad,
                )
            except Exception as e:
                logger.error("Error enviando escalación de agente: %s", e)

    async def _ciclo_principal(self, siguiente_lectura_ts: float) -> None:
        """Un solo event loop por iteración: chat + escalaciones + telemetría."""
        await self._procesar_eventos_chat()
        await self._drenar_escalaciones_agente()

        ahora = time.time()
        if not self._flujo_telemetria_bloqueado() and ahora >= siguiente_lectura_ts:
            lectura = self._obtener_siguiente_lectura()
            if lectura is not None:
                await self._enviar_paquete_minimo(lectura)

    async def _procesar_eventos_chat(self) -> None:
        """Atiende mensajes del operario como conversación natural.

        Cada mensaje (audio, texto, foto) se procesa al instante.
        María siempre tiene el historial completo de la conversación
        para mantener contexto entre mensajes.
        """
        eventos = await self.telegram.obtener_eventos_chat()

        # Procesar cada mensaje individualmente, en orden de llegada
        for evento_audio in eventos['audio_operario']:
            await self._procesar_audio_operario(evento_audio)
        for evento_texto in eventos['texto_operario']:
            await self._procesar_texto_operario(evento_texto)
        for evento_foto in eventos['foto_operario']:
            await self._procesar_foto_operario(evento_foto)

        for chat_id, estado in eventos['resolver_operacion']:
            if estado == 'SI':
                incidente_id = int(self._incidentes_chat.get(chat_id, {}).get('id_incidente', 0) or 0)
                if incidente_id:
                    self.memoria_incidentes.registrar_evento(
                        id_incidente=incidente_id,
                        tipo_evento='confirmacion_solucion',
                        descripcion='El operario confirmo por boton que la novedad fue solucionada.',
                    )
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "Cierre confirmado. Generando ficha de incidente con IA antes de reanudar el monitoreo.",
                )
                cierre_ok = await self._enviar_ficha_cierre_incidente(chat_id)
                if cierre_ok:
                    self._reanudar_chat_operario(chat_id)
                    await self.telegram.enviar_mensaje_simple(
                        chat_id,
                        "Monitoreo automatico reanudado. La ficha de cierre ya fue enviada.",
                    )
                else:
                    await self.telegram.enviar_mensaje_simple(
                        chat_id,
                        "La ficha de cierre no pudo generarse todavia. Mantengo el sistema en espera.",
                    )
            else:
                incidente_id = int(self._incidentes_chat.get(chat_id, {}).get('id_incidente', 0) or 0)
                if incidente_id:
                    self.memoria_incidentes.registrar_evento(
                        id_incidente=incidente_id,
                        tipo_evento='continua_falla',
                        descripcion='El operario indico por boton que la falla continua.',
                    )
                self._pausar_chat_operario(chat_id, motivo='continua_falla')
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "Mantengo pausados los reportes automaticos. Cuando se estabilice, marca que ya fue solucionado.",
                )
            await asyncio.sleep(1)

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

    def _obtener_destinatarios(self, id_maquina: str) -> list[dict[str, Any]]:
        """Obtiene destinatarios en modo operario para este proyecto de demo."""
        personal = self.data_loader.obtener_personal_en_turno(self._planta_objetivo, id_maquina)
        if personal.empty and self.data_loader.personal is not None:
            personal = self.data_loader.personal[
                (self.data_loader.personal['id_planta'] == self._planta_objetivo) &
                (
                    (self.data_loader.personal['id_maquina_asignada'].str.strip() == id_maquina) |
                    (self.data_loader.personal['id_maquina_asignada'].str.strip().str.upper() == 'TODAS')
                )
            ].copy()

        destinatarios: list[dict[str, Any]] = []
        for _, persona in personal.iterrows():
            celular = str(persona['numero_celular']).strip()
            chat_id = self.telegram.obtener_chat_id(celular)
            rol = str(persona.get('rol', '')).strip().lower()
            audiencia = 'operario'
            ya_existe = any(item['chat_id'] == chat_id for item in destinatarios)
            if chat_id is not None and not ya_existe:
                destinatarios.append({
                    'chat_id': chat_id,
                    'audiencia': audiencia,
                    'rol': rol,
                })
        return destinatarios

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
                memoria_incidentes=self.memoria_incidentes,
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
        prompt = ConstructorPrompts.prompt_ficha_ia(
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
        prompt = ConstructorPrompts.prompt_explicacion_evento(self._ultima_lectura_publicada)
        explicacion = self.llm.diagnosticar(
            prompt_texto=prompt,
            imagen_bytes=self._ultimo_panel_bytes,
        )
        explicacion = AnalizadorTelemetria.limpiar_texto_llm(explicacion)
        return await self.telegram.enviar_mensaje_simple(
            chat_id,
            f"<b>Explicacion IA del evento:</b>\n{html.escape(explicacion)}",
        )

    async def _procesar_audio_operario(self, evento_audio: dict[str, Any]) -> None:
        """Interpreta una nota de voz del operario y la registra."""
        chat_id = int(evento_audio['chat_id'])
        self._pausar_chat_operario(
            chat_id,
            motivo='audio_recibido',
        )
        await self.telegram.enviar_mensaje_simple(
            chat_id,
            "Audio recibido. Interpretando nota de voz con Gemini.",
        )

        contexto = ConstructorPrompts.contexto_audio_operario(self._ultima_lectura_publicada)
        historial = self._construir_bloque_historial(chat_id)
        if historial:
            contexto = f"{contexto}\n\n{historial}"
        try:
            resultado = await asyncio.wait_for(
                asyncio.to_thread(
                    self.llm.interpretar_audio_operario,
                    audio_bytes=evento_audio['audio_bytes'],
                    mime_type=evento_audio['mime_type'],
                    prompt_texto=contexto,
                ),
                timeout=60,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Timeout interpretando audio del operario con Gemini para chat_id=%d",
                chat_id,
            )
            resultado = {
                'transcripcion': '',
                'intencion': 'OTRO',
                'accion_detectada': 'Timeout en interpretacion del audio.',
                'resumen_operario': 'Gemini tardo demasiado procesando la nota de voz.',
                'nivel_urgencia': 'MEDIO',
                'respuesta_asistente': (
                    'Tarde mas de lo esperado en interpretar la nota de voz. '
                    'Si el problema ya se soluciono, pulsa el boton de confirmacion o envia una nota mas corta.'
                ),
                'senal_resolucion': 'NO',
            }

        lectura = self._ultima_lectura_publicada or {}
        incidente_existente = self._incidentes_chat.get(chat_id, {})
        incidente_id = int(incidente_existente.get('id_incidente', 0) or 0)
        if not incidente_id:
            incidente_id = self.memoria_incidentes.abrir_incidente(
                chat_id=chat_id,
                lectura=lectura,
                resumen_alerta=AnalizadorTelemetria.resumir_alertas_confirmadas(lectura.get('alertas_confirmadas', [])),
            )
        self._incidentes_chat[chat_id] = {
            'id_incidente': incidente_id,
            'lectura': dict(lectura),
            'resultado_audio': dict(resultado),
            'timestamp': datetime.now().isoformat(),
        }
        self.memoria_incidentes.registrar_evento(
            id_incidente=incidente_id,
            tipo_evento='audio_operario',
            descripcion='El operario envio una nota de voz para actualizar el incidente.',
            payload={
                'intencion': resultado.get('intencion', 'OTRO'),
                'urgencia': resultado.get('nivel_urgencia', 'MEDIO'),
                'senal_resolucion': resultado.get('senal_resolucion', 'NO'),
            },
        )
        self.historial_operario.registrar_interaccion(
            chat_id=chat_id,
            tipo_entrada=evento_audio.get('tipo_entrada', 'audio'),
            mime_type=evento_audio.get('mime_type', 'audio/ogg'),
            duracion_seg=float(evento_audio.get('duracion_seg', 0.0)),
            audio_file_id=str(evento_audio.get('file_id', '')),
            id_planta=str(lectura.get('id_planta', '001')),
            id_maquina=str(lectura.get('id_maquina', '')),
            id_formula=str(lectura.get('id_formula', '')),
            codigo_producto=str(lectura.get('codigo_producto', '')),
            transcripcion=resultado.get('transcripcion', ''),
            intencion=resultado.get('intencion', 'OTRO'),
            accion_detectada=resultado.get('accion_detectada', ''),
            resumen_operario=resultado.get('resumen_operario', ''),
            nivel_urgencia=resultado.get('nivel_urgencia', 'MEDIO'),
        )

        senal_resolucion = str(resultado.get('senal_resolucion', 'NO')).strip().upper() == 'SI'
        if senal_resolucion:
            estado_monitoreo = "Cierre detectado. Generando ficha de incidente antes de reanudar monitoreo."
        else:
            self._pausar_chat_operario(
                chat_id,
                motivo=resultado.get('intencion', 'OTRO'),
            )
            estado_monitoreo = "Envio automatico pausado hasta que reportes solucion del problema."

        respuesta = (
            f"<b>Maria</b>\n"
            f"{html.escape(resultado.get('respuesta_asistente') or resultado.get('resumen_operario', 'Sin novedades relevantes.'))}\n"
            f"<b>Intencion:</b> {html.escape(resultado.get('intencion', 'OTRO'))} | "
            f"<b>Urgencia:</b> {html.escape(resultado.get('nivel_urgencia', 'MEDIO'))}\n"
            f"<i>{html.escape(estado_monitoreo)}</i>"
        )
        await self.telegram.enviar_mensaje_simple(chat_id, respuesta)

        # Registrar en historial de conversación para memoria dentro del incidente
        self._registrar_en_historial(chat_id, 'operario', resultado.get('transcripcion', '(audio)'))
        self._registrar_en_historial(chat_id, 'maria', resultado.get('respuesta_asistente', ''))

        self.memoria_incidentes.registrar_evento(
            id_incidente=incidente_id,
            tipo_evento='respuesta_maria',
            descripcion='Maria respondio al operario con apoyo operativo.',
            payload={
                'respuesta': resultado.get('respuesta_asistente', ''),
                'senal_resolucion': resultado.get('senal_resolucion', 'NO'),
            },
        )
        if senal_resolucion:
            cierre_ok = await self._enviar_ficha_cierre_incidente(chat_id)
            if cierre_ok:
                self._reanudar_chat_operario(chat_id)
                self._limpiar_historial_chat(chat_id)
                self.memoria_incidentes.registrar_evento(
                    id_incidente=incidente_id,
                    tipo_evento='monitoreo_reanudado',
                    descripcion='El monitoreo automatico fue reanudado tras cierre por audio.',
                )
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "Monitoreo automatico reanudado. La ficha de cierre ya fue enviada.",
                )
            else:
                await self.telegram.enviar_mensaje_simple(
                    chat_id,
                    "No pude generar aun la ficha de cierre. El sistema sigue en espera.",
                )
        else:
            self.memoria_incidentes.registrar_evento(
                id_incidente=incidente_id,
                tipo_evento='espera_confirmacion',
                descripcion='El sistema queda pausado esperando confirmacion de solucion.',
            )
            await self.telegram.enviar_confirmacion_solucion(
                chat_id,
                "Confirma cuando la novedad quede atendida para reanudar los reportes.",
            )

    async def _procesar_texto_operario(self, evento_texto: dict[str, Any]) -> None:
        """Interpreta un mensaje de texto libre del operario (misma lógica que audio, sin STT)."""
        chat_id = int(evento_texto['chat_id'])
        texto_operario = evento_texto['texto']

        self._pausar_chat_operario(chat_id, motivo='texto_recibido')
        await self.telegram.enviar_mensaje_simple(
            chat_id,
            "Mensaje recibido. Procesando con Gemini.",
        )

        contexto = ConstructorPrompts.contexto_audio_operario(self._ultima_lectura_publicada)
        historial = self._construir_bloque_historial(chat_id)
        if historial:
            contexto = f"{contexto}\n\n{historial}"
        try:
            resultado = await asyncio.wait_for(
                asyncio.to_thread(
                    self.llm.interpretar_texto_operario,
                    texto_operario=texto_operario,
                    prompt_texto=contexto,
                ),
                timeout=60,
            )
        except asyncio.TimeoutError:
            resultado = {
                'transcripcion': texto_operario,
                'intencion': 'OTRO',
                'accion_detectada': 'Timeout procesando el mensaje.',
                'resumen_operario': texto_operario,
                'nivel_urgencia': 'MEDIO',
                'respuesta_asistente': 'Tarde demasiado en procesar tu mensaje. Intenta de nuevo.',
                'senal_resolucion': 'NO',
            }

        # Reutilizar la misma lógica de incidentes que el audio
        lectura = self._ultima_lectura_publicada or {}
        incidente_existente = self._incidentes_chat.get(chat_id, {})
        incidente_id = int(incidente_existente.get('id_incidente', 0) or 0)
        if not incidente_id:
            incidente_id = self.memoria_incidentes.abrir_incidente(
                chat_id=chat_id,
                lectura=lectura,
                resumen_alerta=f"Texto del operario: {texto_operario[:200]}",
            )
            self._incidentes_chat[chat_id] = {
                'id_incidente': incidente_id,
                'lectura': lectura,
                'resultado_texto': resultado,
            }

        self.memoria_incidentes.registrar_evento(
            id_incidente=incidente_id,
            tipo_evento='texto_operario',
            descripcion=f"Texto: {texto_operario[:200]}",
        )

        # Determinar si el operario confirmó resolución
        senal = (resultado.get('senal_resolucion') or 'NO').upper().strip()
        estado_monitoreo = "Monitoreo normal activo."

        if senal != 'SI':
            self._pausar_chat_operario(chat_id, motivo=resultado.get('intencion', 'OTRO'))
            estado_monitoreo = "Envio automatico pausado hasta que reportes solucion del problema."

        respuesta = (
            f"<b>Maria</b>\n"
            f"{html.escape(resultado.get('respuesta_asistente') or resultado.get('resumen_operario', 'Sin novedades.'))}\n"
            f"<b>Intencion:</b> {html.escape(resultado.get('intencion', 'OTRO'))} | "
            f"<b>Urgencia:</b> {html.escape(resultado.get('nivel_urgencia', 'MEDIO'))}\n"
            f"<i>{html.escape(estado_monitoreo)}</i>"
        )
        await self.telegram.enviar_mensaje_simple(chat_id, respuesta)

        # Memoria de conversación
        self._registrar_en_historial(chat_id, 'operario', texto_operario)
        self._registrar_en_historial(chat_id, 'maria', resultado.get('respuesta_asistente', ''))

        if senal == 'SI':
            self.memoria_incidentes.registrar_evento(
                id_incidente=incidente_id,
                tipo_evento='resolucion_por_texto',
                descripcion='El operario confirmó resolución por texto.',
            )
            cierre_ok = await self._enviar_ficha_cierre_incidente(chat_id)
            if cierre_ok:
                self._reanudar_chat_operario(chat_id)
                self._limpiar_historial_chat(chat_id)
                await self.telegram.enviar_mensaje_simple(
                    chat_id, "Monitoreo automatico reanudado.")
        else:
            await self.telegram.enviar_confirmacion_solucion(
                chat_id,
                "Confirma cuando la novedad quede atendida para reanudar los reportes.",
            )

    async def _procesar_foto_operario(self, evento_foto: dict[str, Any]) -> None:
        """Interpreta una foto del operario usando Gemini multimodal."""
        chat_id = int(evento_foto['chat_id'])
        foto_bytes = evento_foto['foto_bytes']
        caption = evento_foto.get('caption', '')

        # Guardar foto para incluirla en llamadas futuras (audio/texto)
        self._ultima_foto_operario[chat_id] = foto_bytes

        self._pausar_chat_operario(chat_id, motivo='foto_recibida')
        await self.telegram.enviar_mensaje_simple(
            chat_id,
            "Foto recibida. Analizando imagen con Gemini.",
        )

        contexto = ConstructorPrompts.contexto_audio_operario(self._ultima_lectura_publicada)
        historial = self._construir_bloque_historial(chat_id)
        if historial:
            contexto = f"{contexto}\n\n{historial}"
        try:
            resultado = await asyncio.wait_for(
                asyncio.to_thread(
                    self.llm.interpretar_foto_operario,
                    foto_bytes=foto_bytes,
                    caption=caption,
                    prompt_texto=contexto,
                ),
                timeout=60,
            )
        except asyncio.TimeoutError:
            resultado = {
                'transcripcion': caption or 'Foto sin descripción',
                'intencion': 'OTRO',
                'accion_detectada': 'Timeout analizando la foto.',
                'resumen_operario': caption or 'El operario envió una foto.',
                'nivel_urgencia': 'MEDIO',
                'respuesta_asistente': 'Tarde demasiado analizando la foto. Describe lo que ves por texto.',
                'senal_resolucion': 'NO',
            }

        lectura = self._ultima_lectura_publicada or {}
        incidente_existente = self._incidentes_chat.get(chat_id, {})
        incidente_id = int(incidente_existente.get('id_incidente', 0) or 0)
        if not incidente_id:
            incidente_id = self.memoria_incidentes.abrir_incidente(
                chat_id=chat_id,
                lectura=lectura,
                resumen_alerta=f"Foto del operario. Caption: {caption[:200]}",
            )
            self._incidentes_chat[chat_id] = {
                'id_incidente': incidente_id,
                'lectura': lectura,
                'resultado_foto': resultado,
            }

        self.memoria_incidentes.registrar_evento(
            id_incidente=incidente_id,
            tipo_evento='foto_operario',
            descripcion=f"Foto recibida ({evento_foto.get('width', '?')}x{evento_foto.get('height', '?')}). Caption: {caption[:100]}",
        )

        senal = (resultado.get('senal_resolucion') or 'NO').upper().strip()
        estado_monitoreo = "Monitoreo normal activo."
        if senal != 'SI':
            self._pausar_chat_operario(chat_id, motivo=resultado.get('intencion', 'OTRO'))
            estado_monitoreo = "Envio automatico pausado hasta que reportes solucion del problema."

        respuesta = (
            f"<b>Maria</b>\n"
            f"{html.escape(resultado.get('respuesta_asistente') or 'Foto analizada.')}\n"
            f"<b>Hallazgo:</b> {html.escape(resultado.get('transcripcion', ''))}\n"
            f"<b>Intencion:</b> {html.escape(resultado.get('intencion', 'OTRO'))} | "
            f"<b>Urgencia:</b> {html.escape(resultado.get('nivel_urgencia', 'MEDIO'))}\n"
            f"<i>{html.escape(estado_monitoreo)}</i>"
        )
        await self.telegram.enviar_mensaje_simple(chat_id, respuesta)

        # Memoria de conversación
        desc_foto = f"(foto) {caption}" if caption else "(foto enviada)"
        self._registrar_en_historial(chat_id, 'operario', desc_foto)
        self._registrar_en_historial(chat_id, 'maria', resultado.get('respuesta_asistente', ''))

        if senal == 'SI':
            self.memoria_incidentes.registrar_evento(
                id_incidente=incidente_id,
                tipo_evento='resolucion_por_foto',
                descripcion='El operario confirmó resolución con evidencia fotográfica.',
            )
            cierre_ok = await self._enviar_ficha_cierre_incidente(chat_id)
            if cierre_ok:
                self._reanudar_chat_operario(chat_id)
                self._limpiar_historial_chat(chat_id)
                await self.telegram.enviar_mensaje_simple(chat_id, "Monitoreo automatico reanudado.")
        else:
            await self.telegram.enviar_confirmacion_solucion(
                chat_id,
                "Confirma cuando la novedad quede atendida para reanudar los reportes.",
            )

    async def _procesar_multimodal_unificado(self, chat_id: int, inputs: dict) -> None:
        """Procesa múltiples inputs del operario (audio+texto+foto) en UNA llamada a Gemini."""
        self._pausar_chat_operario(chat_id, motivo='multimodal_unificado')

        contexto = ConstructorPrompts.contexto_audio_operario(self._ultima_lectura_publicada)
        historial = self._construir_bloque_historial(chat_id)
        if historial:
            contexto = f"{contexto}\n\n{historial}"

        # Preparar listas para el método unificado del LLM
        audios_raw = [{'audio_bytes': a['audio_bytes'], 'mime_type': a.get('mime_type', 'audio/ogg')}
                      for a in inputs['audios']]
        textos_raw = [t['texto'] for t in inputs['textos']]
        fotos_raw  = [f['foto_bytes'] for f in inputs['fotos']]

        try:
            resultado = await asyncio.wait_for(
                asyncio.to_thread(
                    self.llm.interpretar_multimodal_unificado,
                    audios=audios_raw,
                    textos=textos_raw,
                    fotos=fotos_raw,
                    prompt_texto=contexto,
                ),
                timeout=90,
            )
        except asyncio.TimeoutError:
            n_total = len(audios_raw) + len(textos_raw) + len(fotos_raw)
            resultado = {
                'transcripcion': '; '.join(textos_raw[:3]) if textos_raw else '',
                'intencion': 'OTRO',
                'accion_detectada': f'Timeout procesando {n_total} inputs multimodales.',
                'resumen_operario': 'El operario envió múltiples mensajes.',
                'nivel_urgencia': 'MEDIO',
                'respuesta_asistente': 'Tarde demasiado procesando todos tus mensajes. Intenta enviar uno por uno.',
                'senal_resolucion': 'NO',
            }

        # Incidente
        lectura = self._ultima_lectura_publicada or {}
        incidente_existente = self._incidentes_chat.get(chat_id, {})
        incidente_id = int(incidente_existente.get('id_incidente', 0) or 0)
        if not incidente_id:
            incidente_id = self.memoria_incidentes.abrir_incidente(
                chat_id=chat_id,
                lectura=lectura,
                resumen_alerta=f'Input multimodal: {len(audios_raw)} audio(s), {len(textos_raw)} texto(s), {len(fotos_raw)} foto(s).',
            )
            self._incidentes_chat[chat_id] = {
                'id_incidente': incidente_id,
                'lectura': lectura,
                'resultado_multimodal': resultado,
            }

        self.memoria_incidentes.registrar_evento(
            id_incidente=incidente_id,
            tipo_evento='multimodal_unificado',
            descripcion=(
                f"Input unificado: {len(audios_raw)} audio(s), "
                f"{len(textos_raw)} texto(s), {len(fotos_raw)} foto(s). "
                f"Intención: {resultado.get('intencion', 'OTRO')}"
            ),
        )

        senal = (resultado.get('senal_resolucion') or 'NO').upper().strip()
        estado_monitoreo = "Monitoreo normal activo."
        if senal != 'SI':
            self._pausar_chat_operario(chat_id, motivo=resultado.get('intencion', 'OTRO'))
            estado_monitoreo = "Envio automatico pausado hasta que reportes solucion del problema."

        respuesta = (
            f"<b>Maria</b>\n"
            f"{html.escape(resultado.get('respuesta_asistente') or 'Mensajes procesados.')}\n"
            f"<b>Intencion:</b> {html.escape(resultado.get('intencion', 'OTRO'))} | "
            f"<b>Urgencia:</b> {html.escape(resultado.get('nivel_urgencia', 'MEDIO'))}\n"
            f"<i>{html.escape(estado_monitoreo)}</i>"
        )
        await self.telegram.enviar_mensaje_simple(chat_id, respuesta)

        # Memoria de conversación
        resumen_inputs = "; ".join(textos_raw[:2]) if textos_raw else "(audio+foto)"
        self._registrar_en_historial(chat_id, 'operario', resumen_inputs)
        self._registrar_en_historial(chat_id, 'maria', resultado.get('respuesta_asistente', ''))

        if senal == 'SI':
            self.memoria_incidentes.registrar_evento(
                id_incidente=incidente_id,
                tipo_evento='resolucion_multimodal',
                descripcion='Operario confirmó resolución via inputs multimodales.',
            )
            cierre_ok = await self._enviar_ficha_cierre_incidente(chat_id)
            if cierre_ok:
                self._reanudar_chat_operario(chat_id)
                await self.telegram.enviar_mensaje_simple(chat_id, "Monitoreo automatico reanudado.")
        else:
            await self.telegram.enviar_confirmacion_solucion(
                chat_id,
                "Confirma cuando la novedad quede atendida para reanudar los reportes.",
            )

    def _registrar_en_historial(self, chat_id: int, rol: str, contenido: str) -> None:
        """Agrega un mensaje al historial de conversación del chat."""
        if chat_id not in self._historial_conversacion:
            self._historial_conversacion[chat_id] = []
        self._historial_conversacion[chat_id].append({
            'rol': rol,
            'contenido': contenido[:500],  # limitar para no explotar el contexto
        })
        # Mantener máximo 20 intercambios (10 pares operario-María)
        if len(self._historial_conversacion[chat_id]) > 20:
            self._historial_conversacion[chat_id] = self._historial_conversacion[chat_id][-20:]

    def _construir_bloque_historial(self, chat_id: int) -> str:
        """Construye el bloque de historial de conversación para el prompt."""
        historial = self._historial_conversacion.get(chat_id, [])
        if not historial:
            return ""
        lineas = ["=== HISTORIAL DE CONVERSACION CON ESTE OPERARIO (mismo incidente) ==="]
        for msg in historial:
            prefijo = "OPERARIO" if msg['rol'] == 'operario' else "MARIA"
            lineas.append(f"{prefijo}: {msg['contenido']}")
        lineas.append("=== FIN HISTORIAL ===")
        lineas.append("IMPORTANTE: Usa este historial para dar continuidad. NO repitas lo que ya dijiste. NO pidas informacion que el operario ya te dio.")
        return "\n".join(lineas)

    def _limpiar_historial_chat(self, chat_id: int) -> None:
        """Persiste la conversación al historial general y luego limpia la memoria."""
        historial = self._historial_conversacion.get(chat_id, [])
        if historial:
            self._persistir_conversacion(chat_id, historial)
        self._historial_conversacion.pop(chat_id, None)

    def _persistir_conversacion(self, chat_id: int, historial: list[dict]) -> None:
        """Guarda la conversación completa en CSV para RAG/RLHF futuro."""
        import csv
        from datetime import datetime

        archivo = os.path.join(self.config.data_dir, 'historial_conversaciones.csv')
        existe = os.path.exists(archivo)

        incidente_info = self._incidentes_chat.get(chat_id, {})
        incidente_id = incidente_info.get('id_incidente', 0)
        lectura = incidente_info.get('lectura', {})

        try:
            with open(archivo, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not existe:
                    writer.writerow([
                        'timestamp', 'incidente_id', 'chat_id',
                        'id_maquina', 'id_formula', 'turno',
                        'rol', 'contenido', 'n_mensajes_total',
                    ])
                n_total = len(historial)
                for msg in historial:
                    writer.writerow([
                        datetime.now().isoformat(),
                        incidente_id,
                        chat_id,
                        lectura.get('id_maquina', ''),
                        lectura.get('id_formula', ''),
                        len(historial) // 2,  # pares de intercambio
                        msg['rol'],
                        msg['contenido'],
                        n_total,
                    ])
            logger.info(
                "[MEMORIA] Conversación persistida — incidente=%s | %d mensajes | archivo=%s",
                incidente_id, len(historial), archivo,
            )
        except Exception as e:
            logger.error("[MEMORIA] Error persistiendo conversación: %s", e)

    def _chat_pausado(self, chat_id: int) -> bool:
        """Indica si un chat de operario tiene el flujo automatico pausado."""
        return chat_id in self._chats_pausados_operacion

    def _flujo_telemetria_bloqueado(self) -> bool:
        """Bloquea nuevas lecturas mientras haya incidentes activos o cierres pendientes."""
        return bool(self._chats_pausados_operacion or self._incidentes_chat)

    def _pausar_chat_operario(self, chat_id: int, motivo: str) -> None:
        """Marca un chat como pausado mientras el operario atiende la novedad."""
        self._chats_pausados_operacion[chat_id] = {
            'timestamp': datetime.now(),
            'motivo': str(motivo or 'sin_detalle'),
        }

    def _reanudar_chat_operario(self, chat_id: int) -> None:
        """Reanuda el flujo automatico para un chat de operario."""
        self._chats_pausados_operacion.pop(chat_id, None)
        self._limpiar_historial_chat(chat_id)

    async def _enviar_ficha_cierre_incidente(self, chat_id_origen: int) -> bool:
        """Genera una ficha de cierre para gerencia cuando el operario confirma solucion."""
        incidente = self._incidentes_chat.get(chat_id_origen)
        if not incidente or self._ultimo_panel_bytes is None:
            return False

        lectura = incidente.get('lectura') or self._ultima_lectura_publicada
        resultado_audio = incidente.get('resultado_audio', {})
        id_incidente = int(incidente.get('id_incidente', 0) or 0)
        if not lectura:
            return False

        prompt = ConstructorPrompts.prompt_ficha_cierre(
            lectura=lectura,
            resultado_audio=resultado_audio,
        )
        imagen_ia, texto_ia = self.nano_banana.generar_ficha_visual(
            prompt_texto=prompt,
            imagen_referencia_bytes=self._ultimo_panel_bytes,
        )
        if imagen_ia is None:
            if id_incidente:
                self.memoria_incidentes.registrar_evento(
                    id_incidente=id_incidente,
                    tipo_evento='ficha_fallida',
                    descripcion='La ficha IA de cierre no pudo generarse.',
                    payload={'detalle': texto_ia},
                )
            logger.warning("No fue posible generar ficha de cierre gerencial: %s", texto_ia)
            return False

        chats_destino = self._obtener_chats_gerenciales(str(lectura.get('id_maquina', '')))
        if chat_id_origen not in chats_destino:
            chats_destino.append(chat_id_origen)

        for chat_id in chats_destino:
            enviado = await self.telegram.enviar_imagen(
                chat_id,
                imagen_ia,
                caption="Ficha IA de cierre de incidente",
            )
            if not enviado:
                if id_incidente:
                    self.memoria_incidentes.registrar_evento(
                        id_incidente=id_incidente,
                        tipo_evento='envio_ficha_fallido',
                        descripcion='No fue posible enviar la ficha de cierre por Telegram.',
                        payload={'chat_id': chat_id},
                    )
                logger.warning("No fue posible enviar ficha de cierre a chat_id=%d", chat_id)
                return False
            await asyncio.sleep(1)

        correo_ok = self.email_service.enviar_cierre_incidente(
            lectura=lectura,
            resultado_audio=resultado_audio,
            imagen_png=imagen_ia,
        )
        if not correo_ok:
            if id_incidente:
                self.memoria_incidentes.registrar_evento(
                    id_incidente=id_incidente,
                    tipo_evento='correo_fallido',
                    descripcion='La ficha se genero, pero el correo al supervisor no pudo enviarse.',
                )
            logger.warning("La ficha de cierre no pudo enviarse por correo al supervisor.")
            return False

        if id_incidente:
            self.memoria_incidentes.registrar_evento(
                id_incidente=id_incidente,
                tipo_evento='ficha_y_correo_enviados',
                descripcion='La ficha de cierre fue enviada por Telegram y correo al supervisor.',
                payload={'nota_nano_banana': texto_ia},
            )
            self.memoria_incidentes.cerrar_incidente(
                id_incidente=id_incidente,
                resultado_audio=resultado_audio,
                ficha_generada=True,
                correo_enviado=True,
                monitoreo_reanudado=True,
            )

        self._incidentes_chat.pop(chat_id_origen, None)
        return True

    def _obtener_chats_gerenciales(self, id_maquina: str) -> list[int]:
        """En esta version el cierre visual se comparte solo al chat del operario."""
        return []










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
        video_bytes: Optional[bytes] = None,
    ) -> str:
        """Obtiene la prescripcion multimodal de Maria con fallback determinista."""
        prompt = ConstructorPrompts.prompt_llm_operativo(
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
        # Inyectar bloque enriquecido del Feature Store (Capa 4).
        # Contiene: tasa de cambio, tendencia, correlaciones, matriz 3x3
        # y anomalia global para que Gemini razone sobre la dinamica temporal.
        bloque_features = self.feature_store.construir_bloque_prompt()
        if bloque_features:
            prompt = f"{prompt}\n\n{bloque_features}"
        try:
            # Loop agentico con few-shot dinámico desde feedback real del operario.
            # ShadowTester despacha al modo configurado (off / shadow / ab):
            #   off    → llama solo a la variante A (sin overhead)
            #   shadow → corre A y B en paralelo; el operario solo ve A
            #   ab     → sortea según SHADOW_PORCENTAJE_B qué variante ve el operario
            # La variante asignada se registra en shadow_log.csv para análisis posterior.
            id_maquina = str(lectura.get("id_maquina", ""))
            variable   = lectura.get("variable_principal", "")
            alerta_id  = int(lectura.get("numero_orden", 0) or 0)

            prescripcion, variante = self.shadow_tester.generar_con_shadow(
                prompt_texto=prompt,
                herramientas=self.herramientas,
                imagen_bytes=imagen_bytes,
                video_bytes=video_bytes,
                feedback_loop=self.feedback_loop,
                id_maquina=id_maquina,
                variable=variable,
                alerta_id=alerta_id,
            )
            prescripcion = AnalizadorTelemetria.limpiar_texto_llm(prescripcion)
            if prescripcion:
                logger.debug(
                    "[A/B] Prescripción generada con variante %s | Máq: %s | Var: %s",
                    variante, id_maquina, variable,
                )
                return prescripcion
        except Exception as e:
            logger.error("Fallo en loop agentico de Maria: %s", e, exc_info=True)
        return diagnostico_operativo

    def _calcular_predictor_incidente(
        self,
        *,
        id_maquina: str,
        causa_probable: str,
        severidad: str,
        pronostico_nivel: str,
        estado_temperatura: str,
        estado_presion: str,
        porcentaje_carga: float,
    ) -> dict[str, Any]:
        """Score simple de recurrencia basado en estado actual e historial reciente."""
        score = 10
        score += {
            'INFORMATIVA': 0,
            'PREVENTIVA': 12,
            'ALTA': 24,
            'CRITICA': 34,
        }.get(severidad, 0)
        score += {
            'BAJO': 0,
            'MEDIO': 18,
            'ALTO': 30,
        }.get(pronostico_nivel, 0)

        if estado_temperatura != 'NORMAL':
            score += 12
        if estado_presion != 'NORMAL':
            score += 12
        if porcentaje_carga >= 90:
            score += 10

        contexto_memoria = self.memoria_incidentes.obtener_contexto_predictivo(
            id_maquina=id_maquina,
            causa_probable=causa_probable,
            ventana_horas=24,
        )
        score += min(int(contexto_memoria.get('recientes_maquina', 0)) * 8, 16)
        score += min(int(contexto_memoria.get('similares', 0)) * 10, 20)
        score = max(0, min(100, score))

        if score >= 75:
            nivel = 'ALTO'
        elif score >= 45:
            nivel = 'MEDIO'
        else:
            nivel = 'BAJO'

        mensaje = (
            f"Riesgo {nivel.lower()} de recurrencia: "
            f"{int(contexto_memoria.get('recientes_maquina', 0))} incidente(s) reciente(s) en maquina {id_maquina} "
            f"y {int(contexto_memoria.get('similares', 0))} caso(s) con causa similar en 24 h."
        )
        return {
            'score': int(score),
            'nivel': nivel,
            'mensaje': mensaje,
            'recientes_maquina': int(contexto_memoria.get('recientes_maquina', 0)),
            'similares': int(contexto_memoria.get('similares', 0)),
        }

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
