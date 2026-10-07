from __future__ import annotations

from ....application.ports.outbound.extraction import StatementParser
from ..extraction.classifier import (
    TEMPLATE_BANAMEX,
    TEMPLATE_BANCO_AZTECA,
    TEMPLATE_GENERIC,
    TEMPLATE_SAT_CFDI,
)
from .banamex import BanamexParser
from .banco_azteca import BancoAztecaParser
from .generic_bank import GenericBankParser
from .sat_cfdi import SatCfdiParser


class UnknownTemplateError(Exception):
    """Raised when no parser is registered for a template key."""


class DefaultParserFactory:
    """Maps template keys to parser instances.

    New bank templates are added by registering another parser here, keeping
    the pipeline open for extension without touching the use case.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, StatementParser] = {
            TEMPLATE_SAT_CFDI: SatCfdiParser(),
            TEMPLATE_BANAMEX: BanamexParser(),
            TEMPLATE_BANCO_AZTECA: BancoAztecaParser(),
            TEMPLATE_GENERIC: GenericBankParser(),
        }

    def register(self, template_key: str, parser: StatementParser) -> None:
        self._parsers[template_key] = parser

    def get(self, template_key: str) -> StatementParser:
        parser = self._parsers.get(template_key)
        if parser is None:
            # Fall back to the generic bank parser rather than failing hard.
            fallback = self._parsers.get(TEMPLATE_GENERIC)
            if fallback is None:
                raise UnknownTemplateError(template_key)
            return fallback
        return parser
