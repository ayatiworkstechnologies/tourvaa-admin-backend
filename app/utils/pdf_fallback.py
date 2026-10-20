"""Small dependency-free helpers for creating readable fallback PDFs."""
from pathlib import Path


def write_text_pdf(path: Path, lines: list[str]) -> None:
    """Create a standards-valid PDF containing plain text lines.

    Used only when ReportLab cannot render a document. A real PDF is required
    here: text written to a file called ``.pdf`` is corrupt to every viewer.
    """
    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    wrapped: list[str] = []
    for line in lines:
        text = str(line or "")
        if not text:
            wrapped.append("")
            continue
        while len(text) > 92:
            split_at = text.rfind(" ", 0, 93)
            split_at = split_at if split_at > 0 else 92
            wrapped.append(text[:split_at])
            text = text[split_at:].lstrip()
        wrapped.append(text)

    pages = [wrapped[index:index + 48] for index in range(0, len(wrapped), 48)] or [[""]]
    objects: list[bytes] = []
    page_object_numbers = [5 + index * 2 for index in range(len(pages))]
    content_object_numbers = [4 + index * 2 for index in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page, content_number in zip(pages, content_object_numbers):
        commands = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
        for line in page:
            commands.extend((f"({escape(line)}) Tj", "T*"))
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", "replace")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>".encode("ascii"))

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    path.write_bytes(bytes(output))
