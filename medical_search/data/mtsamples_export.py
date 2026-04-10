from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export transcriptions from mtsamples.csv into .txt files")
    parser.add_argument("csv_path", type=str, help="Path to mtsamples.csv")
    parser.add_argument("output_dir", type=str, help="Directory where .txt files will be written")
    parser.add_argument(
        "--first-only",
        action="store_true",
        help="Export only the first row with non-empty transcription (useful for quick tests)",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    exported = export_mtsamples(csv_path=csv_path, output_dir=output_dir, first_only=args.first_only)
    print(f"Exported {exported} file(s) to {output_dir}")


def export_mtsamples(csv_path: Path, output_dir: Path, first_only: bool = False) -> int:
    exported = 0

    with csv_path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_idx, row in enumerate(reader, start=1):
            transcription = (row.get("transcription") or "").strip()
            if not transcription:
                continue

            sample_name = (row.get("sample_name") or f"mt{row_idx}").strip().replace(" ", "_")
            out_path = output_dir / f"{sample_name}_{row_idx}.txt"
            out_path.write_text(transcription, encoding="utf-8")
            exported += 1

            if first_only:
                break

    return exported


if __name__ == "__main__":
    main()
