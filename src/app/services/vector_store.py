import logging
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 100


class VectorStoreService:
    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_name: str = "tcg_chunks",
        dimension: int = 768,
    ):
        self._client = client
        self._collection_name = collection_name
        self._dimension = dimension

    @property
    def collection_name(self) -> str:
        return self._collection_name

    async def ensure_collection(self) -> None:
        collections = await self._client.get_collections()
        existing = [c.name for c in collections.collections]
        if self._collection_name in existing:
            info = await self._client.get_collection(self._collection_name)
            vectors_cfg = info.config.params.vectors
            existing_dim = vectors_cfg.size if hasattr(vectors_cfg, "size") else None
            if existing_dim is not None and existing_dim != self._dimension:
                raise ValueError(
                    f"Qdrant collection '{self._collection_name}' has dimension "
                    f"{existing_dim} but expected {self._dimension}. "
                    f"Delete the collection or change EMBEDDING_DIMENSION."
                )
            else:
                logger.info(
                    "Qdrant collection '%s' ready (dimension=%d)",
                    self._collection_name,
                    self._dimension,
                )
            return

        await self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=VectorParams(
                size=self._dimension,
                distance=Distance.COSINE,
            ),
        )
        await self._client.create_payload_index(
            collection_name=self._collection_name,
            field_name="document_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        logger.info(
            "Created Qdrant collection '%s' (dimension=%d)",
            self._collection_name,
            self._dimension,
        )

    async def upsert_chunks(
        self,
        chunks: list[dict],
        vectors: list[list[float]],
    ) -> list[str]:
        points: list[PointStruct] = []
        point_ids: list[str] = []
        for chunk, vector in zip(chunks, vectors):
            point_id = str(uuid.uuid4())
            point_ids.append(point_id)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "document_id": chunk["document_id"],
                        "chunk_index": chunk["chunk_index"],
                        "content": chunk["content"],
                        "parent_content": chunk["parent_content"],
                        "metadata": chunk.get("metadata", {}),
                    },
                )
            )

        for i in range(0, len(points), UPSERT_BATCH_SIZE):
            batch = points[i : i + UPSERT_BATCH_SIZE]
            await self._client.upsert(
                collection_name=self._collection_name,
                points=batch,
            )

        logger.info("Upserted %d vectors to Qdrant", len(points))
        return point_ids

    async def search(
        self,
        query_vector: list[float],
        document_ids: list[str],
        limit: int = 20,
    ) -> list[dict]:
        if not document_ids:
            return []
        results = await self._client.search(
            collection_name=self._collection_name,
            query_vector=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchAny(any=document_ids),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
        )
        return [
            {
                "id": str(hit.id),
                "score": hit.score,
                **(hit.payload or {}),
            }
            for hit in results
        ]

    async def delete_by_document(self, document_id: str) -> None:
        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )
        logger.info("Deleted vectors for document %s", document_id)
