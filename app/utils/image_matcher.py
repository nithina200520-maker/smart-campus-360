"""
PHASE 5 AI MATCHING ENGINE - Smart Campus 360 Lost & Found.

Embedding strategy (pluggable, graceful degradation):
  1. PREFERRED - Pretrained ImageNet MobileNetV2 convolutional network executed
     locally with OpenCV DNN (app/static/models/mobilenetv2-7.onnx). Run
     `python download_embedding_model.py` once to fetch the weights (~14 MB).
  2. FALLBACK  - Normalized multi-channel HSV color-spatial histogram embedding
     (works fully offline; used automatically when the pretrained model or
     OpenCV decoding is unavailable).

Phase 5 improvements over the Phase 4 engine:
  * Preprocessing pipeline - object-focused salient crop, grey-world white
    balance and CLAHE local-contrast normalization before embedding, so the
    same object photographed under different lighting/backgrounds scores closer.
  * Spatially partitioned fallback histogram (global + 4 quadrants) for richer
    colour-layout signatures while remaining 512-dim and comparable with the
    legacy Phase 1/4 vectors already stored in the database.
  * A text-similarity signal (title + description token Jaccard) folded into
    the contextual blend, plus deterministic confidence bands.
  * Duplicate-report detection for the same user re-reporting one item.
  * `analyze_image_against_registry()` - the read-only diagnostic path used by
    the Main Admin AI testing lab and the evaluation harness.

Embeddings are stored as {"model", "vector", "pre"} so legacy bare-list vectors
remain comparable and mixed-model cosine comparisons are never performed.
Composite scores are decision SUPPORT only - they are explicitly NOT proof of
ownership (verified by authorized staff). Measured accuracy numbers exist only
in evaluation reports produced by `evaluate_matcher.py` - never hard-coded.
"""
import json
import logging
import re
import time
import cv2
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

HISTOGRAM_MODEL = "hsv_histogram"
CNN_MODEL = "mobilenetv2_imagenet"
CNN_MODEL_PATH = Path(__file__).resolve().parent.parent / "static" / "models" / "mobilenetv2-7.onnx"
PREPROCESS_VERSION = "sc360-ph5-crop-wb-clahe"

# Defaults; the app overrides these through config values LF_MATCH_MIN_COMPOSITE,
# LF_STRONG_MATCH_SCORE, LF_MEDIUM_MATCH_SCORE and LF_DUPLICATE_SCORE.
DEFAULT_MIN_COMPOSITE = 0.35
DEFAULT_STRONG_MATCH = 0.70
DEFAULT_MEDIUM_MATCH = 0.50
DEFAULT_DUPLICATE_SCORE = 0.65
DUPLICATE_WINDOW_DAYS = 14

_COLOR_TOKENS = re.compile(
    r'\b(black|white|red|blue|green|yellow|orange|pink|purple|brown|grey|gray|silver|golden|gold|maroon|beige|tan|navy|cream)\b'
)
_LOCATION_STOPWORDS = {'the', 'near', 'beside', 'behind', 'in', 'at', 'on', 'of', 'a', 'an', 'and', 'block', 'campus'}
_TEXT_STOPWORDS = _LOCATION_STOPWORDS | {
    'to', 'for', 'with', 'from', 'is', 'was', 'were', 'be', 'been', 'my', 'me', 'mine',
    'it', 'this', 'that', 'there', 'here', 'have', 'has', 'had', 'i', 'the item',
}

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


def cnn_available() -> bool:
    """Diagnostics for the AI lab: is the pretrained CNN embedding path active?"""
    return _get_cnn_net() is not None


# ---------------------------------------------------------------------------
# PHASE 5: IMAGE PREPROCESSING
# ---------------------------------------------------------------------------

