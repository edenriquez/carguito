import io

import pytest

from carguito.config.settings import Settings
from carguito.main import create_app


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path/'test.db'}",
        cube_path=":memory:",
        # Per-test keypair, so the suite never mints (or reuses) the real
        # server's ingest key in the repo root.
        ingest_key_path=str(tmp_path / "ingest_key.json"),
        auth_disabled=True,
        # Each test gets a brand-new SQLite file, so create_all lands on the
        # same schema Alembic would build (models.py is the source of truth for
        # both) without paying for the migration history on every test.
        # test_migrations.py exercises the Alembic path itself.
        run_migrations=False,
        # No outbound call from the suite. A test that reaches the Profeco
        # survey is slow, flaky, and red on a laptop with no network — for
        # a reason that has nothing to do with the code under test. The
        # reference port is exercised with a fake, in test_prices.py.
        price_reference_city="",
        listings_source="",
        brave_search_api_key="",
    )
    application = create_app(settings)
    # The app defers bootstrap to the first request (DuckDB single-writer lock
    # vs the dev reloader). Tests may use the container directly without ever
    # issuing a request, so bootstrap eagerly here.
    application.extensions["container"].bootstrap()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


#: Password of the encrypted-PDF fixture below.
PDF_PASSWORD = "carguito123"


def _build_text_pdf(lines: list[str]) -> bytes:
    """A minimal but *valid* one-page PDF (xref and all) with real text.

    Hand-assembled so the suite does not need a PDF-authoring dependency;
    pypdf (dev extra) only encrypts it, which it can do without one.
    """
    content = b"BT /F1 12 Tf 72 720 Td 14 TL\n" + b"".join(
        b"(" + ln.encode("latin-1") + b") Tj T*\n" for ln in lines
    ) + b"ET"
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>stream\n%s\nendstream" % (len(content), content),
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n%s\nendobj\n" % (i, body))
    xref_at = out.tell()
    out.write(b"xref\n0 %d\n" % (len(objs) + 1))
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(
        b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objs) + 1, xref_at)
    )
    return out.getvalue()


@pytest.fixture
def encrypted_pdf_bytes():
    """A password-protected statement-shaped PDF (password: ``PDF_PASSWORD``)."""
    from pypdf import PdfReader, PdfWriter

    plain = _build_text_pdf(
        [
            "BANCO DE PRUEBA Estado de Cuenta",
            "Periodo 01/ENE/2026 al 31/ENE/2026",
            "01/ENE/2026 COMPRA OXXO 123.45",
            "02/ENE/2026 SPEI RECIBIDO NOMINA 500.00",
        ]
    )
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(plain)))
    writer.encrypt(user_password=PDF_PASSWORD, algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.fixture
def sample_cfdi_bytes():
    xml = (
        '<?xml version="1.0"?>'
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        'Total="500.00" Fecha="2024-02-10T09:00:00" TipoDeComprobante="I">'
        '<cfdi:Emisor Nombre="OXXO" Rfc="OXX999999"/>'
        "</cfdi:Comprobante>"
    )
    return io.BytesIO(xml.encode("utf-8"))
