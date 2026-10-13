import os
import io
import base64
import qrcode
from pathlib import Path
from flask import current_app

# Phase 6: QR pickup payload format. The code alone identifies the order; the
# opaque per-order token is the secret that authorizes handover. No customer
# name, user id, role, or amount is ever encoded in the QR image.
PICKUP_PREFIX = "SC360-PICKUP"

def pickup_qr_payload(order) -> str:
    """Build the privacy-safe QR payload for one order."""
    token = getattr(order, "pickup_token", None)
    if token:
        return f"{PICKUP_PREFIX}:{order.order_code}:{token}"
    # Legacy orders created before Phase 6 have no token; verification then
    # falls back to the plain order code exactly as before.
    return f"{PICKUP_PREFIX}:{order.order_code}"

def parse_pickup_payload(text: str):
    """
    Parse a scanned QR string into (order_code, token_or_None).
    Returns (None, None) for anything not shaped like a pickup payload.
    Accepts a bare order code too (manual entry path).
    """
    if not text:
        return None, None
    text = text.strip()
    if text.startswith(PICKUP_PREFIX + ":"):
        parts = text.split(":")
        if len(parts) == 3 and parts[1]:
            return parts[1].upper(), parts[2]
        if len(parts) == 2 and parts[1]:
            return parts[1].upper(), None
        return None, None
    # Manual entry / legacy scanner: plain order code
    return text.upper(), None

def generate_order_qr(order, save_to_disk=True) -> str:
    """
    Generates a high-resolution QR code encoding the privacy-safe pickup
    payload for one order. Returns the relative web path e.g.
    'uploads/qr_codes/ORD-XXXX.png' and optionally writes it to disk.
    """
    payload = pickup_qr_payload(order)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1e293b", back_color="#ffffff")

    if save_to_disk:
        upload_dir = Path(current_app.root_path) / "static" / "uploads" / "qr_codes"
        upload_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{order.order_code}.png"
        filepath = upload_dir / filename
        img.save(filepath)
        return f"uploads/qr_codes/{filename}"
    else:
        # Return base64 string
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

def get_qr_base64_from_text(data_text: str) -> str:
    """Utility to quickly generate inline base64 QR image for any arbitrary string."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"
