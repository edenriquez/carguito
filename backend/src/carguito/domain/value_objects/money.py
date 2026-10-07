from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

DEFAULT_CURRENCY = "MXN"
_CENTS = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Money:
    """An immutable monetary amount with a currency.

    Amounts are stored as :class:`~decimal.Decimal` to avoid float rounding
    errors on financial data.
    """

    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        object.__setattr__(self, "amount", self.amount.quantize(_CENTS, rounding=ROUND_HALF_UP))

    @classmethod
    def of(cls, amount: float | int | str | Decimal, currency: str = DEFAULT_CURRENCY) -> "Money":
        return cls(Decimal(str(amount)), currency)

    def _check(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def abs(self) -> "Money":
        return Money(abs(self.amount), self.currency)

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"
