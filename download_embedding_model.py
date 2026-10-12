"""
Downloads the pretrained MobileNetV2 (ImageNet) ONNX weights used for
Lost & Found image embeddings (Phase 4). One-time, ~14 MB, from the
official onnx/models repository. If you skip this, the system
automatically uses the offline HSV histogram embedding fallback.

Run:  python download_embedding_model.py
"""
import urllib.request
from pathlib import Path

URL = "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv2-7.onnx"
DEST = Path(__file__).resolve().parent / "app" / "static" / "models" / "mobilenetv2-7.onnx"


def main():
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists() and DEST.stat().st_size > 1_000_000:
        print(f"Model already present: {DEST}")
        return
    print("Downloading pretrained MobileNetV2 embedding model (~14 MB)...")
    try:
        urllib.request.urlretrieve(URL, DEST)
        print(f"Saved to {DEST} ({DEST.stat().st_size / 1e6:.1f} MB)")
        print("New reports will now use CNN embeddings; existing ones keep their stored vectors.")
    except Exception as e:
        print(f"Download failed: {e}")
        print("The offline HSV histogram fallback remains fully functional.")


if __name__ == "__main__":
    main()
