"""Tests for the stdlib docx/pdf fixture builders."""

import io

import magic
from markitdown import MarkItDown
from pypdf import PdfReader

from chat.evals.target.fixtures import build_docx, build_pdf

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_build_docx_is_sniffed_as_word():
    """libmagic (used by backend-upload) must see a Word document, not a zip."""
    data = build_docx(["Réunion du 3 mars"])

    assert magic.Magic(mime=True).from_buffer(data[:2048]) == DOCX_MIME


def test_build_docx_text_is_extractable():
    """Paragraph text, including accents and XML special chars, survives conversion."""
    data = build_docx(["Décision : budget <validé> & signé", "Responsable : Mme Durand"])

    text = MarkItDown().convert_stream(io.BytesIO(data), file_extension=".docx").text_content

    assert "Décision : budget <validé> & signé" in text
    assert "Responsable : Mme Durand" in text


def test_build_pdf_text_is_extractable():
    """Lines, including French accents and parentheses, are readable by a PDF parser."""
    data = build_pdf(["Compte rendu (réunion n°2)", "Échéance : 15 avril"])

    text = PdfReader(io.BytesIO(data)).get_page(0).extract_text()

    assert data.startswith(b"%PDF-1.4")
    assert "Compte rendu (réunion n°2)" in text
    assert "Échéance : 15 avril" in text
