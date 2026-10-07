from __future__ import annotations

import logging

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from ....application.ports.outbound import PdfPasswordError
from ....application.use_cases.process_file import (
    DuplicateStatementError,
    UnsupportedFileError,
)
from ....application.use_cases.statements import StatementNotFoundError
from ....application.use_cases.tags import TagNotFoundError
from ....application.use_cases.update_transaction import TransactionNotFoundError
from .auth import AuthError

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AuthError)
    def _auth(err: AuthError):
        return jsonify(error=str(err)), 401

    @app.errorhandler(DuplicateStatementError)
    def _dup(err: DuplicateStatementError):
        return jsonify(error="This file was already processed", detail=str(err)), 409

    @app.errorhandler(UnsupportedFileError)
    def _unsupported(err: UnsupportedFileError):
        return jsonify(error="Unsupported file type", detail=str(err)), 415

    @app.errorhandler(PdfPasswordError)
    def _pdf_password(err: PdfPasswordError):
        # 422 with a machine-readable code: the file itself is fine, the
        # request just lacks (or mis-states) the password, and the client
        # needs to know which of the two to say to the user.
        return (
            jsonify(
                error="This PDF is password-protected",
                code=f"pdf_password_{err.reason}",
                detail=str(err),
            ),
            422,
        )

    @app.errorhandler(StatementNotFoundError)
    def _statement_missing(err: StatementNotFoundError):
        return jsonify(error="Statement not found", detail=str(err)), 404

    @app.errorhandler(TransactionNotFoundError)
    def _transaction_missing(err: TransactionNotFoundError):
        return jsonify(error="Transaction not found", detail=str(err)), 404

    @app.errorhandler(TagNotFoundError)
    def _tag_missing(err: TagNotFoundError):
        # 404 rather than 403 for another user's tag, same non-disclosure
        # reasoning as the statement and transaction handlers above.
        return jsonify(error="Tag not found", detail=str(err)), 404

    # `UnknownCategoryError` deliberately has no handler of its own: it is a
    # ValueError and the 400 below is the right answer. The transaction was
    # found; the *category* the client named does not exist.
    @app.errorhandler(ValueError)
    def _value(err: ValueError):
        return jsonify(error="Bad request", detail=str(err)), 400

    @app.errorhandler(HTTPException)
    def _http(err: HTTPException):
        # Must be registered explicitly: the Exception catch-all below would
        # otherwise swallow werkzeug's own 404/405/413 and report them as 500s.
        return jsonify(error=err.name, detail=err.description), err.code

    @app.errorhandler(Exception)
    def _unexpected(err: Exception):  # pragma: no cover - safety net
        logger.exception("Unhandled error")
        return jsonify(error="Internal server error"), 500
