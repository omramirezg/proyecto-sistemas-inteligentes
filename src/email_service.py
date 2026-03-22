"""
Servicio de correo para enviar cierres ejecutivos de incidentes.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class EmailService:
    """Envio simple de correos SMTP para resumen ejecutivo de incidentes."""

    def __init__(self, config: Optional[ConfigLoader] = None) -> None:
        self.config = config or ConfigLoader()

    def esta_configurado(self) -> bool:
        """Indica si el envio de correo tiene la configuracion minima."""
        return bool(
            self.config.smtp_host
            and self.config.smtp_user
            and self.config.smtp_password
            and self.config.supervisor_emails
        )

    def enviar_cierre_incidente(
        self,
        *,
        lectura: dict,
        resultado_audio: dict,
        imagen_png: bytes,
    ) -> bool:
        """Envia al supervisor la ficha de cierre con resumen ejecutivo."""
        if not self.esta_configurado():
            logger.warning("Servicio de correo no configurado. Falta SMTP o destinatarios.")
            return False

        asunto = (
            f"Cierre de incidente | Planta {lectura.get('id_planta', '001')} | "
            f"Maquina {lectura.get('id_maquina', '')}"
        )

        cuerpo_texto = (
            f"Cierre de incidente operativo\n\n"
            f"Planta: {lectura.get('id_planta', '001')}\n"
            f"Maquina: {lectura.get('id_maquina', '')}\n"
            f"Formula: {lectura.get('id_formula', '')} ({lectura.get('codigo_producto', '')})\n"
            f"Estado final: {lectura.get('estado_global', '')}\n"
            f"Severidad: {lectura.get('severidad', '')}\n"
            f"Temperatura EMA: {lectura.get('temp_ema', 0):.1f} C\n"
            f"Presion EMA: {lectura.get('presion_ema', 0):.1f} PSI\n"
            f"Carga: {lectura.get('porcentaje_carga', 0):.1f}%\n"
            f"Causa probable: {lectura.get('causa_probable', '')}\n"
            f"Reporte del operario: {resultado_audio.get('resumen_operario', '')}\n"
            f"Accion reportada: {resultado_audio.get('accion_detectada', '')}\n"
            f"Respuesta de Maria: {resultado_audio.get('respuesta_asistente', '')}\n"
            f"Monitoreo: reanudado tras cierre del incidente.\n"
        )

        cuerpo_html = f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #1f2937;">
    <h2 style="color: #0f4c81;">Cierre de incidente operativo</h2>
    <p><b>Planta:</b> {lectura.get('id_planta', '001')}<br>
    <b>Maquina:</b> {lectura.get('id_maquina', '')}<br>
    <b>Formula:</b> {lectura.get('id_formula', '')} ({lectura.get('codigo_producto', '')})</p>

    <p><b>Estado final:</b> {lectura.get('estado_global', '')}<br>
    <b>Severidad:</b> {lectura.get('severidad', '')}<br>
    <b>Salud del proceso:</b> {lectura.get('indice_salud', '')}/100 ({lectura.get('etiqueta_salud', '')})</p>

    <p><b>Temperatura EMA:</b> {lectura.get('temp_ema', 0):.1f} C<br>
    <b>Presion EMA:</b> {lectura.get('presion_ema', 0):.1f} PSI<br>
    <b>Carga:</b> {lectura.get('porcentaje_carga', 0):.1f}%</p>

    <p><b>Causa probable:</b> {lectura.get('causa_probable', '')}</p>
    <p><b>Reporte del operario:</b> {resultado_audio.get('resumen_operario', '')}</p>
    <p><b>Accion reportada:</b> {resultado_audio.get('accion_detectada', '')}</p>
    <p><b>Respuesta de Maria:</b> {resultado_audio.get('respuesta_asistente', '')}</p>
    <p><b>Estado de monitoreo:</b> reanudado tras cierre del incidente.</p>
    <p>Se adjunta la ficha visual ejecutiva generada por IA para seguimiento gerencial.</p>
  </body>
</html>
"""

        mensaje = EmailMessage()
        mensaje['Subject'] = asunto
        mensaje['From'] = self.config.smtp_sender or self.config.smtp_user
        mensaje['To'] = ', '.join(self.config.supervisor_emails)
        mensaje.set_content(cuerpo_texto)
        mensaje.add_alternative(cuerpo_html, subtype='html')
        mensaje.add_attachment(
            imagen_png,
            maintype='image',
            subtype='png',
            filename='ficha_cierre_incidente.png',
        )

        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=30) as servidor:
                if self.config.smtp_use_tls:
                    servidor.starttls()
                servidor.login(self.config.smtp_user, self.config.smtp_password)
                servidor.send_message(mensaje)
            logger.info(
                "Correo de cierre enviado a %s",
                ', '.join(self.config.supervisor_emails),
            )
            return True
        except Exception as e:
            logger.error("Error enviando correo de cierre: %s", e, exc_info=True)
            return False
