import os
import io
import base64
import json
import qrcode
from pathlib import Path
from flask import current_app

def generate_order_qr(order, save_to_disk=True) -> str:
    """
    Generates a high-resolution QR code encoding order verification data.
    Returns the relative web path e.g. 'uploads/qr_codes/ORD-XXXX.png'
    and optionally writes it to the app's upload directory.
    """
    payload = {
        "order_code": order.order_code,
        "user_id": order.user_id,
        "role": order.user_role_at_order,
        "is_priority": bool(order.is_priority),
        "total_amount": float(order.total_amount),
        "pickup_time": order.pickup_time.strftime('%Y-%m-%d %H:%M') if order.pickup_time else None,
        "college": "GEC Mosalehosahalli"
    }

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(json.dumps(payload))
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
