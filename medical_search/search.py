from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata

import chromadb
import numpy as np
import spacy

from .processor import preprocess_query


@dataclass(slots=True)
class SearchHit:
    doc_id: str
    score: float
    text: str
    metadata: dict


class MedicalSearcher:
    def __init__(
        self,
        persist_dir: str | Path = "./medical_search/.chroma_medical",
        collection_name: str = "medical_notes",
        nlp_model: str = "en_core_sci_md",
    ):
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.client.get_or_create_collection(
            collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        metadata = self.collection.metadata or {}
        self.distance_space = str(metadata.get("hnsw:space", "l2")).lower()
        self.nlp = spacy.load(nlp_model)

    def search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        query_text = preprocess_query(query)
        query_embedding = self._vectorize(query_text)

        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            include=["documents", "metadatas", "distances", "embeddings"],
        )

        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        result_embeddings = results.get("embeddings", [[]])[0]

        hits: list[SearchHit] = []
        for idx, (doc_id, doc_text, metadata, distance) in enumerate(zip(ids, documents, metadatas, distances)):
            score = self._distance_to_similarity(float(distance))

            if idx < len(result_embeddings) and result_embeddings[idx] is not None:
                doc_embedding = np.asarray(result_embeddings[idx], dtype=np.float32)
                score = self._hybrid_similarity(query_text, doc_text, query_embedding, doc_embedding)

            hits.append(SearchHit(doc_id=doc_id, score=score, text=doc_text, metadata=metadata or {}))

        return hits

    def _distance_to_similarity(self, distance: float) -> float:
        if self.distance_space == "cosine":
            score = 1.0 - distance
        elif self.distance_space == "l2":
            # For normalized vectors: ||a-b||^2 = 2 - 2*cos(theta) => cos(theta)=1 - d^2/2
            score = 1.0 - ((distance * distance) / 2.0)
        else:
            # Fallback for uncommon spaces.
            score = 1.0 - distance

        if score > 1.0:
            return 1.0
        if score < -1.0:
            return -1.0
        return score

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        a_norm = float(np.linalg.norm(a))
        b_norm = float(np.linalg.norm(b))
        if a_norm == 0.0 or b_norm == 0.0:
            return 0.0

        score = float(np.dot(a, b) / (a_norm * b_norm))
        if score > 1.0:
            return 1.0
        if score < -1.0:
            return -1.0
        return score

    def _hybrid_similarity(self, query_text: str, doc_text: str, q_vec: np.ndarray, d_vec: np.ndarray) -> float:
        cosine = self._cosine_similarity(q_vec, d_vec)
        if cosine != 0.0:
            return cosine

        # Fast fallback when vector norms are zero (common for OOV/non-English terms).
        return self._lexical_overlap_similarity(query_text, doc_text)

    def _lexical_overlap_similarity(self, query_text: str, doc_text: str) -> float:
        q_tokens = self._normalize_tokens(query_text)
        d_tokens = self._normalize_tokens(doc_text)
        if not q_tokens or not d_tokens:
            return 0.0

        shared = q_tokens & d_tokens
        return float(len(shared) / len(q_tokens))

    def _normalize_tokens(self, text: str) -> set[str]:
        normalized = unicodedata.normalize("NFKD", text.lower())
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return {token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) > 1}

    def _vectorize(self, text: str) -> np.ndarray:
        vector = self.nlp(text).vector
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            return vector.astype(np.float32)
        return (vector / norm).astype(np.float32)
