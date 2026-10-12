"""
PHASE 4 AI MATCHING ENGINE - Smart Campus 360 Lost & Found.

Embedding strategy (pluggable, graceful degradation):
  1. PREFERRED - Pretrained ImageNet MobileNetV2 convolutional network executed
     locally with OpenCV DNN (app/static/models/mobilenetv2-7.onnx). Run
     `python download_embedding_model.py` once to fetch the weights (~14 MB).
  2. FALLBACK  - Normalized multi-channel HSV color-spatial histogram embedding
     (works fully offline; used automatically when the pretrained model or
     OpenCV decoding is unavailable).

Embeddings are stored as {"model": <name>, "vector": [...]} so legacy bare-list
vectors remain comparable and mixed-model cosine comparisons are never performed.

Contextual ranking blends image similarity with category, colour, date
proximity and location signals. Composite scores are decision SUPPORT only -
they are explicitly NOT proof of ownership (verified by authorized staff).
"""
import json
import logging
import re
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

HISTOGRAM_MODEL = "hsv_histogram"
CNN_MODEL = "mobilenetv2_imagenet"
CNN_MODEL_PATH = Path(__file__).resolve().parent.parent / "static" / "models" / "mobilenetv2-7.onnx"

_COLOR_TOKENS = re.compile(
    r'\b(black|white|red|blue|green|yellow|orange|pink|purple|brown|grey|gray|silver|golden|gold|maroon|beige|tan|navy|cream)\b'
)
_LOCATION_STOPWORDS = {'the', 'near', 'beside', 'behind', 'in', 'at', 'on', 'of', 'a', 'an', 'and', 'block', 'campus'}

_cnn_net_cache = None
_cnn_load_attempted = False


def _get_cnn_net():
    """Lazily load the pretrained MobileNetV2 network (cached per process)."""
    global _cnn_net_cache, _cnn_load_attempted
    if _cnn_load_attempted:
        return _cnn_net_cache
    _cnn_load_attempted = True
    try:
        if CNN_MODEL_PATH.exists():
            _cnn_net_cache = cv2.dnn.readNetFromONNX(str(CNN_MODEL_PATH))
            logger.info("Pretrained MobileNetV2 embedding model loaded.")
    except Exception as e:
        logger.warning(f"Pretrained model load failed ({e}); using histogram fallback.")
    return _cnn_net_cache


def _cnn_embedding(img) -> Optional[List[float]]:
    net = _get_cnn_net()
    if net is None:
        return None
    try:
        blob = cv2.dnn.blobFromImage(
            img, size=(224, 224), mean=[123.675, 116.28, 103.53],
            std=[58.3957, 57.12, 57.375], swapRB=True)
        net.setInput(blob)
        logits = net.forward()
        vec = np.array(logits, dtype=np.float32).flatten()
        norm = np.linalg.norm(vec)
        if norm == 0:
            return None
        return (vec / norm).tolist()
    except Exception as e:
        logger.warning(f"Pretrained embedding failed, falling back to histogram: {e}")
        return None


def _histogram_embedding(img) -> List[float]:
    resized = cv2.resize(img, (224, 224))
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
    cv2.normalize(hist, hist)
    return hist.flatten().tolist()


def extract_image_features(image_path: str) -> Optional[str]:
    """
    Generates an image embedding for similarity matching.
    Prefers the pretrained MobileNetV2 CNN; falls back to the HSV histogram.
    Returns a JSON string {"model": ..., "vector": [...]} or None on failure.
    """
    try:
        p = Path(image_path)
        if not p.exists():
            logger.warning(f"Feature extraction failed: File not found at {image_path}")
            return None

        img = cv2.imread(str(p))
        if img is None:
            logger.warning(f"OpenCV could not decode image at {image_path}")
            return None

        vector = _cnn_embedding(img)
        if vector is not None:
            return json.dumps({"model": CNN_MODEL, "vector": vector})

        return json.dumps({"model": HISTOGRAM_MODEL, "vector": _histogram_embedding(img)})
    except Exception as e:
        logger.error(f"Error extracting image features: {e}")
        return None


def load_embedding(serialized: Optional[str]) -> Tuple[Optional[str], Optional[List[float]]]:
    """Parses both Phase-1 bare-list vectors and Phase-4 {"model","vector"} dicts."""
    if not serialized:
        return None, None
    try:
        data = json.loads(serialized) if isinstance(serialized, str) else serialized
        if isinstance(data, dict):
            return data.get("model", HISTOGRAM_MODEL), data.get("vector")
        if isinstance(data, list):
            return HISTOGRAM_MODEL, data  # legacy Phase 1 vectors
    except Exception:
        pass
    return None, None


