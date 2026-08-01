"""
One-time migration: move invoice/itinerary PDFs out of the public
/storage mount into the private-docs root, and repoint invoices.pdf_path
at the new location.

Before this fix, invoices and itineraries were written under
storage/invoices/ and storage/itineraries/ - both served publicly,
unauthenticated, by the /storage StaticFiles mount in app/main.py, with
predictable sequential filenames. They now live under private-docs/,
which is never mounted publicly and is only reachable through the
existing ownership-checked download routes.

Run from the backend directory:

    python -m scripts.migrate_private_docs
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.main  # noqa: F401,E402 - loads every model into Base.metadata
from app.config import get_storage_root, get_private_docs_root  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.invoices import Invoice  # noqa: E402


def _move_tree(old_dir: Path, new_dir: Path) -> int:
    if not old_dir.exists():
        return 0
    new_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for src in old_dir.iterdir():
        if not src.is_file():
            continue
        dest = new_dir / src.name
        if dest.exists():
            print(f"    skip (already exists): {dest.name}")
            continue
        shutil.move(str(src), str(dest))
        moved += 1
    return moved


def main() -> None:
    storage_root = get_storage_root()
    private_root = get_private_docs_root()

    print("Moving invoice PDFs...")
    moved_invoices = _move_tree(storage_root / "invoices", private_root / "invoices")
    print(f"  moved {moved_invoices} file(s)")

    print("Moving itinerary PDFs...")
    moved_itineraries = _move_tree(storage_root / "itineraries", private_root / "itineraries")
    print(f"  moved {moved_itineraries} file(s)")

    print("Repointing invoices.pdf_path...")
    db = SessionLocal()
    try:
        updated = 0
        for inv in db.query(Invoice).filter(Invoice.pdf_path.like("/storage/invoices/%")).all():
            inv.pdf_path = inv.pdf_path.replace("/storage/invoices/", "/private-docs/invoices/", 1)
            updated += 1
        db.commit()
        print(f"  updated {updated} invoice row(s)")
    finally:
        db.close()

    print("Done.")


if __name__ == "__main__":
    main()
