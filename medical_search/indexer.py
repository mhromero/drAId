from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chromadb
import numpy as np
import spacy

from .processor import ProcessedClinicalText


@dataclass(slots=True)
class IndexedDocument:
    doc_id: str
    patient_id: str
    document_date: str
    source_path: str
    processed: ProcessedClinicalText


class SemanticIndexer:
    def __init__(
        self,
        persist_dir: str | Path = "./medical_search/.chroma_medical",
        collection_name: str = "medical_notes",
        nlp_model: str = "en_core_sci_md",
        chunk_size_tokens: int = 160,
        overlap_tokens: int = 40,
    ):
        self.persist_dir = Path(persist_dir)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(
            collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.nlp = spacy.load(nlp_model)
        self.chunk_size_tokens = max(1, chunk_size_tokens)
        self.overlap_tokens = max(0, overlap_tokens)

    def index_document(self, document: IndexedDocument) -> None:
        chunks = self._chunk_text(document.processed.expanded_text)
        if not chunks:
            return

        embeddings = self._vectorize_chunks(chunks)
        total_chunks = len(chunks)

        ids = [f"{document.doc_id}::chunk:{idx}" for idx in range(total_chunks)]
        metadatas = [
            {
                "patient_id": document.patient_id,
                "document_date": document.document_date,
                "source_path": document.source_path,
                "original_text": document.processed.original_text,
                "chunk_index": idx,
                "total_chunks": total_chunks,
            }
            for idx in range(total_chunks)
        ]

        self.collection.upsert(
            ids=ids,
            embeddings=[embedding.tolist() for embedding in embeddings],
            documents=chunks,
            metadatas=metadatas,
        )

    def _vectorize_chunks(self, chunks: list[str]) -> list[np.ndarray]:
        vectors: list[np.ndarray] = []
        for doc in self.nlp.pipe(chunks, batch_size=32):
            vector = doc.vector
            norm = float(np.linalg.norm(vector))
            if norm == 0.0:
                vectors.append(vector.astype(np.float32))
            else:
                vectors.append((vector / norm).astype(np.float32))
        return vectors

    def _chunk_text(self, text: str) -> list[str]:
        doc = self.nlp(text)
        sentences = [(sent.text.strip(), len(sent)) for sent in doc.sents if sent.text.strip()]

        if not sentences:
            stripped = text.strip()
            return [stripped] if stripped else []

        chunks: list[str] = []
        idx = 0
        while idx < len(sentences):
            token_count = 0
            end = idx
            chunk_sentences: list[str] = []

            while end < len(sentences) and (token_count < self.chunk_size_tokens or not chunk_sentences):
                sent_text, sent_tokens = sentences[end]
                chunk_sentences.append(sent_text)
                token_count += sent_tokens
                end += 1

            chunks.append(" ".join(chunk_sentences))

            if end >= len(sentences):
                break

            overlap_count = 0
            back = end - 1
            while back >= idx and overlap_count < self.overlap_tokens:
                overlap_count += sentences[back][1]
                back -= 1

            next_idx = back + 1
            idx = next_idx if next_idx > idx else end

        return chunks
