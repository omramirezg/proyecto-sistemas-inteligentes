"""Construccion de mensajes de alerta para operarios y gerencia."""

import html
from typing import Any

from analizador_telemetria import AnalizadorTelemetria


class ConstructorMensajes:
    """Formatea mensajes de proceso para distintas audiencias."""

    @staticmethod
    def mensaje_operario(
        lectura: dict[str, Any],
        estado_global: str,
        severidad: str,
        indice_salud: int,
        etiqueta_salud: str,
        estado_temperatura: str,
        estado_presion: str,
        porcentaje_carga: float,
        tendencia_temp: str,
        tendencia_pres: str,
        pronostico: str,
        pronostico_nivel: str,
        causa_probable: str,
    ) -> str:
        """Construye un mensaje breve y accionable para el operario."""
        resumen_tendencia = AnalizadorTelemetria.resumen_tendencia_corta(
            tendencia_temp=tendencia_temp,
            tendencia_pres=tendencia_pres,
            pronostico_nivel=pronostico_nivel,
        )
        causa_corta = AnalizadorTelemetria.compactar_causa_probable(causa_probable)
        estado_linea = f"{estado_global} | {severidad}"
        if severidad in {'ALTA', 'CRITICA'}:
            estado_linea = f"Atencion: {estado_linea}"

        return (
            f"<b>Lectura {lectura['numero']} | Maquina {lectura['id_maquina']}</b>\n"
            f"<b>{estado_linea}</b>\n"
            f"Temp <b>{lectura['temp_ema']:.1f} C</b> ({estado_temperatura}) | "
            f"Pres <b>{lectura['presion_ema']:.1f} PSI</b> ({estado_presion})\n"
            f"Salud <b>{indice_salud}/100</b> ({etiqueta_salud}) | Carga <b>{porcentaje_carga:.1f}%</b>\n"
            f"<b>Lectura rapida:</b> {resumen_tendencia}\n"
            f"<b>Posible causa:</b> {causa_corta}"
        )

    @staticmethod
    def mensaje_gerencial(
        lectura: dict[str, Any],
        estado_global: str,
        severidad: str,
        indice_salud: int,
        etiqueta_salud: str,
        estado_temperatura: str,
        estado_presion: str,
        porcentaje_carga: float,
        pronostico: str,
        pronostico_nivel: str,
        causa_probable: str,
        prescripcion_maria: str,
        resumen_alerta: str,
    ) -> str:
        """Construye un mensaje mas completo para supervisor o gerencia."""
        mensaje = (
            f"<b>Lectura {lectura['numero']} | Planta {lectura['id_planta']} | Maquina {lectura['id_maquina']}</b>\n"
            f"<b>{estado_global}</b> | {severidad} | Salud <b>{indice_salud}/100</b> ({etiqueta_salud})\n"
            f"Temp <b>{lectura['temp_ema']:.1f} C</b> ({estado_temperatura}) | "
            f"Pres <b>{lectura['presion_ema']:.1f} PSI</b> ({estado_presion}) | "
            f"Carga <b>{porcentaje_carga:.1f}%</b>\n"
            f"<b>Pronostico 5 min:</b> {pronostico} ({pronostico_nivel})\n"
            f"<b>Causa probable:</b> {causa_probable}\n"
            f"<b>Maria:</b> {html.escape(ConstructorMensajes.compactar_prescripcion_maria(prescripcion_maria))}"
        )
        if resumen_alerta:
            mensaje += f"\n<b>Alarma confirmada:</b> {resumen_alerta}"
        return mensaje

    @staticmethod
    def compactar_prescripcion_maria(prescripcion: str) -> str:
        """Reduce la salida de Maria a una sola instruccion clara para chat."""
        texto = AnalizadorTelemetria.limpiar_texto_llm(prescripcion)
        if not texto:
            return 'Continuar monitoreo operativo.'

        partes = [
            fragmento.strip()
            for fragmento in texto.replace('?', '.').replace('!', '.').split('.')
            if fragmento.strip()
        ]
        if not partes:
            return texto[:110].rstrip(' ,.;:') + ('...' if len(texto) > 110 else '')

        primera = partes[0]
        if len(primera) <= 110:
            return primera + '.'
        return primera[:107].rstrip(' ,.;:') + '...'
