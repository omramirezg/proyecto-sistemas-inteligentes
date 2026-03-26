"""
RAG Retriever — Recuperacion semantica con ChromaDB.

Implementa RAG real: embeddings + vector store + retrieval semantico.
En lugar de inyectar las 20 fallas completas en cada prompt, busca
semanticamente las mas relevantes para la alerta actual.

Colecciones:
    - fallas_planta:     20 fallas con sintomas, causas, acciones
    - incidentes_hist:   17+ incidentes pasados con resoluciones
    - conversaciones:    conversaciones pasadas para contexto
"""

import logging
import os
import yaml
import csv
from typing import Optional

logger = logging.getLogger(__name__)


class RAGRetriever:
    """Retriever semantico usando ChromaDB como vector store."""

    def __init__(self, config_dir: str = 'config', data_dir: str = 'data'):
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._client = None
        self._col_fallas = None
        self._col_incidentes = None
        self._col_conversaciones = None
        self._inicializado = False

    def inicializar(self) -> bool:
        """Crea el cliente ChromaDB e indexa los documentos."""
        try:
            import chromadb

            # ChromaDB persistente en disco — los datos sobreviven reinicios
            import os
            db_path = os.path.join(self._data_dir, "chromadb")
            os.makedirs(db_path, exist_ok=True)
            self._client = chromadb.PersistentClient(path=db_path)

            # Crear colecciones
            self._col_fallas = self._client.get_or_create_collection(
                name="fallas_planta",
                metadata={"hnsw:space": "cosine"},
            )
            self._col_incidentes = self._client.get_or_create_collection(
                name="incidentes_historicos",
                metadata={"hnsw:space": "cosine"},
            )
            self._col_conversaciones = self._client.get_or_create_collection(
                name="conversaciones",
                metadata={"hnsw:space": "cosine"},
            )

            # Indexar documentos
            n_fallas = self._indexar_fallas()
            n_incidentes = self._indexar_incidentes()
            n_conv = self._indexar_conversaciones()

            self._inicializado = True
            logger.info(
                "[RAG] Inicializado: %d fallas | %d incidentes | %d conversaciones indexadas",
                n_fallas, n_incidentes, n_conv,
            )
            return True

        except Exception as e:
            logger.error("[RAG] Error inicializando ChromaDB: %s", e)
            return False

    def _indexar_fallas(self) -> int:
        """Indexa las fallas de base_conocimiento_planta.yaml."""
        ruta = os.path.join(self._config_dir, 'base_conocimiento_planta.yaml')
        if not os.path.exists(ruta):
            logger.warning("[RAG] No se encontro base_conocimiento_planta.yaml")
            return 0

        with open(ruta, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        fallas = data.get('fallas_comunes', [])
        if not fallas:
            return 0

        # Verificar si ya estan indexadas
        if self._col_fallas.count() >= len(fallas):
            return self._col_fallas.count()

        ids = []
        documents = []
        metadatas = []

        for falla in fallas:
            fid = falla.get('id', 'F000')
            sintomas = ' '.join(falla.get('sintomas', []))
            causa = falla.get('causa_raiz', '')
            nombre = falla.get('nombre', '')
            verificacion = ' '.join(falla.get('verificacion', []))
            accion_op = ' '.join(falla.get('accion_operario', []))
            accion_mant = ' '.join(falla.get('accion_mantenimiento', []))
            tiempo = falla.get('tiempo_resolucion_tipico', '')

            # Documento completo para embedding
            doc = (
                f"Falla {fid}: {nombre}. "
                f"Sintomas: {sintomas}. "
                f"Causa raiz: {causa}. "
                f"Verificacion: {verificacion}. "
                f"Accion operario: {accion_op}. "
                f"Accion mantenimiento: {accion_mant}. "
                f"Tiempo resolucion: {tiempo}."
            )

            ids.append(fid)
            documents.append(doc)
            metadatas.append({
                'id': fid,
                'nombre': nombre,
                'causa_raiz': causa,
            })

        self._col_fallas.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(ids)

    def _indexar_incidentes(self) -> int:
        """Indexa incidentes historicos del YAML."""
        ruta = os.path.join(self._config_dir, 'base_conocimiento_planta.yaml')
        if not os.path.exists(ruta):
            return 0

        with open(ruta, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        incidentes = data.get('historial_incidentes_referencia', [])
        if not incidentes:
            return 0

        if self._col_incidentes.count() >= len(incidentes):
            return self._col_incidentes.count()

        ids = []
        documents = []
        metadatas = []

        for i, inc in enumerate(incidentes):
            iid = f"INC_{i:03d}"
            doc = (
                f"Incidente en maquina {inc.get('maquina', '?')} "
                f"({inc.get('fecha', '?')}): "
                f"{inc.get('descripcion', '')}. "
                f"Falla: {inc.get('falla', '?')}. "
                f"Resolucion: {inc.get('resolucion', '')}. "
                f"Tiempo: {inc.get('tiempo_total', '?')}. "
                f"Leccion: {inc.get('leccion', '')}."
            )

            ids.append(iid)
            documents.append(doc)
            metadatas.append({
                'maquina': str(inc.get('maquina', '')),
                'falla': str(inc.get('falla', '')),
                'fecha': str(inc.get('fecha', '')),
            })

        self._col_incidentes.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(ids)

    def _indexar_conversaciones(self) -> int:
        """Indexa conversaciones pasadas del CSV."""
        ruta = os.path.join(self._data_dir, 'historial_conversaciones.csv')
        if not os.path.exists(ruta):
            return 0

        try:
            conversaciones = []
            with open(ruta, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    conversaciones.append(row)
        except Exception:
            return 0

        if not conversaciones or self._col_conversaciones.count() >= len(conversaciones):
            return self._col_conversaciones.count()

        ids = []
        documents = []
        metadatas = []

        for i, conv in enumerate(conversaciones):
            cid = f"CONV_{i:04d}"
            doc = (
                f"Conversacion con operario (chat {conv.get('chat_id', '?')}): "
                f"{conv.get('contenido', '')}. "
                f"Incidente: {conv.get('incidente_id', '?')}."
            )
            ids.append(cid)
            documents.append(doc[:5000])  # Limitar tamano
            metadatas.append({
                'chat_id': str(conv.get('chat_id', '')),
                'incidente_id': str(conv.get('incidente_id', '')),
            })

        if ids:
            self._col_conversaciones.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(ids)

    def buscar_fallas_similares(self, contexto_alerta: str, n_resultados: int = 3) -> list[str]:
        """Busca las fallas mas relevantes para la alerta actual."""
        if not self._inicializado or not self._col_fallas:
            return []

        try:
            resultados = self._col_fallas.query(
                query_texts=[contexto_alerta],
                n_results=min(n_resultados, self._col_fallas.count()),
            )

            documentos = resultados.get('documents', [[]])[0]
            distancias = resultados.get('distances', [[]])[0]

            logger.info(
                "[RAG] Busqueda de fallas: query='%s...' | %d resultados | distancias=%s",
                contexto_alerta[:60], len(documentos),
                [f"{d:.3f}" for d in distancias] if distancias else "N/A",
            )
            return documentos

        except Exception as e:
            logger.error("[RAG] Error buscando fallas: %s", e)
            return []

    def buscar_incidentes_similares(self, contexto_alerta: str, n_resultados: int = 2) -> list[str]:
        """Busca incidentes historicos similares a la alerta actual."""
        if not self._inicializado or not self._col_incidentes:
            return []

        try:
            resultados = self._col_incidentes.query(
                query_texts=[contexto_alerta],
                n_results=min(n_resultados, self._col_incidentes.count()),
            )

            documentos = resultados.get('documents', [[]])[0]
            distancias = resultados.get('distances', [[]])[0]

            logger.info(
                "[RAG] Busqueda de incidentes: %d resultados | distancias=%s",
                len(documentos),
                [f"{d:.3f}" for d in distancias] if distancias else "N/A",
            )
            return documentos

        except Exception as e:
            logger.error("[RAG] Error buscando incidentes: %s", e)
            return []

    def buscar_conversaciones_similares(self, contexto: str, n_resultados: int = 2) -> list[str]:
        """Busca conversaciones pasadas similares."""
        if not self._inicializado or not self._col_conversaciones:
            return []
        if self._col_conversaciones.count() == 0:
            return []

        try:
            resultados = self._col_conversaciones.query(
                query_texts=[contexto],
                n_results=min(n_resultados, self._col_conversaciones.count()),
            )
            return resultados.get('documents', [[]])[0]
        except Exception as e:
            logger.error("[RAG] Error buscando conversaciones: %s", e)
            return []

    def construir_bloque_rag(self, contexto_alerta: str) -> str:
        """Construye el bloque de contexto RAG para inyectar en el prompt.

        Este es el metodo principal: recibe el contexto de la alerta actual
        y devuelve un bloque de texto con las fallas e incidentes mas relevantes.
        """
        if not self._inicializado:
            return ""

        fallas = self.buscar_fallas_similares(contexto_alerta, n_resultados=3)
        incidentes = self.buscar_incidentes_similares(contexto_alerta, n_resultados=2)
        conversaciones = self.buscar_conversaciones_similares(contexto_alerta, n_resultados=1)

        bloques = []

        if fallas:
            bloques.append("=== FALLAS MAS PROBABLES (recuperadas por similitud semantica) ===")
            for i, falla in enumerate(fallas, 1):
                bloques.append(f"Falla candidata {i}: {falla}")
            bloques.append("=== FIN FALLAS CANDIDATAS ===")

        if incidentes:
            bloques.append("")
            bloques.append("=== INCIDENTES HISTORICOS SIMILARES ===")
            for i, inc in enumerate(incidentes, 1):
                bloques.append(f"Precedente {i}: {inc}")
            bloques.append("=== FIN INCIDENTES ===")

        if conversaciones:
            bloques.append("")
            bloques.append("=== CONVERSACIONES PASADAS SIMILARES ===")
            for i, conv in enumerate(conversaciones, 1):
                bloques.append(f"Referencia {i}: {conv}")
            bloques.append("=== FIN CONVERSACIONES ===")

        if bloques:
            bloques.insert(0, "IMPORTANTE: Las siguientes fallas e incidentes fueron recuperados por SIMILITUD SEMANTICA con la alerta actual. Usalos como referencia para el diagnostico.")

        return "\n".join(bloques)

    def agregar_conversacion(self, chat_id: int, incidente_id: int, contenido: str) -> None:
        """Agrega una conversacion cerrada al indice para futuras busquedas."""
        if not self._inicializado or not self._col_conversaciones:
            return

        try:
            cid = f"CONV_LIVE_{chat_id}_{incidente_id}"
            doc = f"Conversacion con operario (chat {chat_id}): {contenido}. Incidente: {incidente_id}."
            self._col_conversaciones.add(
                ids=[cid],
                documents=[doc[:5000]],
                metadatas=[{'chat_id': str(chat_id), 'incidente_id': str(incidente_id)}],
            )
            logger.info("[RAG] Conversacion indexada: %s", cid)
        except Exception as e:
            logger.error("[RAG] Error indexando conversacion: %s", e)

    @property
    def stats(self) -> dict:
        """Estadisticas del retriever."""
        if not self._inicializado:
            return {'inicializado': False}
        return {
            'inicializado': True,
            'fallas_indexadas': self._col_fallas.count() if self._col_fallas else 0,
            'incidentes_indexados': self._col_incidentes.count() if self._col_incidentes else 0,
            'conversaciones_indexadas': self._col_conversaciones.count() if self._col_conversaciones else 0,
        }
