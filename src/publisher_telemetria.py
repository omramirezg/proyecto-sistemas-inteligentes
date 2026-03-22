"""
Publisher de Telemetría — Google Cloud Pub/Sub
================================================
Simula los sensores de la planta publicando lecturas de telemetría
como mensajes JSON al topic de Pub/Sub.

En producción real, este módulo sería reemplazado por el firmware
de los PLCs o el gateway IoT de la planta. En el prototipo, lee
el CSV histórico y lo publica fila por fila simulando el flujo real.

Arquitectura:
    CSV → PublisherTelemetria → Pub/Sub Topic → Worker (subscriber)

Cada mensaje contiene una lectura cruda de sensores en JSON:
    - Valores de sensores: corriente, temp_acond, presion_vapor, etc.
    - Identificadores: id_planta, id_maquina, id_formula
    - Timestamp de la lectura original
    - message_id único para garantizar idempotencia en el subscriber

Uso standalone:
    python publisher_telemetria.py

Uso como hilo desde el worker:
    publisher = PublisherTelemetria(config)
    threading.Thread(target=publisher.publicar_en_loop, daemon=True).start()
"""

import json
import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class PublisherTelemetria:
    """
    Publica lecturas de telemetría al topic de Pub/Sub.

    Lee el CSV de telemetría y publica cada fila como mensaje JSON,
    simulando el flujo continuo de datos que vendría de sensores reales.
    """

    def __init__(self, config) -> None:
        self.config = config
        self._cliente: Optional[object] = None
        self._topic_path: Optional[str] = None
        self._telemetria: Optional[pd.DataFrame] = None
        self._indice: int = 0
        self._ejecutando: bool = False
        self._lock = threading.Lock()

    # -----------------------------------------------------------------------
    # Inicialización lazy del cliente Pub/Sub
    # -----------------------------------------------------------------------

    def _inicializar_cliente(self) -> None:
        """Inicializa el cliente PublisherClient (lazy loading)."""
        if self._cliente is not None:
            return
        try:
            from google.cloud import pubsub_v1

            self._cliente = pubsub_v1.PublisherClient()
            self._topic_path = self._cliente.topic_path(
                self.config.gcp_project,
                self.config.pubsub_topic,
            )
            logger.info(
                "Publisher Pub/Sub inicializado. Topic: %s",
                self._topic_path,
            )
        except Exception as e:
            logger.error("Error inicializando PublisherClient: %s", e)
            raise

    def crear_topic_si_no_existe(self) -> None:
        """
        Crea el topic en Pub/Sub si no existe.
        Idempotente — si ya existe, no hace nada.
        Útil al arrancar el sistema por primera vez.
        """
        self._inicializar_cliente()
        try:
            self._cliente.create_topic(request={"name": self._topic_path})
            logger.info("Topic creado: %s", self._topic_path)
        except Exception as e:
            if "AlreadyExists" in str(e) or "409" in str(e):
                logger.debug("Topic ya existe: %s", self._topic_path)
            else:
                logger.error("Error creando topic: %s", e)
                raise

    # -----------------------------------------------------------------------
    # Carga de telemetría
    # -----------------------------------------------------------------------

    def _cargar_telemetria(self) -> bool:
        """Carga el CSV de telemetría en memoria."""
        archivo = self.config.data_dir / "telemetria_planta_001.csv"
        if not archivo.exists():
            logger.error("CSV de telemetría no encontrado: %s", archivo)
            return False
        try:
            self._telemetria = pd.read_csv(
                archivo,
                parse_dates=["fecha_registro"],
            )
            logger.info(
                "Telemetría cargada: %d lecturas disponibles.",
                len(self._telemetria),
            )
            return True
        except Exception as e:
            logger.error("Error cargando CSV de telemetría: %s", e)
            return False

    # -----------------------------------------------------------------------
    # Publicación de mensajes
    # -----------------------------------------------------------------------

    def _serializar_fila(self, fila: pd.Series) -> dict:
        """
        Convierte una fila del DataFrame en el dict JSON del mensaje.
        Añade un message_id único para garantizar idempotencia en el subscriber.
        """
        timestamp = fila.get("fecha_registro")
        if hasattr(timestamp, "isoformat"):
            timestamp_str = timestamp.isoformat()
        else:
            timestamp_str = str(timestamp)

        return {
            "message_id":       str(uuid.uuid4()),
            "timestamp_sensor": timestamp_str,
            "timestamp_pubsub": datetime.now().isoformat(),
            "id_planta":        str(fila.get("id_planta", "1")).zfill(3),
            "id_maquina":       str(fila.get("id_maquina", "")).zfill(3),
            "id_formula":       str(fila.get("id_formula", "")),
            "numero_orden":     str(fila.get("numero_orden", "")),
            "corriente":        float(fila.get("corriente", 0)),
            "temp_acond":       float(fila.get("temp_acond", 0)),
            "presion_vapor":    float(fila.get("presion_vapor", 0)),
            "vapor":            float(fila.get("vapor", 0)),
            "porcentaje_vapor": float(fila.get("porcentaje_vapor", 0)),
            "tiempo_proceso":   float(fila.get("tiempo_proceso", 0)),
            "retornando":       int(fila.get("retornando", 0)),
            "humedad_real":     float(fila.get("humedad_real", 0)),
            "durabilidad_real": float(fila.get("durabilidad_real", 0)),
            "kw_h_proceso":     float(fila.get("kw_h_proceso", 0)),
        }

    def publicar_una_lectura(self) -> bool:
        """
        Publica la siguiente lectura disponible del CSV.
        Reinicia desde el inicio al llegar al final (simulación en loop).
        Retorna True si la publicación fue exitosa.
        """
        self._inicializar_cliente()

        if self._telemetria is None:
            if not self._cargar_telemetria():
                return False

        with self._lock:
            if self._indice >= len(self._telemetria):
                logger.info("[PUBLISHER] Fin de telemetría. Reiniciando desde el inicio.")
                self._indice = 0

            fila = self._telemetria.iloc[self._indice]
            self._indice += 1

        datos = self._serializar_fila(fila)
        payload = json.dumps(datos, ensure_ascii=False).encode("utf-8")

        try:
            futuro = self._cliente.publish(self._topic_path, payload)
            msg_id_pubsub = futuro.result(timeout=10)
            logger.debug(
                "[PUBLISHER] Lectura publicada → Pub/Sub ID: %s | Máquina: %s | "
                "T: %.1f°C | P: %.2f PSI",
                msg_id_pubsub,
                datos["id_maquina"],
                datos["temp_acond"],
                datos["presion_vapor"],
            )
            return True
        except Exception as e:
            logger.error("[PUBLISHER] Error publicando mensaje: %s", e)
            return False

    def publicar_en_loop(self, intervalo_seg: Optional[float] = None) -> None:
        """
        Publica lecturas en loop continuo con el intervalo configurado.
        Diseñado para correr en un hilo daemon — se detiene cuando el
        proceso principal termina.

        Args:
            intervalo_seg: Segundos entre publicaciones. Si es None, usa
                           config.intervalo_simulacion.
        """
        intervalo = intervalo_seg or self.config.intervalo_simulacion
        self._ejecutando = True

        logger.info(
            "[PUBLISHER] Loop iniciado. Publicando cada %d segundos en topic '%s'.",
            intervalo,
            self.config.pubsub_topic,
        )

        try:
            self.crear_topic_si_no_existe()
        except Exception as e:
            logger.warning("[PUBLISHER] No se pudo verificar el topic: %s", e)

        while self._ejecutando:
            self.publicar_una_lectura()
            time.sleep(intervalo)

        logger.info("[PUBLISHER] Loop detenido.")

    def detener(self) -> None:
        """Señaliza al loop que debe detenerse."""
        self._ejecutando = False


# ---------------------------------------------------------------------------
# Entry point standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import ConfigLoader

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = ConfigLoader()
    publisher = PublisherTelemetria(config)
    print(f"Publicando en topic: {config.pubsub_topic}")
    print(f"Intervalo: {config.intervalo_simulacion}s")
    print("Presiona Ctrl+C para detener.\n")

    try:
        publisher.publicar_en_loop()
    except KeyboardInterrupt:
        print("\nPublisher detenido.")