def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Computes cosine similarity between two feature vectors."""
    try:
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        if len(a) != len(b):
            return 0.0
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        similarity = float(np.dot(a, b) / (norm_a * norm_b))
        return max(0.0, min(1.0, similarity))
    except Exception as e:
        logger.error(f"Error computing cosine similarity: {e}")
        return 0.0


# ---------------------------------------------------------------------------
# PHASE 4: CONTEXTUAL SIGNAL EXTRACTION
# ---------------------------------------------------------------------------

def extract_colors(text: str) -> set:
    return {m.lower() for m in _COLOR_TOKENS.findall((text or '').lower())}


def category_score(item_a, item_b) -> float:
    return 1.0 if (item_a.category or '') == (item_b.category or '') else 0.0


def color_score(item_a, item_b) -> float:
    a_colors = extract_colors(f"{item_a.color_hint or ''} {item_a.title} {item_a.description}")
    b_colors = extract_colors(f"{item_b.color_hint or ''} {item_b.title} {item_b.description}")
    if not a_colors or not b_colors:
        return 0.0
    overlap = len(a_colors & b_colors) / len(a_colors | b_colors)
    return round(overlap, 3)


def date_score(item_a, item_b) -> float:
    """Linear proximity decay: identical dates = 1.0, 60+ days apart = 0.0."""
    da, db = item_a.date_time_reported, item_b.date_time_reported
    if not da or not db:
        return 0.0
    days = abs((da - db).total_seconds()) / 86400.0
    return round(max(0.0, 1.0 - days / 60.0), 3)


def location_score(item_a, item_b) -> float:
    """Jaccard token overlap of reported locations (campus-aware)."""
    def tokens(text):
        return {t for t in re.findall(r"[a-z]+", (text or '').lower()) if t not in _LOCATION_STOPWORDS}
    ta, tb = tokens(item_a.location_reported), tokens(item_b.location_reported)
    if not ta or not tb:
        return 0.0
    return round(len(ta & tb) / len(ta | tb), 3)


def context_factors(item_a, item_b) -> Dict[str, float]:
    """Weighted contextual signals (category 35%, colour 25%, date 20%, location 20%)."""
    f = {
        "category": category_score(item_a, item_b),
        "colour": color_score(item_a, item_b),
        "date_proximity": date_score(item_a, item_b),
        "location": location_score(item_a, item_b),
    }
    f["blended"] = round(0.35 * f["category"] + 0.25 * f["colour"] + 0.20 * f["date_proximity"] + 0.20 * f["location"], 3)
    return f


def rank_matches(query_item, candidate_items, min_composite: float = 0.35, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Ranks potential counterparts by blending the image embedding cosine score
    with contextual signals. Image + context = 0.65/0.35 when a comparable
    embedding exists; otherwise context-only matches are capped at 0.75 weight
    (text description matches alone are weak evidence).
    """
    q_model, q_vec = load_embedding(query_item.image_feature_vector)
    results = []
    for item in candidate_items:
        if item.id == query_item.id:
            continue
        i_model, i_vec = load_embedding(item.image_feature_vector)
        image_score = 0.0
        if q_vec and i_vec and q_model == i_model:
            image_score = compute_cosine_similarity(q_vec, i_vec)

        factors = context_factors(query_item, item)
        if image_score > 0:
            composite = round(0.65 * image_score + 0.35 * factors["blended"], 3)
        else:
            composite = round(0.75 * factors["blended"], 3)

        if composite >= min_composite:
            results.append({
                "item_id": item.id,
                "title": item.title,
                "category": item.category,
                "location_reported": item.location_reported,
                "photo_url": item.photo_url,
                "date_time_reported": item.date_time_reported.strftime('%Y-%m-%d %H:%M') if item.date_time_reported else "",
                "image_score": round(image_score, 3),
                "composite_score": composite,
                "similarity_score": round(image_score, 3),
                "confidence_decimal": composite,
                "factors": factors,
                "embedding_model": q_model or "none",
            })
    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return results[:limit]


def match_item_against_catalog(query_vector_json: str, target_items: List[Any], min_similarity: float = 0.55) -> List[Dict[str, Any]]:
    """
    Legacy Phase 1 API retained for compatibility: pure image-vector cosine
    comparison against a catalog of LostFoundItem model objects.
    """
    matches = []
    q_model, q_vec = load_embedding(query_vector_json)
    if not q_vec:
        return []
    for item in target_items:
        i_model, i_vec = load_embedding(item.image_feature_vector)
        if not i_vec or i_model != q_model:
            continue
        score = compute_cosine_similarity(q_vec, i_vec)
        if score >= min_similarity:
            matches.append({
                "item_id": item.id,
                "title": item.title,
                "category": item.category,
                "location_reported": item.location_reported,
                "similarity_score": round(score * 100, 1),
                "confidence_decimal": round(score, 3),
                "photo_url": item.photo_url,
                "date_time_reported": item.date_time_reported.strftime('%Y-%m-%d %H:%M') if item.date_time_reported else ""
            })
    matches.sort(key=lambda x: x["similarity_score"], reverse=True)
    return matches


def validate_image_bytes(file_storage) -> bool:
    """Phase 4 SECURITY: verifies true image content by magic bytes, not just extension."""
    try:
        header = file_storage.read(12)
        file_storage.seek(0)
        if len(header) < 12:
            return False
        # PNG / JPEG / WebP(RIFF) / GIF
        if header.startswith(b'\x89PNG\r\n\x1a\n'):
            return True
        if header.startswith(b'\xff\xd8\xff'):
            return True
        if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            return True
        if header[:6] in (b'GIF87a', b'GIF89a'):
            return True
        return False
    except Exception:
        return False
