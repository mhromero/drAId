# dr AId

Diagnostic screening for doctor appointments based on patient symptoms and history through integration with an LLM model.

https://youtu.be/YCr1c3JRJwE

https://youtu.be/5faREiga4o0

## Medical Semantic Search Pipeline

This repository now includes a modular clinical search pipeline in `medical_search/`:

- `ingest.py`: ingests `.txt` and `.pdf`, including OCR fallback for scanned PDFs.
- `processor.py`: SciSpaCy clinical NLP (`en_core_sci_md`), abbreviation expansion, negation filtering, entity linking.
- `indexer.py`: sentence-transformers embeddings + ChromaDB storage.
- `search.py`: semantic retrieval with cosine-based similarity scores.
- `cli.py`: simple CLI for indexing and querying.

### Install dependencies

```bash
uv sync
```

Tesseract OCR binary is required for scanned PDFs:

```bash
sudo apt-get update && sudo apt-get install -y tesseract-ocr
```

### Index clinical documents

```bash
uv run medical-search index medical_search/data/paciente_demo_001 --patient-id paciente_demo_001
```

This command recursively processes `.txt` and `.pdf` files.

### Search by clinical intent

```bash
uv run medical-search query "cetirizine treatment" --top-k 5
```
