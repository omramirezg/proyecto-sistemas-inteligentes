"""
Script Utilitario para Simulación IoT en Tiempo Real
=====================================================
Ajusta la columna temporal de los archivos CSV de telemetría a la fecha
y hora en la que se ejecuta este script. Esto permite simular una 
captura de datos IoT que ocurre siempre en tiempo real para las 
pruebas del Motor de Reglas (motor_reglas.py).

Ejecución: python data/avanzar_tiempo.py
"""

import pandas as pd
from datetime import datetime
import os
from pathlib import Path
import logging

# Configurar logging simple
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def actualizar_tiempos():
    directorio_data = Path(__file__).resolve().parent
    
    archivos = [
        directorio_data / "telemetria_planta_001.csv",
        directorio_data / "telemetria_planta_002.csv"
    ]

    fecha_inicial = datetime.now()
    logger.info("Iniciando ajuste temporal a partir de: %s", fecha_inicial.strftime('%Y-%m-%d %H:%M:%S'))

    for archivo in archivos:
        if archivo.exists():
            try:
                # Leer el archivo CSV
                df = pd.read_csv(archivo)
                
                # Generar rango de fechas (1 minuto de diferencia por fila)
                nuevas_fechas = pd.date_range(
                    start=fecha_inicial, 
                    periods=len(df), 
                    freq='min'  # Frecuencia de 1 minuto
                )
                
                # Formatear a string prescindiendo de los microsegundos si se quiere (pero con milisegundos como el original)
                df['fecha_registro'] = nuevas_fechas.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]
                
                # Guardar el CSV sobrescribiendo
                df.to_csv(archivo, index=False)
                logger.info("✅ Archivo actualizado: %s (%d filas adaptadas)", archivo.name, len(df))
            
            except Exception as e:
                logger.error("❌ Error procesando %s: %s", archivo.name, e)
        else:
            logger.warning("⚠️ No encontrado: %s", archivo.name)

if __name__ == "__main__":
    actualizar_tiempos()
