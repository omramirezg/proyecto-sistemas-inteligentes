"""
Módulo de Configuración Central
================================
Gestiona la carga de variables de entorno y configuraciones YAML
para todos los componentes del sistema de alertamiento IA.

Principio: Desacoplamiento Lógico — ningún parámetro operativo
se escribe de forma fija en el código fuente.
"""

import os
import logging
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Directorio raíz del proyecto (un nivel arriba de /src)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigLoader:
    """
    Centraliza el acceso a toda la configuración del sistema.
    
    Carga variables de entorno desde .env y archivos YAML desde /config.
    Implementa el patrón Singleton para evitar cargas múltiples.
    """

    _instance: Optional['ConfigLoader'] = None

    def __new__(cls) -> 'ConfigLoader':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        # Cargar variables de entorno desde .env
        env_path = PROJECT_ROOT / '.env'
        if env_path.exists():
            load_dotenv(env_path)
            logger.info("Variables de entorno cargadas desde: %s", env_path)
        else:
            logger.warning("Archivo .env no encontrado en: %s", env_path)

        # Cache de configuraciones YAML
        self._yaml_cache: dict = {}

    # =====================================================
    # Propiedades de Google Cloud Platform
    # =====================================================

    @property
    def gcp_project(self) -> str:
        """ID del proyecto en Google Cloud Platform."""
        return os.getenv('GOOGLE_CLOUD_PROJECT', '')

    @property
    def gcp_credentials_path(self) -> str:
        """Ruta al archivo de credenciales JSON de GCP."""
        cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '')
        if not os.path.isabs(cred_path):
            cred_path = str(PROJECT_ROOT / cred_path)
        return cred_path

    @property
    def gcs_bucket(self) -> str:
        """Nombre del bucket en Google Cloud Storage."""
        return os.getenv('GCS_BUCKET', '')

    # =====================================================
    # Propiedades de Telegram
    # =====================================================

    @property
    def telegram_bot_token(self) -> str:
        """Token del bot de Telegram obtenido de @BotFather."""
        return os.getenv('TELEGRAM_BOT_TOKEN', '')

    # =====================================================
    # Propiedades de Gemini (Vertex AI)
    # =====================================================

    @property
    def gemini_model(self) -> str:
        """Modelo de Gemini a utilizar."""
        return os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')

    @property
    def gemini_image_model(self) -> str:
        """Modelo de Gemini para generación/edición de imágenes."""
        return os.getenv('GEMINI_IMAGE_MODEL', 'gemini-2.5-flash-image')

    @property
    def gemini_location(self) -> str:
        """Región de Vertex AI."""
        return os.getenv('GEMINI_LOCATION', 'us-central1')

    # =====================================================
    # Propiedades de Text-to-Speech
    # =====================================================

    @property
    def tts_language(self) -> str:
        """Código de idioma para Cloud TTS."""
        return os.getenv('TTS_LANGUAGE', 'es-US')

    @property
    def tts_voice(self) -> str:
        """Nombre de la voz para Cloud TTS."""
        return os.getenv('TTS_VOICE', 'es-US-Neural2-A')

    # =====================================================
    # Propiedades de rutas del proyecto
    # =====================================================

    @property
    def data_dir(self) -> Path:
        """Directorio de datos (CSVs maestros y telemetría)."""
        return PROJECT_ROOT / 'data'

    @property
    def logs_dir(self) -> Path:
        """Directorio de logs."""
        return PROJECT_ROOT / 'logs'

    @property
    def config_dir(self) -> Path:
        """Directorio de configuraciones YAML."""
        return PROJECT_ROOT / 'config'

    # =====================================================
    # Propiedades de simulación (prototipo)
    # =====================================================

    @property
    def intervalo_simulacion(self) -> int:
        """Segundos entre cada lectura simulada de telemetría."""
        return int(os.getenv('INTERVALO_SIMULACION', '5'))

    @property
    def max_alertas_por_ventana(self) -> int:
        """Máximo de alertas permitidas en la ventana anti-spam."""
        return int(os.getenv('MAX_ALERTAS_VENTANA', '2'))

    @property
    def ventana_antispam_minutos(self) -> int:
        """Duración en minutos de la ventana anti-spam."""
        return int(os.getenv('VENTANA_ANTISPAM_MIN', '10'))

    @property
    def ema_alpha(self) -> float:
        """Factor de suavizado alpha para EMA (0 < alpha <= 1)."""
        return float(os.getenv('EMA_ALPHA', '0.3'))

    # =====================================================
    # Carga de archivos YAML
    # =====================================================

    def cargar_yaml(self, nombre_archivo: str) -> dict:
        """
        Carga un archivo YAML desde el directorio /config.
        
        Los resultados se cachean para evitar lecturas repetidas al disco.
        
        Args:
            nombre_archivo: Nombre del archivo YAML (ej: 'agente_persona.yaml')
            
        Returns:
            Diccionario con el contenido del YAML.
            
        Raises:
            FileNotFoundError: Si el archivo no existe.
        """
        if nombre_archivo in self._yaml_cache:
            return self._yaml_cache[nombre_archivo]

        yaml_path = self.config_dir / nombre_archivo
        if not yaml_path.exists():
            raise FileNotFoundError(
                f"Archivo de configuración no encontrado: {yaml_path}"
            )

        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        self._yaml_cache[nombre_archivo] = data
        logger.info("Configuración YAML cargada: %s", nombre_archivo)
        return data

    @property
    def agente_persona(self) -> dict:
        """Configuración de personalidad y system prompt del agente LLM."""
        return self.cargar_yaml('agente_persona.yaml')

    @property
    def politicas_empresa(self) -> dict:
        """Políticas empresariales y guardarraíles de seguridad."""
        return self.cargar_yaml('politicas_empresa.yaml')

    def recargar_yaml(self) -> None:
        """Limpia la caché de YAML para forzar recarga desde disco."""
        self._yaml_cache.clear()
        logger.info("Caché de configuraciones YAML limpiada.")

    # =====================================================
    # Configuración de Logging
    # =====================================================

    def configurar_logging(self) -> None:
        """
        Configura el sistema de logging con salida a consola y archivo.
        
        Los logs de depuración van a /logs/app_debug.log (rotativo).
        """
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.logs_dir / 'app_debug.log'

        # Formato profesional con contexto
        formato = logging.Formatter(
            fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Handler de archivo
        file_handler = logging.FileHandler(
            log_file, encoding='utf-8', mode='a'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formato)

        # Handler de consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formato)

        # Configuración del logger raíz
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        
        # Evitar handlers duplicados
        if not root_logger.handlers:
            root_logger.addHandler(file_handler)
            root_logger.addHandler(console_handler)

        logger.info("Sistema de logging configurado. Archivo: %s", log_file)
