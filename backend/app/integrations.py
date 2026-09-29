"""Adapter interfaces for external systems. Nothing here is connected."""
from __future__ import annotations
from typing import Any, Dict, List

INTEGRATION_READY = "Integration-ready"


class BaseAdapter:
    key = "base"
    label = "Base adapter"
    description = ""
    fields_expected: tuple = ()

    def status(self) -> Dict[str, Any]:
        return {"key": self.key, "label": self.label, "description": self.description,
                "status": INTEGRATION_READY, "connected": False,
                "fields_expected": list(self.fields_expected),
                "note": "No credentials or endpoint are configured. DRISHTI does not claim a "
                        "live connection to this system."}

    def fetch(self, *_args, **_kwargs):
        raise NotImplementedError(
            f"{self.label} is {INTEGRATION_READY.lower()} but not connected.")


class ESakshiAdapter(BaseAdapter):
    key = "esakshi"
    label = "eSAKSHI"
    description = "MPLADS work sanction and implementation portal."
    fields_expected = ("work_id", "sanction_order", "revised_cost", "milestones")


class PaimanaAdapter(BaseAdapter):
    key = "paimana"
    label = "PAIMANA"
    description = "Geo-tagged field verification imagery."
    fields_expected = ("work_id", "latitude", "longitude", "photograph_url", "captured_at")


class PaymentLedgerAdapter(BaseAdapter):
    key = "payment_ledger"
    label = "Payment ledger"
    description = "Transaction-level release and payment records."
    fields_expected = ("work_id", "transaction_id", "payee", "amount", "paid_on")


ADAPTERS: List[BaseAdapter] = [ESakshiAdapter(), PaimanaAdapter(), PaymentLedgerAdapter()]
ADAPTERS_BY_KEY = {adapter.key: adapter for adapter in ADAPTERS}


def registry_status() -> Dict[str, Any]:
    return {"integrations": [adapter.status() for adapter in ADAPTERS],
            "note": "Adapters are interfaces only. Connecting them requires official access."}