def _preprocess_image(img) -> Tuple[Any, Dict[str, bool]]:
    """
    Improves embedding stability for phone photos of lost items:
      1. Salient crop   - keeps the region around the dominant edges (the object)
                          instead of the whole frame, shrinking background noise.
      2. White balance  - grey-world assumption removes colour cast from indoor
                          campus lighting (yellow corridors, canteen bulbs).
      3. CLAHE          - local contrast normalization on the LAB lightness band
                          so shadows/overexposure do not dominate the embedding.
    Every step is individually guarded; on failure the raw image is returned.
    """
    info = {"cropped": False, "white_balance": False, "clahe": False}
    try:
        h, w = img.shape[:2]
        if h < 32 or w < 32:
            return img, info

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 40, 140)
        edges = cv2.dilate(edges, np.ones((9, 9), np.uint8))
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            areas = [cv2.contourArea(c) for c in contours]
            keep = [c for c, a in zip(contours, areas) if a >= max(areas) * 0.15]
            rx, ry, rw, rh = cv2.boundingRect(np.vstack(keep))
            margin = int(max(rw, rh) * 0.08)
            x0, y0 = max(0, rx - margin), max(0, ry - margin)
            x1, y1 = min(w, rx + rw + margin), min(h, ry + rh + margin)
            crop = img[y0:y1, x0:x1]
            if (crop.shape[0] * crop.shape[1] >= 0.05 * h * w) and min(crop.shape[:2]) >= 32:
                img = crop
                info["cropped"] = True

        means = cv2.mean(img)[:3]
        avg = (means[0] + means[1] + means[2]) / 3.0
        if avg > 1:
            scales = [min(2.0, max(0.5, avg / m)) if m > 1 else 1.0 for m in means]
            img = cv2.merge([
                np.clip(img[:, :, i].astype(np.float32) * scales[i], 0, 255).astype(np.uint8)
                for i in range(3)
            ])
            info["white_balance"] = True

        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        info["clahe"] = True
    except Exception as e:
        logger.warning(f"Preprocessing degraded to raw image: {e}")
    return img, info


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
    """
    Phase 5 spatial histogram: the mean of one global and four quadrant HSV
    histograms (each 8x8x8, L2-normalized). Still 512 dimensions, so vectors
    stay directly comparable with legacy Phase 1/4 embeddings in the database.
    """
    resized = cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)

    def hist(region):
        h = cv2.calcHist([region], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
        cv2.normalize(h, h)
        return h.flatten()

    qh, qw = 112, 112
    parts = [hist(hsv),
             hist(hsv[:qh, :qw]), hist(hsv[:qh, qw:]),
             hist(hsv[qh:, :qw]), hist(hsv[qh:, qw:])]
    vec = np.mean(parts, axis=0)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.flatten().tolist()


def _embed_image(img) -> Tuple[str, List[float], Dict[str, bool]]:
    """Shared core: preprocess, then CNN embedding with histogram fallback."""
    prepared, pre_info = _preprocess_image(img)
    vector = _cnn_embedding(prepared)
    if vector is not None:
        return CNN_MODEL, vector, pre_info
    return HISTOGRAM_MODEL, _histogram_embedding(prepared), pre_info


def extract_image_features(image_path: str) -> Optional[str]:
    """
    Generates an image embedding for similarity matching.
    Prefers the pretrained MobileNetV2 CNN; falls back to the HSV histogram.
    Returns a JSON string {"model", "vector", "pre"} or None on failure.
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

        model, vector, _ = _embed_image(img)
        return json.dumps({"model": model, "vector": vector, "pre": PREPROCESS_VERSION})
    except Exception as e:
        logger.error(f"Error extracting image features: {e}")
        return None


def load_embedding(serialized: Optional[str]) -> Tuple[Optional[str], Optional[List[float]]]:
    """Parses Phase-1 bare-list vectors and Phase-4/5 {"model","vector",...} dicts."""
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
# PHASE 4/5: CONTEXTUAL SIGNAL EXTRACTION
# ---------------------------------------------------------------------------

def extract_colors(text: str) -> set:
    return {m.lower() for m in _COLOR_TOKENS.findall((text or '').lower())}


def _word_tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", (text or '').lower()) if t not in _TEXT_STOPWORDS}


def text_similarity(item_a, item_b) -> float:
    """Jaccard token overlap over title + colour + description (free-text metadata)."""
    ta = _word_tokens(f"{item_a.title or ''} {item_a.color_hint or ''} {item_a.description or ''}")
    tb = _word_tokens(f"{item_b.title or ''} {item_b.color_hint or ''} {item_b.description or ''}")
    if not ta or not tb:
        return 0.0
    return round(len(ta & tb) / len(ta | tb), 3)


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


def days_apart(item_a, item_b) -> float:
    da, db = item_a.date_time_reported, item_b.date_time_reported
    if not da or not db:
        return 9999.0
    return round(abs((da - db).total_seconds()) / 86400.0, 2)


def location_score(item_a, item_b) -> float:
    """Jaccard token overlap of reported locations (campus-aware)."""
    def tokens(text):
        return {t for t in re.findall(r"[a-z]+", (text or '').lower()) if t not in _LOCATION_STOPWORDS}
    ta, tb = tokens(item_a.location_reported), tokens(item_b.location_reported)
    if not ta or not tb:
        return 0.0
    return round(len(ta & tb) / len(ta | tb), 3)


def context_factors(item_a, item_b) -> Dict[str, float]:
    """Phase 5 weighted contextual signals (category 32%, colour 20%, date 18%,
    location 18%, free text 12%). The 'text' key is additive for stored factors."""
    f = {
        "category": category_score(item_a, item_b),
        "colour": color_score(item_a, item_b),
        "date_proximity": date_score(item_a, item_b),
        "location": location_score(item_a, item_b),
        "text": text_similarity(item_a, item_b),
    }
    f["blended"] = round(
        0.32 * f["category"] + 0.20 * f["colour"] + 0.18 * f["date_proximity"]
        + 0.18 * f["location"] + 0.12 * f["text"], 3)
    return f


def confidence_band(composite: float,
                    strong: float = DEFAULT_STRONG_MATCH,
                    medium: float = DEFAULT_MEDIUM_MATCH) -> str:
    """Threshold-labelled confidence band shown to reviewers (never a raw % claim)."""
    if composite >= strong:
        return "high"
    if composite >= medium:
        return "medium"
    return "possible"


def rank_matches(query_item, candidate_items, min_composite: float = DEFAULT_MIN_COMPOSITE,
                 limit: int = 10, strong: float = DEFAULT_STRONG_MATCH,
                 medium: float = DEFAULT_MEDIUM_MATCH) -> List[Dict[str, Any]]:
    """
    Ranks potential counterparts by blending the image embedding cosine score
    with contextual signals (category/colour/date/location/text).
    Phase 5 weighting:
      * image + context : 0.60 * image + 0.40 * blended context
      * context only    : capped at 0.75 * blended (free-text alone is weak proof)
    Ties are broken deterministically by date proximity, then image score.
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
            composite = round(0.60 * image_score + 0.40 * factors["blended"], 3)
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
                "days_apart": days_apart(query_item, item),
                "image_score": round(image_score, 3),
                "text_score": factors["text"],
                "composite_score": composite,
                "similarity_score": round(image_score, 3),
                "confidence_decimal": composite,
                "confidence_band": confidence_band(composite, strong, medium),
                "factors": factors,
                "embedding_model": q_model or "none",
            })
    results.sort(key=lambda x: (x["composite_score"], x["days_apart"] * -1, x["image_score"]),
                 reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# PHASE 5: DUPLICATE REPORT DETECTION
# ---------------------------------------------------------------------------

def duplicate_score(item_a, item_b) -> Dict[str, float]:
    """
    Scoring used when the SAME user re-reports what looks like the same item.
    Signals: free-text overlap, image embedding cosine, colour overlap.
    """
    text = text_similarity(item_a, item_b)
    a_model, a_vec = load_embedding(item_a.image_feature_vector)
    b_model, b_vec = load_embedding(item_b.image_feature_vector)
    image = 0.0
    if a_vec and b_vec and a_model == b_model:
        image = compute_cosine_similarity(a_vec, b_vec)
    colour = color_score(item_a, item_b)
    score = round(0.55 * text + 0.30 * image + 0.15 * colour, 3)
    return {"score": score, "text": round(text, 3), "image": round(image, 3), "colour": round(colour, 3)}


def find_duplicate_report(new_item, existing_items,
                          min_score: float = DEFAULT_DUPLICATE_SCORE,
                          max_days: int = DUPLICATE_WINDOW_DAYS) -> Optional[Dict[str, Any]]:
    """
    Detects a duplicate of an earlier report by the same user. A candidate must:
      * belong to the same reporter and same report type (lost/found),
      * share the category,
      * be within `max_days` of the new report,
      * and satisfy: combined score >= min_score with a strong primary signal
        (text overlap >= 0.45 OR image cosine >= 0.85).
    Returns the best-matching earlier report's details, or None.
    """
    best = None
    for cand in existing_items:
        if cand.id == new_item.id:
            continue
        if cand.user_id != new_item.user_id or cand.report_type != new_item.report_type:
            continue
        if (cand.category or '') != (new_item.category or ''):
            continue
        if days_apart(new_item, cand) > max_days:
            continue
        s = duplicate_score(new_item, cand)
        if s["score"] >= min_score and (s["text"] >= 0.45 or s["image"] >= 0.85):
            if best is None or s["score"] > best["score"]:
                best = {
                    "item_id": cand.id,
                    "title": cand.title,
                    "score": s["score"],
                    "signals": s,
                }
    return best


# ---------------------------------------------------------------------------
# PHASE 5: READ-ONLY QUERY PROXY + LAB / EVALUATION ANALYSIS
# ---------------------------------------------------------------------------

@dataclass
class QueryItem:
    """
    Lightweight stand-in for a LostFoundItem used by the AI testing lab and the
    evaluation harness. Nothing is written to the database; rank/duplicate
    functions only read the attributes below.
    """
    id: int = 0
    user_id: Optional[int] = None
    report_type: str = 'lost'
    title: str = ''
    category: str = 'Other'
    location_reported: str = ''
    date_time_reported: datetime = field(default_factory=datetime.utcnow)
    description: str = ''
    color_hint: Optional[str] = None
    photo_url: Optional[str] = None
    image_feature_vector: Optional[str] = None


def analyze_image_against_registry(image_path: str, meta: Dict[str, Any],
                                  candidate_items: List[Any],
                                  min_composite: float = DEFAULT_MIN_COMPOSITE,
                                  limit: int = 10,
                                  strong: float = DEFAULT_STRONG_MATCH,
                                  medium: float = DEFAULT_MEDIUM_MATCH) -> Dict[str, Any]:
    """
    Diagnostic, read-only pipeline for the Main Admin AI testing lab:
    preprocess -> embed -> rank -> report everything it observed, including
    explicit error strings. Never mutates the database.
    """
    started = time.perf_counter()
    out: Dict[str, Any] = {
        "ok": False, "error": None, "preprocessing": None, "embedding": None,
        "ranked": [], "candidates_evaluated": len(candidate_items), "elapsed_ms": None,
    }
    try:
        p = Path(image_path)
        if not p.exists():
            out["error"] = f"Image file not found: {image_path}"
            return out
        img = cv2.imread(str(p))
        if img is None:
            out["error"] = "OpenCV could not decode the uploaded file as an image."
            return out

        model, vector, pre_info = _embed_image(img)
        serialized = json.dumps({"model": model, "vector": vector, "pre": PREPROCESS_VERSION})
        out["preprocessing"] = {**pre_info, "version": PREPROCESS_VERSION}
        out["embedding"] = {
            "model": model,
            "dimensions": len(vector),
            "cnn_active": model == CNN_MODEL,
            "l2_norm": round(float(np.linalg.norm(np.array(vector, dtype=np.float32))), 4),
        }

        proxy = QueryItem(
            id=0,
            user_id=meta.get("user_id"),
            report_type=meta.get("report_type", "lost"),
            title=meta.get("title", ""),
            category=meta.get("category", "Other"),
            location_reported=meta.get("location_reported", ""),
            date_time_reported=meta.get("date_time_reported") or datetime.utcnow(),
            description=meta.get("description", ""),
            color_hint=meta.get("color_hint"),
            image_feature_vector=serialized,
        )
        out["ranked"] = rank_matches(proxy, candidate_items, min_composite=min_composite,
                                     limit=limit, strong=strong, medium=medium)
        out["ok"] = True
    except Exception as e:
        logger.error(f"Lab analysis failed: {e}")
        out["error"] = f"Analysis error: {e}"
    finally:
        out["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return out


# ---------------------------------------------------------------------------
# LEGACY + SECURITY HELPERS
# ---------------------------------------------------------------------------

def match_item_against_catalog(query_vector_json: str, target_items: List[Any],
                               min_similarity: float = 0.55) -> List[Dict[str, Any]]:
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
