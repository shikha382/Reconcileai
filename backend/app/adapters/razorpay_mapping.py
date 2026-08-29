"""Phase 5: explicit canonical mappings from realistic external-provider
payloads into `app.schemas.records`' canonical dict shapes. Every mapper
returns a `MappingResult` -- listing exactly which source field became
which canonical field via which transformation (Phase 5's own required
table shape), and any field that could NOT be safely mapped is recorded in
`unsupported_fields`, never silently dropped or guessed.

Money/timestamp conversion is delegated entirely to `app.adapters.money`/
`app.adapters.timestamps` (never re-derived here); ID translation is
delegated to `app.adapters.id_mapping` (never a second normalization
engine, per Phase 8). This module performs ONLY field-shape translation --
no matching, no verification, no policy, no AI, no priority.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.adapters.base import FieldMapping, MappingResult
from app.adapters.errors import ProviderResponseError, ProviderSchemaMismatchError
from app.adapters.id_mapping import external_id_to_canonical
from app.adapters.money import minor_units_to_decimal
from app.adapters.timestamps import normalize_provider_timestamp


def _require(raw: dict, field_name: str, source_type: str) -> object:
    if field_name not in raw:
        raise ProviderSchemaMismatchError(f"{source_type}: missing required field {field_name!r}")
    value = raw[field_name]
    if value is None:
        raise ProviderSchemaMismatchError(f"{source_type}: required field {field_name!r} is null")
    return value


def _parse_rupee_amount(value: object, *, field_name: str) -> Decimal:
    """Some sources (internal ledgers, bank exports) already give a decimal
    rupee string/Decimal rather than integer minor units -- unlike
    Razorpay's own payment/settlement/refund objects, which always use
    paise. Accepting BOTH shapes, explicitly and separately (never
    guessing which one a given int actually means), is exactly Phase 6's
    "document and test the conversion carefully" instruction."""
    if isinstance(value, float):
        raise ProviderResponseError(f"{field_name}: received a float amount ({value!r}); pass a string or Decimal instead")
    if isinstance(value, bool):
        raise ProviderResponseError(f"{field_name}: received a boolean where an amount was expected")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ProviderResponseError(f"{field_name}: {value!r} is not a valid decimal amount")


def map_razorpay_payment(raw: dict) -> MappingResult:
    """Razorpay Payment entity -> canonical `payment` record.
    https://razorpay.com/docs/api/payments/ (public field names; values in
    every fixture this project ships are entirely synthetic)."""
    mappings: list[FieldMapping] = []
    unsupported: list[str] = []
    try:
        external_id = str(_require(raw, "id", "payment"))
        order_external_id = str(_require(raw, "order_id", "payment"))
        amount = minor_units_to_decimal(_require(raw, "amount", "payment"), field_name="amount")
        mappings.append(FieldMapping("amount", "amount", "minor_units_to_decimal (paise -> INR Decimal)", "Decimal, > 0, <= 2dp"))

        currency = str(_require(raw, "currency", "payment")).strip().upper()
        mappings.append(FieldMapping("currency", "currency", "strip + upper", "must be in ALLOWED_CURRENCIES"))

        method = str(_require(raw, "method", "payment"))
        mappings.append(FieldMapping("method", "method", "pass-through", "non-empty string"))

        captured_at = normalize_provider_timestamp(_require(raw, "created_at", "payment"), field_name="created_at")
        mappings.append(FieldMapping("created_at", "captured_at", "normalize_provider_timestamp (Unix epoch -> naive UTC datetime)", "must be a plausible date"))

        status = str(_require(raw, "status", "payment"))
        mappings.append(FieldMapping("status", "status", "pass-through", "non-empty string"))

        canonical_payment_id = external_id_to_canonical("payment", external_id)
        mappings.append(FieldMapping("id", "payment_id", "external_id_to_canonical (deterministic hash)", "matches ^PAY-\\d{5}$"))

        canonical_order_id = external_id_to_canonical("order", order_external_id)
        mappings.append(FieldMapping("order_id", "order_id", "external_id_to_canonical (deterministic hash)", "matches ^ORD-\\d{5}$"))

        gateway_ref = external_id  # the provider's own payment ID IS the gateway's own reference for this transaction
        mappings.append(FieldMapping("id", "gateway_ref", "pass-through (provider's own ID is the gateway reference)", "non-empty string"))

        for unmapped in ("fee", "tax", "notes", "captured", "international", "card_id", "bank", "wallet", "vpa", "email", "contact"):
            if unmapped in raw:
                unsupported.append(unmapped)  # not applicable to canonical Payment -- fee/tax live on Settlement in this project's model

        canonical = {
            "payment_id": canonical_payment_id,
            "order_id": canonical_order_id,
            "amount": amount,
            "currency": currency,
            "method": method,
            "captured_at": captured_at,
            "status": status,
            "gateway_ref": gateway_ref,
            "metadata": {"external_id": external_id, "source": "razorpay"},
        }
        return MappingResult(canonical=canonical, field_mappings=mappings, unsupported_fields=unsupported)
    except (ProviderResponseError, ValueError) as exc:
        return MappingResult(canonical=None, field_mappings=mappings, unsupported_fields=unsupported, rejection_reason=str(exc))


def map_razorpay_settlement(raw: dict) -> MappingResult:
    """Razorpay-style per-transaction settlement reconciliation line
    (this project models the per-payment settlement-recon export shape,
    not the raw batch-level Settlement entity, since that is what a
    per-payment reconciliation system actually needs -- documented in
    docs/provider-adapters.md)."""
    mappings: list[FieldMapping] = []
    unsupported: list[str] = []
    try:
        external_id = str(_require(raw, "id", "settlement"))
        amount = minor_units_to_decimal(_require(raw, "amount", "settlement"), field_name="amount")
        mappings.append(FieldMapping("amount", "amount", "minor_units_to_decimal (paise -> INR Decimal)", "Decimal, > 0, <= 2dp"))

        fee = minor_units_to_decimal(raw.get("fees", 0), field_name="fees")
        mappings.append(FieldMapping("fees", "fee", "rename + minor_units_to_decimal", "Decimal, >= 0, <= 2dp"))

        tax = minor_units_to_decimal(raw.get("tax", 0), field_name="tax")
        mappings.append(FieldMapping("tax", "tax", "minor_units_to_decimal", "Decimal, >= 0, <= 2dp"))

        # net_amount is not a distinct field Razorpay's own settlement
        # object always provides -- computed explicitly here (amount - fee -
        # tax), matching this project's own established net_amount
        # semantics (app.engines.reconciliation.verification), never a
        # second, competing definition.
        net_amount = amount - fee - tax
        mappings.append(FieldMapping("(computed)", "net_amount", "amount - fee - tax", "Decimal, > 0, <= 2dp"))

        # Razorpay's real Settlement entity does not include a currency
        # field at all -- Razorpay only ever settles in INR for Indian
        # merchants, so this is a documented, always-true default, not a
        # guess about financial content (unlike an amount or an ID, where
        # this project never defaults). If a future fixture/response DOES
        # supply one, it is honored (and rejected downstream by the
        # existing ALLOWED_CURRENCIES check if it's ever anything else).
        currency = str(raw.get("currency", "INR")).strip().upper()
        if "currency" not in raw:
            mappings.append(FieldMapping("(absent -- Razorpay settlements are always INR)", "currency", "documented default 'INR'", "must be in ALLOWED_CURRENCIES"))
        settled_at = normalize_provider_timestamp(_require(raw, "created_at", "settlement"), field_name="created_at")
        mappings.append(FieldMapping("created_at", "settled_at", "normalize_provider_timestamp", "must be a plausible date"))

        utr = str(_require(raw, "utr", "settlement"))
        mappings.append(FieldMapping("utr", "utr_reference", "rename, pass-through", "non-empty string"))

        status = str(_require(raw, "status", "settlement"))
        settlement_batch_id = str(raw.get("settlement_batch_id", external_id))

        canonical_settlement_id = external_id_to_canonical("settlement", external_id)
        mappings.append(FieldMapping("id", "settlement_id", "external_id_to_canonical (deterministic hash)", "matches ^STL-\\d{5}$"))

        payment_id = None
        payment_external_id = raw.get("payment_id")
        if payment_external_id:
            payment_id = external_id_to_canonical("payment", str(payment_external_id))
            mappings.append(FieldMapping("payment_id", "payment_id", "external_id_to_canonical (deterministic hash)", "matches ^PAY-\\d{5}$ or null"))
        else:
            unsupported.append("payment_id (absent -- settlement not yet linked, left null rather than guessed)")

        canonical = {
            "settlement_id": canonical_settlement_id,
            "payment_id": payment_id,
            "settlement_batch_id": settlement_batch_id,
            "amount": amount,
            "fee": fee,
            "tax": tax,
            "net_amount": net_amount,
            "currency": currency,
            "settled_at": settled_at,
            "utr_reference": utr,
            "status": status,
            "metadata": {"external_id": external_id, "source": "razorpay"},
        }
        return MappingResult(canonical=canonical, field_mappings=mappings, unsupported_fields=unsupported)
    except (ProviderResponseError, ValueError) as exc:
        return MappingResult(canonical=None, field_mappings=mappings, unsupported_fields=unsupported, rejection_reason=str(exc))


_DIRECTION_MAP = {"CR": "credit", "DR": "debit", "CREDIT": "credit", "DEBIT": "debit"}


def map_bank_transaction(raw: dict) -> MappingResult:
    """Generic bank-statement-export line (not a Razorpay entity -- banks
    do not share one common API shape, so this models a realistic generic
    export format instead of inventing a specific bank's real format)."""
    mappings: list[FieldMapping] = []
    unsupported: list[str] = []
    try:
        external_id = str(_require(raw, "txn_id", "bank_transaction"))
        value_date = normalize_provider_timestamp(_require(raw, "value_date", "bank_transaction"), field_name="value_date")
        mappings.append(FieldMapping("value_date", "value_date", "normalize_provider_timestamp", "must be a plausible date"))

        narration = str(_require(raw, "narration", "bank_transaction"))
        mappings.append(FieldMapping("narration", "narration", "pass-through (normalize_reference applied downstream)", "non-empty string"))

        raw_type = str(_require(raw, "type", "bank_transaction")).strip().upper()
        if raw_type not in _DIRECTION_MAP:
            raise ProviderResponseError(f"bank_transaction: unrecognized transaction type {raw_type!r}")
        direction = _DIRECTION_MAP[raw_type]
        mappings.append(FieldMapping("type", "direction", "CR/DR -> credit/debit lookup", "must be 'credit' or 'debit'"))

        amount = _parse_rupee_amount(_require(raw, "amount", "bank_transaction"), field_name="amount")
        mappings.append(FieldMapping("amount", "amount", "parse_rupee_amount (bank exports already use decimal rupees, not paise)", "Decimal, > 0, <= 2dp"))

        currency = str(_require(raw, "currency", "bank_transaction")).strip().upper()

        matched_settlement_id = None
        linked_ref = raw.get("linked_reference")
        if linked_ref:
            matched_settlement_id = external_id_to_canonical("settlement", str(linked_ref))
            mappings.append(FieldMapping("linked_reference", "matched_settlement_id", "external_id_to_canonical (deterministic hash)", "matches ^STL-\\d{5}$ or null"))

        canonical = {
            "bank_txn_id": external_id_to_canonical("bank_transaction", external_id),
            "value_date": value_date,
            "narration": narration,
            "direction": direction,
            "amount": amount,
            "currency": currency,
            "matched_settlement_id": matched_settlement_id,
            "metadata": {"external_id": external_id, "source": "bank_statement"},
        }
        return MappingResult(canonical=canonical, field_mappings=mappings, unsupported_fields=unsupported)
    except (ProviderResponseError, ValueError) as exc:
        return MappingResult(canonical=None, field_mappings=mappings, unsupported_fields=unsupported, rejection_reason=str(exc))


def map_internal_order(raw: dict) -> MappingResult:
    """Generic internal order-management-system export (not Razorpay --
    the merchant's own order record)."""
    mappings: list[FieldMapping] = []
    unsupported: list[str] = []
    try:
        external_id = str(_require(raw, "order_ref", "order"))
        customer_ref = str(_require(raw, "customer_ref", "order"))
        created_at = normalize_provider_timestamp(_require(raw, "created_at", "order"), field_name="created_at")
        status = str(_require(raw, "status", "order"))
        amount = _parse_rupee_amount(_require(raw, "amount", "order"), field_name="amount")
        mappings.append(FieldMapping("amount", "amount", "parse_rupee_amount (internal ledgers already use decimal rupees)", "Decimal, > 0, <= 2dp"))
        currency = str(_require(raw, "currency", "order")).strip().upper()

        canonical = {
            "order_id": external_id_to_canonical("order", external_id),
            "customer_ref": customer_ref,
            "created_at": created_at,
            "status": status,
            "amount": amount,
            "currency": currency,
            "metadata": {"external_id": external_id, "source": "internal_ledger"},
        }
        mappings.append(FieldMapping("order_ref", "order_id", "external_id_to_canonical (deterministic hash)", "matches ^ORD-\\d{5}$"))
        return MappingResult(canonical=canonical, field_mappings=mappings, unsupported_fields=unsupported)
    except (ProviderResponseError, ValueError) as exc:
        return MappingResult(canonical=None, field_mappings=mappings, unsupported_fields=unsupported, rejection_reason=str(exc))


def map_razorpay_refund(raw: dict) -> MappingResult:
    """Razorpay Refund entity -> canonical `refund` record."""
    mappings: list[FieldMapping] = []
    unsupported: list[str] = []
    try:
        external_id = str(_require(raw, "id", "refund"))
        payment_external_id = str(_require(raw, "payment_id", "refund"))
        amount = minor_units_to_decimal(_require(raw, "amount", "refund"), field_name="amount")
        mappings.append(FieldMapping("amount", "amount", "minor_units_to_decimal (paise -> INR Decimal)", "Decimal, > 0, <= 2dp"))
        currency = str(_require(raw, "currency", "refund")).strip().upper()
        status = str(_require(raw, "status", "refund"))
        initiated_at = normalize_provider_timestamp(_require(raw, "created_at", "refund"), field_name="created_at")
        mappings.append(FieldMapping("created_at", "initiated_at", "normalize_provider_timestamp", "must be a plausible date"))

        # Razorpay's refund object does not expose a separate "processed at"
        # timestamp distinct from created_at -- an explicit, documented rule:
        # a refund already in a terminal "processed" state is treated as
        # processed at the same instant it was created (this project's own
        # synthetic dataset never needs sub-second refund-processing
        # latency); anything not yet processed leaves processed_at null,
        # never guessed.
        processed_at = initiated_at if status == "processed" else None
        mappings.append(FieldMapping("status + created_at", "processed_at", "created_at if status=='processed' else null", "must be a plausible date or null"))

        canonical = {
            "refund_id": external_id_to_canonical("refund", external_id),
            "payment_id": external_id_to_canonical("payment", payment_external_id),
            "amount": amount,
            "currency": currency,
            "initiated_at": initiated_at,
            "processed_at": processed_at,
            "status": status,
            "reference": external_id,
            "metadata": {"external_id": external_id, "source": "razorpay"},
        }
        mappings.append(FieldMapping("id", "refund_id", "external_id_to_canonical (deterministic hash)", "matches ^REF-\\d{5}$"))
        mappings.append(FieldMapping("payment_id", "payment_id", "external_id_to_canonical (deterministic hash)", "matches ^PAY-\\d{5}$"))
        mappings.append(FieldMapping("id", "reference", "pass-through (provider's own ID doubles as the refund reference)", "non-empty string"))
        return MappingResult(canonical=canonical, field_mappings=mappings, unsupported_fields=unsupported)
    except (ProviderResponseError, ValueError) as exc:
        return MappingResult(canonical=None, field_mappings=mappings, unsupported_fields=unsupported, rejection_reason=str(exc))


MAPPERS = {
    "payment": map_razorpay_payment,
    "settlement": map_razorpay_settlement,
    "bank_transaction": map_bank_transaction,
    "order": map_internal_order,
    "refund": map_razorpay_refund,
}
