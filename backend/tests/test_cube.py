from datetime import date
from decimal import Decimal
from uuid import uuid4

from carguito.adapters.outbound.cube import DuckDbCube
from carguito.domain.entities import Category, Transaction
from carguito.domain.value_objects.enums import TxType


def test_cube_summary():
    cube = DuckDbCube(":memory:")
    user = uuid4()
    food = Category(name="Comida")
    cube.sync_categories([food])

    txs = [
        Transaction(user_id=user, tx_date=date(2024, 1, 5), amount=Decimal(100),
                    raw_description="OXXO", tx_type=TxType.EXPENSE, category_id=food.id),
        Transaction(user_id=user, tx_date=date(2024, 1, 6), amount=Decimal(300),
                    raw_description="Walmart", tx_type=TxType.EXPENSE, category_id=food.id),
        Transaction(user_id=user, tx_date=date(2024, 1, 7), amount=Decimal(5000),
                    raw_description="Nomina", tx_type=TxType.INCOME),
    ]
    cube.upsert_transactions(txs)

    summary = cube.spending_summary(user)
    assert summary.total_income == Decimal("5000.00")
    assert summary.total_expense == Decimal("400.00")
    assert summary.top_category == "Comida"
    assert summary.by_category[0].amount == Decimal("400.00")
    assert summary.by_category[0].percentage == 100.0

    monthly = cube.monthly_series(user)
    assert monthly[-1].month == "2024-01"
    assert monthly[-1].expense == Decimal("400.00")


def test_upsert_is_idempotent():
    cube = DuckDbCube(":memory:")
    user = uuid4()
    tx = Transaction(user_id=user, tx_date=date(2024, 1, 5), amount=Decimal(100),
                     raw_description="OXXO", tx_type=TxType.EXPENSE)
    cube.upsert_transactions([tx])
    cube.upsert_transactions([tx])  # same id again
    summary = cube.spending_summary(user)
    assert summary.total_expense == Decimal("100.00")
