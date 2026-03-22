"""
Modulo de notificaciones por Telegram.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class NotificadorBase(ABC):
    """Interfaz base para notificaciones."""

    @abstractmethod
    async def enviar_alerta_texto(
        self, chat_id: int, texto_alerta: str, alerta_id: int
    ) -> bool:
        ...

    @abstractmethod
    async def enviar_mensaje_simple(self, chat_id: int, texto: str) -> bool:
        ...

    @abstractmethod
    async def enviar_mensaje_con_boton_pdf(
        self,
        chat_id: int,
        texto: str,
        alerta_id: Optional[int] = None,
        audiencia: str = 'operario',
    ) -> bool:
        ...

    @abstractmethod
    async def enviar_audio(self, chat_id: int, audio_bytes: bytes) -> bool:
        ...

    @abstractmethod
    async def enviar_confirmacion_solucion(self, chat_id: int, texto: str) -> bool:
        ...

    @abstractmethod
    async def enviar_pdf(self, chat_id: int, pdf_bytes: bytes, nombre: str) -> bool:
        ...

    @abstractmethod
    async def enviar_documento(
        self,
        chat_id: int,
        contenido: bytes,
        nombre: str,
        caption: str,
    ) -> bool:
        ...


class TelegramNotificador(NotificadorBase):
    """Implementacion de Telegram."""

    REGISTRO_ARCHIVO = 'registro_usuarios.json'

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()
        self.token = self.config.telegram_bot_token
        self._usuarios_registrados: dict[str, int] = {}
        self._registro_path = self.config.data_dir / self.REGISTRO_ARCHIVO
        self._ultimo_update_id: Optional[int] = None
        self._polling_inicializado = False
        self._cargar_registros()
        logger.info(
            "TelegramNotificador inicializado. %d usuarios registrados.",
            len(self._usuarios_registrados),
        )

    def _cargar_registros(self) -> None:
        if self._registro_path.exists():
            try:
                with open(self._registro_path, 'r', encoding='utf-8') as f:
                    self._usuarios_registrados = json.load(f)
            except Exception as e:
                logger.error("Error cargando registros: %s", e)
                self._usuarios_registrados = {}

    def _guardar_registros(self) -> None:
        try:
            with open(self._registro_path, 'w', encoding='utf-8') as f:
                json.dump(self._usuarios_registrados, f, indent=2)
        except Exception as e:
            logger.error("Error guardando registros: %s", e)

    def registrar_usuario(self, numero_celular: str, chat_id: int) -> None:
        self._usuarios_registrados[numero_celular] = chat_id
        self._guardar_registros()
        logger.info("Usuario registrado: %s -> chat_id=%d", numero_celular, chat_id)

    def obtener_chat_id(self, numero_celular: str) -> Optional[int]:
        celular = numero_celular.strip()
        chat_id = self._usuarios_registrados.get(celular)
        if chat_id is None:
            chat_id = self._usuarios_registrados.get(celular.lstrip('+'))
        if chat_id is None:
            chat_id = self._usuarios_registrados.get('+' + celular.lstrip('+'))
        return chat_id

    async def _obtener_bot(self):
        from telegram import Bot
        return Bot(token=self.token)

    async def enviar_alerta_texto(
        self, chat_id: int, texto_alerta: str, alerta_id: int
    ) -> bool:
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            bot = await self._obtener_bot()
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Util y Aplicado", callback_data=f"feedback:{alerta_id}:UTIL")],
                [InlineKeyboardButton("Falso Positivo", callback_data=f"feedback:{alerta_id}:FALSO_POSITIVO")],
                [InlineKeyboardButton("Falla Mecanica", callback_data=f"feedback:{alerta_id}:FALLA_MECANICA")],
            ])

            await bot.send_message(
                chat_id=chat_id,
                text=texto_alerta,
                parse_mode='HTML',
                reply_markup=keyboard,
            )
            logger.info("Alerta texto enviada: chat_id=%d, alerta_id=%d", chat_id, alerta_id)
            return True
        except Exception as e:
            logger.error("Error enviando alerta texto a chat_id=%d: %s", chat_id, e)
            return False

    async def enviar_mensaje_simple(self, chat_id: int, texto: str) -> bool:
        try:
            bot = await self._obtener_bot()
            await bot.send_message(chat_id=chat_id, text=texto, parse_mode='HTML')
            logger.info("Mensaje simple enviado: chat_id=%d", chat_id)
            return True
        except Exception as e:
            logger.error("Error enviando mensaje simple a chat_id=%d: %s", chat_id, e)
            return False

    async def enviar_mensaje_con_boton_pdf(
        self,
        chat_id: int,
        texto: str,
        alerta_id: Optional[int] = None,
        audiencia: str = 'operario',
    ) -> bool:
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            bot = await self._obtener_bot()
            filas = []

            if audiencia == 'gerencial':
                filas = [[
                    InlineKeyboardButton("Solicitar PDF", callback_data="solicitar_pdf"),
                    InlineKeyboardButton("Solicitar Dashboard", callback_data="solicitar_dashboard"),
                ]]
                filas.append([
                    InlineKeyboardButton("Ficha Gerencial", callback_data="solicitar_ficha_gerencial"),
                    InlineKeyboardButton("Explicar evento", callback_data="explicar_evento"),
                ])
                filas.append([
                    InlineKeyboardButton("Ficha Operario", callback_data="solicitar_ficha_operario"),
                ])

            if alerta_id is not None and audiencia != 'gerencial':
                filas.append([
                    InlineKeyboardButton("Util", callback_data=f"feedback:{alerta_id}:UTIL"),
                    InlineKeyboardButton("Falso positivo", callback_data=f"feedback:{alerta_id}:FALSO_POSITIVO"),
                ])
                filas.append([
                    InlineKeyboardButton("Mantenimiento", callback_data=f"feedback:{alerta_id}:FALLA_MECANICA"),
                ])
            teclado = InlineKeyboardMarkup(filas) if filas else None
            await bot.send_message(
                chat_id=chat_id,
                text=texto,
                parse_mode='HTML',
                reply_markup=teclado,
            )
            logger.info("Mensaje con boton PDF enviado: chat_id=%d", chat_id)
            return True
        except Exception as e:
            logger.error(
                "Error enviando mensaje con boton PDF a chat_id=%d: %s",
                chat_id,
                e,
            )
            return False

    async def enviar_audio(self, chat_id: int, audio_bytes: bytes) -> bool:
        try:
            import io

            bot = await self._obtener_bot()
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = 'lectura.mp3'
            audio_file.seek(0)

            await bot.send_audio(
                chat_id=chat_id,
                audio=audio_file,
                title="Lectura de proceso",
                caption="Audio de temperatura y presion",
            )
            logger.info(
                "Audio enviado: chat_id=%d, %.1f KB",
                chat_id,
                len(audio_bytes) / 1024,
            )
            return True
        except Exception as e:
            logger.error("Error enviando audio a chat_id=%d: %s", chat_id, e)
            return False

    async def enviar_confirmacion_solucion(self, chat_id: int, texto: str) -> bool:
        """Pregunta al operario si la novedad ya fue solucionada."""
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            bot = await self._obtener_bot()
            teclado = InlineKeyboardMarkup([[
                InlineKeyboardButton("Si, solucionado", callback_data="resolver_operacion:SI"),
                InlineKeyboardButton("No, continua", callback_data="resolver_operacion:NO"),
            ]])
            await bot.send_message(
                chat_id=chat_id,
                text=texto,
                parse_mode='HTML',
                reply_markup=teclado,
            )
            logger.info("Confirmacion de solucion enviada: chat_id=%d", chat_id)
            return True
        except Exception as e:
            logger.error("Error enviando confirmacion de solucion a chat_id=%d: %s", chat_id, e)
            return False

    async def enviar_imagen(
        self, chat_id: int, imagen_bytes: bytes, caption: str = ""
    ) -> bool:
        try:
            import io

            bot = await self._obtener_bot()
            imagen_file = io.BytesIO(imagen_bytes)
            imagen_file.name = 'grafica_monitoreo.png'
            imagen_file.seek(0)

            await bot.send_photo(
                chat_id=chat_id,
                photo=imagen_file,
                caption=caption or "Grafica de monitoreo",
            )
            logger.info(
                "Imagen enviada: chat_id=%d, %.1f KB",
                chat_id,
                len(imagen_bytes) / 1024,
            )
            return True
        except Exception as e:
            logger.error("Error enviando imagen a chat_id=%d: %s", chat_id, e)
            return False

    async def enviar_pdf(
        self, chat_id: int, pdf_bytes: bytes, nombre: str
    ) -> bool:
        return await self.enviar_documento(
            chat_id=chat_id,
            contenido=pdf_bytes,
            nombre=nombre,
            caption="Reporte PDF de planta 001",
        )

    async def enviar_documento(
        self,
        chat_id: int,
        contenido: bytes,
        nombre: str,
        caption: str,
    ) -> bool:
        try:
            import io

            bot = await self._obtener_bot()
            doc_file = io.BytesIO(contenido)
            doc_file.name = nombre
            doc_file.seek(0)

            await bot.send_document(
                chat_id=chat_id,
                document=doc_file,
                caption=caption,
            )
            logger.info(
                "Documento enviado: chat_id=%d, archivo=%s, %.1f KB",
                chat_id,
                nombre,
                len(contenido) / 1024,
            )
            return True
        except Exception as e:
            logger.error("Error enviando documento a chat_id=%d: %s", chat_id, e)
            return False

    async def _descargar_archivo(self, file_id: str) -> bytes:
        """Descarga un archivo enviado al bot y lo devuelve en memoria."""
        bot = await self._obtener_bot()
        archivo = await bot.get_file(file_id)
        contenido = await archivo.download_as_bytearray()
        return bytes(contenido)

    async def obtener_eventos_chat(self) -> dict[str, list]:
        """Lee mensajes recientes y devuelve solicitudes del chat."""
        try:
            bot = await self._obtener_bot()
            updates = await bot.get_updates(
                offset=self._ultimo_update_id,
                timeout=0,
                allowed_updates=["message", "callback_query"],
            )
        except Exception as e:
            logger.error("Error consultando solicitudes de PDF: %s", e)
            return {
                'pdf': [],
                'dashboard': [],
                'ficha_operario': [],
                'ficha_gerencial': [],
                'explicar_evento': [],
                'audio_operario': [],
                'feedback': [],
                'resolver_operacion': [],
            }

        if not self._polling_inicializado:
            if updates:
                self._ultimo_update_id = updates[-1].update_id + 1
            self._polling_inicializado = True
            return {
                'pdf': [],
                'dashboard': [],
                'ficha_operario': [],
                'ficha_gerencial': [],
                'explicar_evento': [],
                'audio_operario': [],
                'feedback': [],
                'resolver_operacion': [],
            }

        eventos = {
            'pdf': [],
            'dashboard': [],
            'ficha_operario': [],
            'ficha_gerencial': [],
            'explicar_evento': [],
            'audio_operario': [],
            'feedback': [],
            'resolver_operacion': [],
        }
        for update in updates:
            self._ultimo_update_id = update.update_id + 1
            message = getattr(update, 'message', None)
            callback_query = getattr(update, 'callback_query', None)

            if callback_query is not None:
                try:
                    texto_respuesta = "Solicitud recibida"
                    if isinstance(callback_query.data, str) and callback_query.data.startswith('feedback:'):
                        texto_respuesta = "Feedback recibido"
                    elif isinstance(callback_query.data, str) and callback_query.data.startswith('resolver_operacion:'):
                        texto_respuesta = "Confirmacion recibida"
                    await bot.answer_callback_query(
                        callback_query_id=callback_query.id,
                        text=texto_respuesta,
                    )
                except Exception as e:
                    logger.error("Error respondiendo callback de PDF: %s", e)

                if callback_query.data == 'solicitar_pdf':
                    chat_id = callback_query.message.chat_id
                    if chat_id not in eventos['pdf']:
                        eventos['pdf'].append(chat_id)
                elif callback_query.data == 'solicitar_dashboard':
                    chat_id = callback_query.message.chat_id
                    if chat_id not in eventos['dashboard']:
                        eventos['dashboard'].append(chat_id)
                elif callback_query.data == 'solicitar_ficha_operario':
                    chat_id = callback_query.message.chat_id
                    if chat_id not in eventos['ficha_operario']:
                        eventos['ficha_operario'].append(chat_id)
                elif callback_query.data == 'solicitar_ficha_gerencial':
                    chat_id = callback_query.message.chat_id
                    if chat_id not in eventos['ficha_gerencial']:
                        eventos['ficha_gerencial'].append(chat_id)
                elif callback_query.data == 'explicar_evento':
                    chat_id = callback_query.message.chat_id
                    if chat_id not in eventos['explicar_evento']:
                        eventos['explicar_evento'].append(chat_id)
                elif callback_query.data.startswith('feedback:'):
                    try:
                        _, alerta_id, feedback = callback_query.data.split(':', 2)
                        eventos['feedback'].append(
                            (callback_query.message.chat_id, int(alerta_id), feedback)
                        )
                    except Exception as e:
                        logger.error("Callback de feedback invalido: %s", e)
                elif callback_query.data.startswith('resolver_operacion:'):
                    try:
                        _, estado = callback_query.data.split(':', 1)
                        eventos['resolver_operacion'].append(
                            (callback_query.message.chat_id, estado.strip().upper())
                        )
                    except Exception as e:
                        logger.error("Callback de resolucion invalido: %s", e)
                continue

            if message is None:
                continue

            if getattr(message, 'voice', None) is not None:
                try:
                    voice = message.voice
                    eventos['audio_operario'].append({
                        'chat_id': message.chat_id,
                        'audio_bytes': await self._descargar_archivo(voice.file_id),
                        'mime_type': voice.mime_type or 'audio/ogg',
                        'duracion_seg': float(voice.duration or 0),
                        'file_id': voice.file_id,
                        'tipo_entrada': 'voice',
                    })
                except Exception as e:
                    logger.error("Error descargando nota de voz del operario: %s", e)
                continue

            if getattr(message, 'audio', None) is not None:
                try:
                    audio = message.audio
                    eventos['audio_operario'].append({
                        'chat_id': message.chat_id,
                        'audio_bytes': await self._descargar_archivo(audio.file_id),
                        'mime_type': audio.mime_type or 'audio/mpeg',
                        'duracion_seg': float(audio.duration or 0),
                        'file_id': audio.file_id,
                        'tipo_entrada': 'audio',
                    })
                except Exception as e:
                    logger.error("Error descargando audio del operario: %s", e)
                continue

            if message.text is None:
                continue

            texto = message.text.strip().lower()
            if texto in {'solicitar pdf', '/pdf', 'pdf'}:
                chat_id = message.chat_id
                if chat_id not in eventos['pdf']:
                    eventos['pdf'].append(chat_id)
            if texto in {'solicitar dashboard', '/dashboard', 'dashboard'}:
                chat_id = message.chat_id
                if chat_id not in eventos['dashboard']:
                    eventos['dashboard'].append(chat_id)
            if texto in {'solicitar ficha operario', '/ficha_operario', 'ficha operario'}:
                chat_id = message.chat_id
                if chat_id not in eventos['ficha_operario']:
                    eventos['ficha_operario'].append(chat_id)
            if texto in {'solicitar ficha gerencial', '/ficha_gerencial', 'ficha gerencial'}:
                chat_id = message.chat_id
                if chat_id not in eventos['ficha_gerencial']:
                    eventos['ficha_gerencial'].append(chat_id)
            if texto in {'explicar evento', '/explicar_evento', 'explicar'}:
                chat_id = message.chat_id
                if chat_id not in eventos['explicar_evento']:
                    eventos['explicar_evento'].append(chat_id)

        return eventos


def formatear_alerta_html(
    tipo_alerta: str,
    id_planta: str,
    id_maquina: str,
    id_formula: str,
    codigo_producto: str,
    variable: str,
    valor_suavizado: float,
    limite_violado: float,
    limite_min: float,
    limite_max: float,
    porcentaje_carga: float,
    timestamp: datetime,
    es_retorno_normal: bool = False,
) -> str:
    """Mantiene compatibilidad con el formato anterior de alertas."""
    nombres = {
        'presion_vapor': 'Presion de Vapor',
        'temp_acond': 'Temperatura Acondicionador',
    }
    nombre_var = nombres.get(variable, variable)
    hora = timestamp.strftime('%H:%M:%S')
    fecha = timestamp.strftime('%Y-%m-%d')

    if es_retorno_normal:
        return (
            f"<b>PROCESO ESTABLE</b>\n"
            f"Planta <b>{id_planta}</b> | Maq <b>{id_maquina}</b>\n"
            f"Formula {id_formula} ({codigo_producto})\n"
            f"{nombre_var} retorno a banda normal\n"
            f"Banda: [{limite_min:.1f} - {limite_max:.1f}]\n"
            f"Valor actual (EMA): <b>{valor_suavizado:.2f}</b>\n"
            f"Carga: {porcentaje_carga:.0f}%\n"
            f"{fecha} {hora}\n"
        )

    return (
        f"<b>ALERTA: {tipo_alerta.replace('_', ' ')}</b>\n"
        f"Planta <b>{id_planta}</b> | Maq <b>{id_maquina}</b>\n"
        f"Formula {id_formula} ({codigo_producto})\n"
        f"<b>{nombre_var}</b>\n"
        f"Valor suavizado (EMA): <b>{valor_suavizado:.2f}</b>\n"
        f"Limite violado: <b>{limite_violado:.1f}</b>\n"
        f"Banda permitida: [{limite_min:.1f} - {limite_max:.1f}]\n"
        f"Carga del motor: {porcentaje_carga:.0f}%\n"
        f"{fecha} {hora}"
    )
