from __future__ import annotations

from enum import Enum


class TxType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class SourceType(str, Enum):
    BANK_PDF = "bank_pdf"
    SAT_XML = "sat_xml"


class StatementSource(str, Enum):
    """How the statement's contents reached the server.

    Not a synonym for :class:`SourceType` (what kind of document it is): this
    records *custody*. ``WEB`` means the raw file was uploaded and read
    server-side, then discarded; ``DEVICE`` means the phone extracted the text
    and the file never left it (docs/custody-plan.md G1/G2). The dashboard says
    different, true things about each, so the difference has to be stored --
    it cannot be re-derived from anything else on the row.
    """

    WEB = "web"
    DEVICE = "device"


class StatementStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class AccountKind(str, Enum):
    """What kind of account a statement describes.

    User-declared, never inferred: the parsers cannot reliably tell a credit
    card statement from a debit one across banks, and a wrong guess would
    poison every metric that later branches on it (credit-card "expenses"
    include payments *to* the card). ``None`` on the entity means "the user
    hasn't said" — an honest unknown, not a default.
    """

    DEBIT = "debit"
    CREDIT = "credit"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    PAYROLL = "payroll"


class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    PENDING = "pending"
