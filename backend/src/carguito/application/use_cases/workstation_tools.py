"""What the model may ask of a lens, beyond what the brief already says.

The brief hands the model a profile, a monthly series, a weekday histogram and
the movements themselves -- up to a cap, because a rule that matches five
thousand rows should not turn one question into a five-thousand-row prompt.
Everything past the cap, and every sum or grouping the brief did not
precompute, is reached through these three functions instead.

Every figure they return is computed here, in ``Decimal``, over the same rows
the brief was built from. That is the point: the model gets to *ask* for a
total, never to produce one. It is the same posture the brief takes with the
weekday histogram, extended to whatever the user thinks to ask next.
"""

from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Any

from ..ports.outbound.chat import ChatTool

#: (ISO date, label, amount as text) -- the shape ``AnswerWorkstationQuestion``
#: already collects for the brief.
Row = tuple[str, str, str]

#: The most movements one search returns. Past this the model is not reading,
#: it is re-dumping the brief; it should group instead.
MAX_SEARCH = 200
DEFAULT_SEARCH = 50
MAX_GROUPS = 100
DEFAULT_GROUPS = 50

_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

_FILTER_PROPERTIES: dict[str, Any] = {
    "contiene": {
        "type": "string",
        "description": "Texto que debe aparecer en la descripción (sin distinguir acentos ni mayúsculas).",
    },
    "desde": {"type": "string", "description": "Fecha inicial inclusive, aaaa-mm-dd."},
    "hasta": {"type": "string", "description": "Fecha final inclusive, aaaa-mm-dd."},
    "monto_min": {"type": "number", "description": "Monto mínimo inclusive, en pesos."},
    "monto_max": {"type": "number", "description": "Monto máximo inclusive, en pesos."},
}

TOOLS: list[ChatTool] = [
    ChatTool(
        name="buscar_movimientos",
        description=(
            "Lista movimientos del conjunto que cumplan filtros de texto, fecha o monto. "
            "Devuelve cuántos coinciden, su total, y hasta `limite` de ellos. Úsala cuando "
            "la lista del resumen esté truncada o necesites ver movimientos concretos."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                **_FILTER_PROPERTIES,
                "orden": {
                    "type": "string",
                    "enum": ["fecha_desc", "fecha_asc", "monto_desc", "monto_asc"],
                    "description": "Orden de los movimientos devueltos. Por defecto fecha_desc.",
                },
                "limite": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_SEARCH,
                    "description": f"Cuántos devolver. Por defecto {DEFAULT_SEARCH}.",
                },
            },
        },
    ),
    ChatTool(
        name="agrupar_movimientos",
        description=(
            "Agrupa los movimientos del conjunto (opcionalmente filtrados) y devuelve por "
            "grupo: cuántos son, cuánto suman y el promedio. Úsala para cualquier suma, "
            "conteo o comparación entre comercios, días, semanas o meses: nunca sumes a mano."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["por"],
            "properties": {
                "por": {
                    "type": "string",
                    "enum": ["descripcion", "dia", "semana", "mes", "dia_semana"],
                    "description": "Criterio de agrupación.",
                },
                **_FILTER_PROPERTIES,
                "limite": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_GROUPS,
                    "description": f"Cuántos grupos devolver. Por defecto {DEFAULT_GROUPS}.",
                },
            },
        },
    ),
    ChatTool(
        name="resumen_de_periodo",
        description=(
            "Perfil de los movimientos que cumplan los filtros: cuántos, total, promedio, "
            "mediana, mínimo, máximo, primer y último movimiento. Úsala para comparar "
            "subperiodos o un comercio contra el conjunto."
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {**_FILTER_PROPERTIES},
        },
    ),
]


