"""
PHASE 7 - Payment gateway abstraction for the Smart Canteen.

Two interchangeable providers implement the same small interface:

* ``SandboxProvider`` - the default. A deterministic in-process gateway used by
  development and the automated test suite. No network calls, no credentials.
  Outcome switches (see Config) let us exercise success / failure / delayed
  (async webhook) payment and refund paths.

* ``StripeProvider``  - the official Stripe Python SDK (https://stripe.com/docs/api).
  Runs in TEST MODE ONLY: a secret key that is not ``sk_test_``/``rk_test_``
  is refused at construction so real money can never move from this code path.

Credentials are read from Flask config (populated from environment / .env only)
and are NEVER rendered into templates or exposed to the frontend.

Webhook payloads are always signature-verified before anything is processed:
 - Stripe: ``stripe.Webhook.construct_event`` with the signing secret.
 - Sandbox: HMAC-SHA256 over the raw body, header ``X-Sandbox-Signature:
   t=<unix_ts>,v1=<hex>`` with replay-window tolerance.
"""
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field

from flask import current_app

SANDBOX_SIGNATURE_HEADER = "X-Sandbox-Signature"


class WebhookVerificationError(Exception):
    """Raised when a webhook payload fails signature verification."""


@dataclass
class IntentResult:
    """Normalised result of creating/confirming a payment intent."""
    status: str                      # 'succeeded' | 'processing' | 'failed'
    intent_id: str = ""
    reference: str = ""              # gateway charge / transaction reference
    client_secret: str = ""          # only ever shown to the paying customer
    failure_reason: str = ""


@dataclass
class RefundResult:
    """Normalised result of a gateway refund initiation."""
    status: str                      # 'succeeded' | 'processing' | 'failed'
    provider_refund_id: str = ""
    message: str = ""


# --------------------------------------------------------------------- sandbox

class SandboxProvider:
    """
    Deterministic local gateway. Intent state lives in our own Payment row,
    so this provider is completely stateless except for the config switches.
    """
    name = "sandbox"

    def _payment_outcome(self):
        return current_app.config.get("PAYMENT_SANDBOX_PAYMENT_OUTCOME", "succeeded")

    def _refund_outcome(self):
        return current_app.config.get("PAYMENT_SANDBOX_REFUND_OUTCOME", "succeeded")

    def create_payment(self, order):
        intent_id = f"sbx_pi_{order.order_code}_{secrets.token_hex(6)}"
        return IntentResult(
            status="created",
            intent_id=intent_id,
            client_secret=f"{intent_id}_secret_{secrets.token_hex(8)}",
        )

    def confirm_payment(self, payment):
        """Backend-side verification of the intent we just created."""
        outcome = self._payment_outcome()
        if outcome == "failed":
            return IntentResult(status="failed", intent_id=payment.intent_id,
                                failure_reason="sandbox_declined (test switch)")
        if outcome == "processing":
            # Async: the payment is only finalised by a signed webhook later.
            return IntentResult(status="processing", intent_id=payment.intent_id)
        return IntentResult(status="succeeded", intent_id=payment.intent_id,
                            reference=f"sbx_ch_{payment.intent_id.split('_')[-1]}")

    def refund(self, payment, amount, reason=""):
        outcome = self._refund_outcome()
        refund_id = f"sbx_re_{secrets.token_hex(8)}"
        if outcome == "failed":
            return RefundResult(status="failed", provider_refund_id=refund_id,
                                message="sandbox refund declined (test switch)")
        if outcome == "processing":
            return RefundResult(status="processing", provider_refund_id=refund_id,
                                message="Bank accepted the refund; settlement is pending")
        return RefundResult(status="succeeded", provider_refund_id=refund_id,
                            message="Refund settled instantly (sandbox)")

    def verify_refund(self, refund):
        """Re-sync a delayed refund; succeeds once the 'bank' has settled it."""
        # The sandbox settles every still-pending refund on first re-sync.
        return RefundResult(status="succeeded", provider_refund_id=refund.provider_refund_id,
                            message="Refund settlement confirmed on re-sync (sandbox)")

    # -- webhook signing helpers (used by tests and the sandbox simulator) ----

    @staticmethod
    def sign_payload(body: bytes, secret: str) -> str:
        ts = int(time.time())
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return f"t={ts},v1={sig}"

    def verify_webhook(self, headers, body: bytes):
        secret = current_app.config["PAYMENT_WEBHOOK_SECRET"]
        header = headers.get(SANDBOX_SIGNATURE_HEADER, "")
        parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
        ts, sig = parts.get("t", "0"), parts.get("v1", "")
        tolerance = current_app.config["PAYMENT_WEBHOOK_TOLERANCE_SECS"]
        if not sig or abs(time.time() - int(ts or 0)) > tolerance:
            raise WebhookVerificationError("Sandbox webhook signature missing, malformed or expired.")
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise WebhookVerificationError("Sandbox webhook signature mismatch.")
        try:
            return json.loads(body)
        except (ValueError, TypeError):
            raise WebhookVerificationError("Sandbox webhook body is not valid JSON.")

    def normalize_event(self, event):
        """Sandbox payloads already use the normalised internal shape."""
        return event


# ---------------------------------------------------------------------- stripe

