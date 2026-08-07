"""
Diagnoses a "view doc shows something other than the file" report: looks up
a SupplierDocument or AgentDocument by id, prints how it's stored, builds
the same signed Cloudinary URL the /private-documents endpoint would return,
and fetches it directly to show exactly what Cloudinary sends back.

Run on the server where the real database/Cloudinary account live:
  python -m scripts.diagnose_document supplier 19
  python -m scripts.diagnose_document agent 7
"""
import sys

import app.main  # noqa: F401  (registers all SQLAlchemy models)

from app.database import SessionLocal
from app.utils.cloudinary_client import get_private_file_url


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("supplier", "agent"):
        raise SystemExit("Usage: python -m scripts.diagnose_document <supplier|agent> <document_id>")
    owner_type, doc_id = sys.argv[1], int(sys.argv[2])

    db = SessionLocal()
    try:
        if owner_type == "supplier":
            from app.models.suppliers import SupplierDocument as Model
        else:
            from app.models.agents import AgentDocument as Model

        doc = db.query(Model).filter(Model.id == doc_id).first()
        if not doc:
            print(f"No {owner_type} document with id={doc_id} found in this database.")
            return

        print(f"id={doc.id}  document_type={getattr(doc, 'document_type', None)!r}  mime_type={doc.mime_type!r}")
        print(f"file_path={doc.file_path!r}")

        if not doc.file_path:
            print("-> file_path is empty. Nothing to serve; the frontend would get a 404.")
            return

        if not doc.file_path.startswith("cloudinary:"):
            print("-> Not a Cloudinary marker (legacy /private-documents/ or /storage/ path) - different code path, not the Cloudinary one.")
            return

        resource_type, _, public_id = doc.file_path.removeprefix("cloudinary:").partition(":")
        print(f"resource_type={resource_type!r}  public_id={public_id!r}")

        try:
            url = get_private_file_url(public_id, resource_type or "image")
        except Exception as error:
            print(f"-> get_private_file_url raised: {error!r}")
            return
        print(f"signed URL: {url}")

        import urllib.request
        import urllib.error

        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                body = response.read(500)
                print(f"-> HTTP {response.status}  Content-Type: {response.headers.get('Content-Type')}")
                print(f"-> First 500 bytes: {body!r}")
        except urllib.error.HTTPError as error:
            body = error.read(500)
            print(f"-> HTTP {error.code} {error.reason}  Content-Type: {error.headers.get('Content-Type')}")
            print(f"-> First 500 bytes of error body: {body!r}")
        except Exception as error:
            print(f"-> Request failed: {error!r}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
