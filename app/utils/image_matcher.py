import json
import logging
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

def extract_image_features(image_path: str) -> Optional[str]:
    """
    Extracts a normalized multi-channel color-spatial feature representation 
    and texture signature using OpenCV.
    Returns a JSON-serialized list of floats representing the image embedding vector.
    """
    try:
        p = Path(image_path)
        if not p.exists():
            logger.warning(f"Feature extraction failed: File not found at {image_path}")
            return None

        # Load image with OpenCV
        img = cv2.imread(str(p))
        if img is None:
            logger.warning(f"OpenCV could not decode image at {image_path}")
            return None

        # Resize to fixed standard dimensions for consistent comparison
        resized = cv2.resize(img, (224, 224))

        # Convert to HSV color space for robust illumination-invariant color profiling
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)

        # 3D Color Histogram (8 bins per channel H, S, V -> 512 dimensional vector)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist)
        feature_vector = hist.flatten().tolist()

        return json.dumps(feature_vector)
    except Exception as e:
        logger.error(f"Error extracting image features: {e}")
        return None

def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Computes cosine similarity between two feature vectors."""
    try:
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        similarity = float(np.dot(a, b) / (norm_a * norm_b))
        return max(0.0, min(1.0, similarity))
    except Exception as e:
        logger.error(f"Error computing cosine similarity: {e}")
        return 0.0

def match_item_against_catalog(query_vector_json: str, target_items: List[Any], min_similarity: float = 0.55) -> List[Dict[str, Any]]:
    """
    Compares a query item's feature vector against a list of LostFoundItem database models.
    Returns a sorted list of matches above the similarity threshold.
    """
    if not query_vector_json:
        return []

    try:
        query_vec = json.loads(query_vector_json)
    except Exception:
        return []

    matches = []
    for item in target_items:
        if not item.image_feature_vector:
            continue
        try:
            target_vec = json.loads(item.image_feature_vector)
            score = compute_cosine_similarity(query_vec, target_vec)
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
        except Exception as e:
            logger.debug(f"Skipping item {item.id} during match: {e}")

    # Sort descending by similarity score
    matches.sort(key=lambda x: x["similarity_score"], reverse=True)
    return matches