class StripeProvider:
    """
    Official Stripe SDK, payment-intents + refunds flow, TEST MODE ONLY.
    Docs: https://docs.stripe.com/payments/accept-a-payment?html=python
          https://docs.stripe.com/api/refunds
          https://docs.stripe.com/webhooks#verify-official-libraries
    """
    name = "stripe"

    def __init__(self):
        import stripe  # guarded: only required when PAYMENT_PROVIDER=stripe
        key = current_app.config.get("STRIPE_SECRET_KEY", "")
        if not key:
            raise RuntimeError("PAYMENT_PROVIDER=stripe but STRIPE_SECRET_KEY is not configured.")
        if not (key.startswith("sk_test_") or key.startswith("rk_test_")):
            raise RuntimeError(
                "Refusing to initialise Stripe: only TEST mode (sk_test_*/rk_test_*) keys are "
                "allowed by this integration. Real-money keys must never reach Smart Campus 360.")
        self._stripe = stripe
        self._stripe.api_key = key

    def create_payment(self, order):
        intent = self._stripe.PaymentIntent.create(
            amount=round(float(order.total_amount) * 100),  # paise
            currency=current_app.config["PAYMENT_CURRENCY"],
            metadata={"order_code": order.order_code, "user_id": str(order.user_id)},
            description=f"Smart Campus 360 canteen order {order.order_code}",
        )
        return IntentResult(
            status="created",
            intent_id=intent.id,
            client_secret=intent.client_secret or "",
        )

    def confirm_payment(self, payment):
        intent = self._stripe.PaymentIntent.retrieve(payment.intent_id)
        if intent.status == "succeeded":
            charge_id = intent.latest_charge or ""
            if not charge_id and intent.charges and intent.charges.data:
                charge_id = intent.charges.data[0].id
            return IntentResult(status="succeeded", intent_id=intent.id, reference=str(charge_id))
        # Anything not final stays 'processing': the signed webhook (or a later
        # re-sync) finalises it. Never treat a pending intent as failed - that
        # would release stock and cancel a payment that may still capture.
        if intent.status in ("processing", "requires_confirmation", "requires_action",
                             "requires_payment_method"):
            return IntentResult(status="processing", intent_id=intent.id)
        return IntentResult(
            status="failed", intent_id=intent.id,
            failure_reason=getattr(getattr(intent, "last_payment_error", None), "message", "")
            or f"Stripe intent status: {intent.status}",
        )

    def refund(self, payment, amount, reason=""):
        try:
            refund = self._stripe.Refund.create(
                payment_intent=payment.intent_id,
                amount=round(float(amount) * 100),
                reason="requested_by_customer" if reason else "duplicate",
                metadata={"order_code": payment.order.order_code, "note": (reason or "")[:200]},
            )
        except self._stripe.StripeError as exc:
            return RefundResult(status="failed", message=str(exc))
        status = {"succeeded": "succeeded"}.get(refund.status, "processing")
        return RefundResult(status=status, provider_refund_id=refund.id,
                            message=f"Stripe refund {refund.status}")

    def verify_refund(self, refund):
        obj = self._stripe.Refund.retrieve(refund.provider_refund_id)
        status = {"succeeded": "succeeded", "failed": "failed", "cancelled": "failed"}.get(obj.status, "processing")
        return RefundResult(status=status, provider_refund_id=obj.id, message=f"Stripe refund {obj.status}")

    def verify_webhook(self, headers, body: bytes):
        sig_header = headers.get("Stripe-Signature", "")
        try:
            return self._stripe.Webhook.construct_event(
                body, sig_header, current_app.config["PAYMENT_WEBHOOK_SECRET"])
        except (ValueError, self._stripe.error.SignatureVerificationError) as exc:
            raise WebhookVerificationError(f"Stripe webhook verification failed: {exc}")

    def normalize_event(self, event):
        """
        Map a signature-verified Stripe Event to our normalised shape
        {'id', 'type', 'data'} so one service layer handles every gateway.
        Event types used: payment_intent.succeeded / .payment_failed /
        .processing and charge.refund.updated (docs.stripe.com/webhooks).
        """
        obj = event["data"]["object"] if isinstance(event, dict) else event.data.object
        etype = event["type"] if isinstance(event, dict) else event.type
        eid = event["id"] if isinstance(event, dict) else event.id
        data = {}
        if etype.startswith("payment_intent."):
            data["intent_id"] = obj.id
            if etype == "payment_intent.succeeded":
                ref = getattr(obj, "latest_charge", "") or ""
                if not ref and getattr(obj, "charges", None) and obj.charges.data:
                    ref = obj.charges.data[-1].id
                data["reference"] = str(ref)
            if etype == "payment_intent.payment_failed":
                err = getattr(obj, "last_payment_error", None)
                data["failure_reason"] = (getattr(err, "message", "")
                                          or getattr(err, "code", "")
                                          or "Stripe payment failed")
        elif etype.startswith(("charge.refund.", "refund.")):
            data.update({"provider_refund_id": obj.id, "status": getattr(obj, "status", "")})
        return {"id": eid, "type": etype, "data": data}


# --------------------------------------------------------------------- factory

def get_provider():
    """Return the configured provider instance (per request/app context)."""
    name = current_app.config.get("PAYMENT_PROVIDER", "sandbox")
    if name == "stripe":
        return StripeProvider()
    return SandboxProvider()


def provider_name():
    return current_app.config.get("PAYMENT_PROVIDER", "sandbox")
