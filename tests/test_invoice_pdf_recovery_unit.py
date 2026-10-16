from pathlib import Path

from app.services import invoices


class _Invoice:
    invoice_number = "30"
    pdf_path = "/private-docs/invoices/30.pdf"


def test_download_regenerates_a_missing_derived_pdf(monkeypatch, tmp_path):
    invoice = _Invoice()
    pdf_path = tmp_path / "30.pdf"
    regenerated = []

    monkeypatch.setattr(invoices, "get_invoice", lambda db, invoice_id, actor: invoice)
    monkeypatch.setattr(invoices, "log_audit", lambda *args, **kwargs: None)

    def regenerate(db, invoice_id, actor, request=None):
        regenerated.append((invoice_id, actor))
        pdf_path.write_bytes(b"%PDF-1.4")
        return invoice

    monkeypatch.setattr(invoices, "regenerate_invoice_pdf", regenerate)
    monkeypatch.setattr(
        "app.utils.media.resolve_private_docs_path",
        lambda file_path, prefix: pdf_path if file_path == invoice.pdf_path else None,
    )

    resolved, filename = invoices.download_invoice_pdf(object(), 30, actor="agent")

    assert Path(resolved) == pdf_path
    assert filename == "30.pdf"
    assert regenerated == [(30, "agent")]
