"""
Re-index all policy documents in data/uploaded_policies/ into ChromaDB.

Reads document metadata (sensitivity_level, allowed_roles, title) from the
SQLite database — not from file front matter — because admins set that metadata
at upload time via the form. This matches exactly what process_upload() does.

Clears the existing ChromaDB collection first so stale chunks from the old
word-count chunker are fully replaced by the new heading-based chunks.

Usage (from repo root with venv active):
    python scripts/reindex_policies.py
    python scripts/reindex_policies.py --dry-run   # show chunks without writing
"""

import argparse
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so backend.app.* imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.database import SessionLocal  # noqa: E402
from backend.app.documents.chunker import chunk_document  # noqa: E402
from backend.app.documents.loader import LoadedDocument  # noqa: E402
from backend.app.documents.service import _load_body  # noqa: E402
from backend.app.models import Document  # noqa: E402
from backend.app.rag.vector_store import VectorStore  # noqa: E402

POLICIES_DIR = Path("data/uploaded_policies")


def reindex(dry_run: bool = False) -> None:
    db = SessionLocal()
    try:
        doc_records = db.query(Document).order_by(Document.filename).all()
    finally:
        db.close()

    if not doc_records:
        print("No documents found in SQLite. Upload documents via the admin UI first.")
        return

    print(f"Found {len(doc_records)} document record(s) in SQLite:\n")

    all_chunks = []
    for record in doc_records:
        file_path = POLICIES_DIR / record.filename
        if not file_path.exists():
            print(f"  [SKIP] {record.filename} — file not found on disk")
            continue

        loaded: LoadedDocument = _load_body(file_path)
        loaded.title = record.title
        loaded.sensitivity_level = record.sensitivity_level
        loaded.allowed_roles = record.sensitivity_level  # reconstruct from level
        loaded.filename = record.filename

        # Reconstruct allowed_roles from sensitivity level the same way the upload does
        _ROLE_MAP = {
            "public":       "user,security_analyst,admin",
            "internal":     "user,security_analyst,admin",
            "confidential": "security_analyst,admin",
            "restricted":   "admin",
        }
        loaded.allowed_roles = _ROLE_MAP.get(record.sensitivity_level, "admin")

        chunks = chunk_document(loaded)

        # Re-apply the same chunk ID prefix as process_upload
        for chunk in chunks:
            chunk.chunk_id = f"upload{record.id}_{chunk.chunk_id}"

        print(
            f"  {record.filename}  →  {len(chunks)} chunk(s)"
            f"  [sensitivity={record.sensitivity_level}, db_id={record.id}]"
        )
        for chunk in chunks:
            heading = chunk.section_heading or "(no heading)"
            print(f"      chunk {chunk.chunk_id}  §{heading}")

        all_chunks.extend(chunks)

    print(f"\nTotal chunks: {len(all_chunks)}")

    if dry_run:
        print("\n[dry-run] Skipping ChromaDB write.")
        return

    store = VectorStore()
    print("\nResetting ChromaDB collection…")
    store.reset_collection()
    print(f"Inserting {len(all_chunks)} chunks…")
    store.add_chunks(all_chunks)
    print("Done. Re-indexing complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-index policy documents into ChromaDB")
    parser.add_argument("--dry-run", action="store_true", help="Show chunks without writing")
    args = parser.parse_args()
    reindex(dry_run=args.dry_run)
