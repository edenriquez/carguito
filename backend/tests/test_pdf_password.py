"""Password-protected PDF uploads: the 422 handshake and the happy path.

Bank e-statements in Mexico (Banamex nómina among them) routinely ship
encrypted. The upload endpoint answers with a machine-readable ``code`` so the
web client knows whether to *ask* for a password or to say the one it sent was
wrong — two different sentences to a person.
"""

import io

from carguito.adapters.outbound.extraction import PdfExtractor
from carguito.application.ports.outbound import PdfPasswordError

from .conftest import PDF_PASSWORD


def _post_pdf(client, data: bytes, password: str | None = None):
    form: dict = {"file": (io.BytesIO(data), "estado_de_cuenta.pdf")}
    if password is not None:
        form["password"] = password
    return client.post("/api/statements", data=form, content_type="multipart/form-data")


def test_upload_without_password_names_the_ask(client, encrypted_pdf_bytes):
    resp = _post_pdf(client, encrypted_pdf_bytes)
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["code"] == "pdf_password_required"


def test_upload_with_wrong_password_names_the_rejection(client, encrypted_pdf_bytes):
    resp = _post_pdf(client, encrypted_pdf_bytes, password="not-it")
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "pdf_password_incorrect"


def test_upload_with_correct_password_processes(client, encrypted_pdf_bytes):
    resp = _post_pdf(client, encrypted_pdf_bytes, password=PDF_PASSWORD)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["statement_id"]
    # The file parsed like any other statement once opened.
    assert client.get("/api/statements").get_json()["total"] == 1


def test_rejected_upload_leaves_no_statement_behind(client, encrypted_pdf_bytes):
    """A 422 must not burn the content hash: the retry with the right password
    is the same bytes, and it has to be allowed in."""
    assert _post_pdf(client, encrypted_pdf_bytes).status_code == 422
    assert client.get("/api/statements").get_json()["total"] == 0
    assert _post_pdf(client, encrypted_pdf_bytes, password=PDF_PASSWORD).status_code == 201


def test_extractor_distinguishes_missing_from_wrong(encrypted_pdf_bytes):
    extractor = PdfExtractor()
    for password, reason in ((None, "required"), ("not-it", "incorrect")):
        try:
            extractor.extract(encrypted_pdf_bytes, "e.pdf", "application/pdf", password=password)
            raise AssertionError("expected PdfPasswordError")
        except PdfPasswordError as err:
            assert err.reason == reason

    doc = extractor.extract(
        encrypted_pdf_bytes, "e.pdf", "application/pdf", password=PDF_PASSWORD
    )
    assert "COMPRA OXXO" in doc.text
