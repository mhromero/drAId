from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .indexer import IndexedDocument, SemanticIndexer
from .ingest import IngestionError, ingest_file
from .processor import initialize_nlp, process_clinical_text
from .search import MedicalSearcher


def run_cli() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "index":
        _run_index(args)
        return

    if args.command == "query":
        _run_query(args)
        return

    parser.print_help()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Medical semantic search CLI")
    subparsers = parser.add_subparsers(dest="command")

    index_parser = subparsers.add_parser("index", help="Index clinical files from a folder")
    index_parser.add_argument("input_dir", type=str, help="Folder containing .txt/.pdf files")
    index_parser.add_argument(
        "--patient-id",
        type=str,
        default=None,
        help="Patient identifier shared by all files in input_dir (default: folder name)",
    )
    index_parser.add_argument("--persist-dir", type=str, default="./medical_search/.chroma_medical")
    index_parser.add_argument("--collection", type=str, default="medical_notes")
    index_parser.add_argument("--embedding-model", type=str, default="en_core_sci_md")
    index_parser.add_argument("--chunk-size", type=int, default=160, help="Target tokens per chunk")
    index_parser.add_argument("--chunk-overlap", type=int, default=40, help="Token overlap between chunks")

    query_parser = subparsers.add_parser("query", help="Search indexed clinical notes")
    query_parser.add_argument("query", type=str, help="Natural language query")
    query_parser.add_argument("--top-k", type=int, default=5)
    query_parser.add_argument("--persist-dir", type=str, default="./medical_search/.chroma_medical")
    query_parser.add_argument("--collection", type=str, default="medical_notes")
    query_parser.add_argument("--embedding-model", type=str, default="en_core_sci_md")

    return parser


def _run_index(args: argparse.Namespace) -> None:
    input_dir = Path(args.input_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist or is not a directory: {input_dir}")

    nlp = initialize_nlp()
    indexer = SemanticIndexer(
        persist_dir=args.persist_dir,
        collection_name=args.collection,
        nlp_model=args.embedding_model,
        chunk_size_tokens=args.chunk_size,
        overlap_tokens=args.chunk_overlap,
    )
    patient_id = args.patient_id or input_dir.name

    indexed = 0
    failed = 0
    for source in _iter_input_documents(input_dir):
        try:
            ingested = ingest_file(source)
            processed = process_clinical_text(ingested.raw_text, nlp)

            document_date = _extract_date_from_name(source.stem)

            indexer.index_document(
                IndexedDocument(
                    doc_id=str(source.resolve()),
                    patient_id=patient_id,
                    document_date=document_date,
                    source_path=str(source.resolve()),
                    processed=processed,
                )
            )
            indexed += 1
            print(f"Indexed: {source}")
        except IngestionError as exc:
            failed += 1
            print(f"[ERROR] {source}: {exc}")

    print(f"Done. Indexed={indexed}, Failed={failed}")


def _run_query(args: argparse.Namespace) -> None:
    searcher = MedicalSearcher(
        persist_dir=args.persist_dir,
        collection_name=args.collection,
        nlp_model=args.embedding_model,
    )

    hits = searcher.search(args.query, top_k=args.top_k)
    if not hits:
        print("No results found.")
        return

    for idx, hit in enumerate(hits, start=1):
        patient_id = hit.metadata.get("patient_id", "unknown")
        document_date = hit.metadata.get("document_date", "unknown")
        source_path = hit.metadata.get("source_path", "unknown")

        print(f"\n[{idx}] score={hit.score:.6f}")
        print(f"patient_id={patient_id}  date={document_date}")
        print(f"source={source_path}")
        print("snippet:")
        print(_truncate(hit.text, limit=450))


def _iter_input_documents(input_dir: Path):
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".txt", ".pdf"}:
            yield path


def _extract_date_from_name(stem: str) -> str:
    for token in stem.replace("-", "_").split("_"):
        try:
            parsed = datetime.strptime(token, "%Y%m%d")
            return parsed.date().isoformat()
        except ValueError:
            continue
    return "unknown"


def _truncate(text: str, limit: int = 450) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."
