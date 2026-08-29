from app.db.models import BankTransaction, FeeRule, Order, Payment, RawRecord, Refund, Settlement
from app.ingestion.pipeline import ingest_source_directory


def test_ingest_loads_all_300_orders_and_related_records(db_session, dataset_seed_dir):
    report = ingest_source_directory(db_session, dataset_seed_dir)
    db_session.commit()

    assert report.counts["order"] == 300
    assert report.all_valid
    assert db_session.query(Order).count() == 300
    assert db_session.query(Payment).count() == report.counts["payment"]
    assert db_session.query(Settlement).count() == report.counts["settlement"]
    assert db_session.query(BankTransaction).count() == report.counts["bank_transaction"]
    assert db_session.query(Refund).count() == report.counts["refund"]
    assert db_session.query(FeeRule).count() == 3


def test_raw_payload_is_preserved_unmodified_alongside_normalized(db_session, dataset_seed_dir):
    ingest_source_directory(db_session, dataset_seed_dir)
    db_session.commit()

    raw_orders = db_session.query(RawRecord).filter_by(source_type="order").all()
    assert len(raw_orders) == 300
    from shared.money import loads

    sample = raw_orders[0]
    raw_payload = loads(sample.raw_json)
    assert raw_payload["order_id"] == sample.record_ref


def test_reingestion_is_idempotent_no_duplicate_rows(db_session, dataset_seed_dir):
    ingest_source_directory(db_session, dataset_seed_dir)
    db_session.commit()
    first_order_count = db_session.query(Order).count()
    first_raw_count = db_session.query(RawRecord).count()

    ingest_source_directory(db_session, dataset_seed_dir)
    db_session.commit()

    assert db_session.query(Order).count() == first_order_count
    # Raw records are append-only by design (every ingest run is its own
    # audit trail entry) -- so re-running DOES add new raw rows, but must
    # NOT duplicate the typed, upserted entity rows checked above.
    assert db_session.query(RawRecord).count() == first_raw_count * 2


def test_ingested_amounts_are_decimal_and_survive_round_trip(db_session, dataset_seed_dir, small_dataset):
    ingest_source_directory(db_session, dataset_seed_dir)
    db_session.commit()

    sample_order = small_dataset.orders[0]
    reloaded = db_session.get(Order, sample_order["order_id"])
    assert reloaded.amount == sample_order["amount"]
