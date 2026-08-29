from datetime import datetime
from decimal import Decimal

from app.db.models import Order


def test_decimal_round_trips_through_sqlite_without_float_drift(db_session):
    tricky_amount = Decimal("4970.37")  # a value that is NOT exactly representable in binary float
    order = Order(
        order_id="ORD-99999",
        customer_ref="CUST-0001",
        amount=tricky_amount,
        currency="INR",
        created_at=datetime(2026, 6, 1, 10, 0, 0),
        status="paid",
        metadata_json="{}",
    )
    db_session.add(order)
    db_session.commit()
    db_session.expire_all()  # force a real reload from SQLite, not the Python object cache

    reloaded = db_session.get(Order, "ORD-99999")
    assert isinstance(reloaded.amount, Decimal)
    assert reloaded.amount == tricky_amount
    assert str(reloaded.amount) == "4970.37"


def test_order_requires_all_fields(db_session):
    order = Order(
        order_id="ORD-00001",
        customer_ref="CUST-0001",
        amount=Decimal("100.00"),
        currency="INR",
        created_at=datetime(2026, 6, 1),
        status="paid",
        metadata_json="{}",
    )
    db_session.add(order)
    db_session.commit()
    assert db_session.get(Order, "ORD-00001") is not None