class LensTools:
    """The three functions above, bound to one lens's rows."""

    def __init__(self, rows: Sequence[Row]) -> None:
        self._rows = [_Movement.parse(r) for r in rows]

    @property
    def specs(self) -> list[ChatTool]:
        return TOOLS

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Run one tool; the answer is JSON the model reads. Raises on a bad name."""
        if name == "buscar_movimientos":
            result = self.search(arguments)
        elif name == "agrupar_movimientos":
            result = self.group(arguments)
        elif name == "resumen_de_periodo":
            result = self.summary(arguments)
        else:
            raise ValueError(f"herramienta desconocida: {name}")
        return json.dumps(result, ensure_ascii=False)

    # --- the tools -------------------------------------------------------
    def search(self, args: dict[str, Any]) -> dict[str, Any]:
        rows = self._filtered(args)
        order = str(args.get("orden") or "fecha_desc")
        key = (lambda m: m.amount) if order.startswith("monto") else (lambda m: m.day)
        rows.sort(key=key, reverse=order.endswith("desc"))
        limit = _bounded(args.get("limite"), DEFAULT_SEARCH, MAX_SEARCH)
        return {
            "coinciden": len(rows),
            "total": _money(sum((m.amount for m in rows), Decimal(0))),
            "mostrados": min(limit, len(rows)),
            "movimientos": [m.as_json() for m in rows[:limit]],
        }

    def group(self, args: dict[str, Any]) -> dict[str, Any]:
        by = str(args.get("por") or "descripcion")
        if by not in ("descripcion", "dia", "semana", "mes", "dia_semana"):
            raise ValueError(f"criterio desconocido: {by}")
        rows = self._filtered(args)
        buckets: dict[str, list[_Movement]] = defaultdict(list)
        for m in rows:
            buckets[m.bucket(by)].append(m)

        groups = [
            {
                "grupo": label,
                "movimientos": len(members),
                "total": _money(sum((m.amount for m in members), Decimal(0))),
                "promedio": _money(
                    sum((m.amount for m in members), Decimal(0)) / len(members)
                ),
            }
            for label, members in buckets.items()
        ]
        # Time buckets read in order; everything else by weight, heaviest first.
        if by in ("dia", "semana", "mes"):
            groups.sort(key=lambda g: g["grupo"])
        elif by == "dia_semana":
            groups.sort(key=lambda g: _WEEKDAYS.index(g["grupo"]))
        else:
            groups.sort(key=lambda g: Decimal(g["total"]), reverse=True)
        limit = _bounded(args.get("limite"), DEFAULT_GROUPS, MAX_GROUPS)
        return {
            "por": by,
            "movimientos": len(rows),
            "total": _money(sum((m.amount for m in rows), Decimal(0))),
            "grupos_totales": len(groups),
            "grupos": groups[:limit],
        }

    def summary(self, args: dict[str, Any]) -> dict[str, Any]:
        rows = self._filtered(args)
        if not rows:
            return {"movimientos": 0, "nota": "ningún movimiento cumple los filtros"}
        amounts = [m.amount for m in rows]
        days = sorted(m.day for m in rows)
        total = sum(amounts, Decimal(0))
        return {
            "movimientos": len(rows),
            "total": _money(total),
            "promedio": _money(total / len(rows)),
            "mediana": _money(median(amounts)),
            "minimo": _money(min(amounts)),
            "maximo": _money(max(amounts)),
            "primer_movimiento": days[0].isoformat(),
            "ultimo_movimiento": days[-1].isoformat(),
            "dias_cubiertos": (days[-1] - days[0]).days + 1,
        }

    # --- filtering -------------------------------------------------------
    def _filtered(self, args: dict[str, Any]) -> list[_Movement]:
        needle = _fold(str(args.get("contiene") or ""))
        start = _as_date(args.get("desde"))
        end = _as_date(args.get("hasta"))
        low = _as_decimal(args.get("monto_min"))
        high = _as_decimal(args.get("monto_max"))
        out = []
        for m in self._rows:
            if needle and needle not in m.folded:
                continue
            if start and m.day < start:
                continue
            if end and m.day > end:
                continue
            if low is not None and m.amount < low:
                continue
            if high is not None and m.amount > high:
                continue
            out.append(m)
        return out


class _Movement:
    __slots__ = ("amount", "day", "folded", "label")

    def __init__(self, day: date, label: str, amount: Decimal) -> None:
        self.day = day
        self.label = label
        self.folded = _fold(label)
        self.amount = amount

    @classmethod
    def parse(cls, row: Row) -> _Movement:
        iso, label, amount = row
        return cls(date.fromisoformat(iso), label, Decimal(amount))

    def as_json(self) -> dict[str, str]:
        return {"fecha": self.day.isoformat(), "descripcion": self.label, "monto": _money(self.amount)}

    def bucket(self, by: str) -> str:
        if by == "descripcion":
            return self.label
        if by == "dia":
            return self.day.isoformat()
        if by == "mes":
            return self.day.strftime("%Y-%m")
        if by == "semana":
            year, week, _ = self.day.isocalendar()
            return f"{year}-W{week:02d}"
        return _WEEKDAYS[self.day.weekday()]


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def _bounded(value: Any, default: int, maximum: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, maximum))


def _as_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as exc:
        raise ValueError(f"fecha inválida {value!r}: usa aaaa-mm-dd") from exc


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError as exc:
        raise ValueError(f"monto inválido {value!r}") from exc


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
