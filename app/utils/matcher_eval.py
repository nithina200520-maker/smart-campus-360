"""
PHASE 5: MATCHER EVALUATION HARNESS - Smart Campus 360 Lost & Found.

An evaluation procedure for the AI matcher using LABELED test photographs.
Dataset layout (all paths relative to a single root directory):

    <root>/
      gallery/<label>/<photo>.jpg   - known items already "in the system"
      queries/<label>/<photo>.jpg   - new photos to be matched
      metadata.csv                  - OPTIONAL columns:
            path,report_type,title,category,color_hint,location_reported,description

Each query is scored against every gallery image with the production ranking
pipeline (preprocess -> embed -> cosine -> composite). A query counts as a HIT
when the top-ranked gallery image carries the SAME label as the query.

Measured metrics (only ever computed from an actual run - never hard-coded):
    precision_at_1, hit_at_3, hit_at_5, MRR, and a composite-threshold sweep.

This module ships with a deterministic SYNTHETIC sample generator so the
procedure is runnable end-to-end out of the box; synthetic numbers describe
the synthetic set ONLY and must never be presented as real-world accuracy.
"""
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.utils.image_matcher import (
    QueryItem, extract_image_features, load_embedding, compute_cosine_similarity,
    context_factors, rank_matches, DEFAULT_MIN_COMPOSITE,
)

logger = logging.getLogger(__name__)

LABEL_SEPARATOR = "__"  # reserved internally; labels come from folder names


# ---------------------------------------------------------------------------
# Dataset discovery
# ---------------------------------------------------------------------------

def load_labeled_dataset(root: str) -> Dict[str, Any]:
    """Reads queries/<label>/ and gallery/<label>/ folders. Returns split lists."""
    base = Path(root)
    meta = _load_metadata(base)

    def scan(folder: Path) -> List[Dict[str, Any]]:
        entries = []
        if not folder.exists():
            return entries
        for label_dir in sorted(folder.iterdir()):
            if not label_dir.is_dir():
                continue
            label = label_dir.name
            for img in sorted(label_dir.iterdir()):
                if img.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                    continue
                entry = {"label": label, "path": str(img)}
                entry.update(meta.get(str(img.relative_to(base)).replace("\\", "/"), {}))
                entries.append(entry)
        return entries

    return {
        "queries": scan(base / "queries"),
        "gallery": scan(base / "gallery"),
    }


def _load_metadata(base: Path) -> Dict[str, Dict[str, str]]:
    """Optional metadata.csv keyed by dataset-relative path."""
    out: Dict[str, Dict[str, str]] = {}
    csv_path = base / "metadata.csv"
    if not csv_path.exists():
        return out
    try:
        with csv_path.open(newline='', encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                p = (row.get('path') or '').strip().replace("\\", "/")
                if p:
                    out[p] = {k: (v or '').strip() for k, v in row.items() if k != 'path'}
    except Exception as e:
        logger.warning(f"metadata.csv unreadable ({e}); continuing without it.")
    return out


def _entry_to_item(entry: Dict[str, Any], item_id: int) -> QueryItem:
    return QueryItem(
        id=item_id,
        user_id=0,
        report_type=entry.get('report_type', 'found'),
        title=entry.get('title') or Path(entry['path']).stem,
        category=entry.get('category', 'Other'),
        location_reported=entry.get('location_reported', ''),
        description=entry.get('description', '') or entry.get('title', ''),
        color_hint=entry.get('color_hint') or None,
        photo_url=entry.get('photo_url'),
        date_time_reported=datetime.strptime(entry['date'], '%Y-%m-%d')
            if entry.get('date') else datetime.utcnow(),
        image_feature_vector=entry.get('vector'),
    )


# ---------------------------------------------------------------------------
# Evaluation run
# ---------------------------------------------------------------------------

def run_evaluation(root: str, min_composite: float = DEFAULT_MIN_COMPOSITE,
                   use_text_context: bool = False) -> Dict[str, Any]:
    """
    Scores every labeled query against the labeled gallery using the same
    embedding + cosine pipeline that production uses. Text context is OFF by
    default for a clean image-only measurement (labels on synthetic fixtures
    intentionally leak into nothing); enable it to measure the full composite.

    Returns a metrics dict; {'error': ...} when the dataset is unusable.
    """
    ds = load_labeled_dataset(root)
    for side in ('queries', 'gallery'):
        ds[side] = [e for e in ds[side] if _embed_entry(e)]
    if not ds["queries"] or not ds["gallery"]:
        return {"error": "Dataset needs at least one query and one gallery image "
                         "under queries/<label>/ and gallery/<label>/."}

    gallery_items = [_entry_to_item(e, i + 1) for i, e in enumerate(ds["gallery"])]
    gallery_labels = {g.id: ds["gallery"][g.id - 1]["label"] for g in gallery_items}

    per_query = []
    ranks = []
    for q_entry in ds["queries"]:
        q_item = _entry_to_item(q_entry, 0)
        if use_text_context:
            ranked = rank_matches(q_item, gallery_items, min_composite=0.0, limit=len(gallery_items))
        else:
            ranked = _rank_image_only(q_item, gallery_items)
        correct_positions = [i for i, r in enumerate(ranked)
                             if gallery_labels[r["item_id"]] == q_entry["label"]]
        best_rank = correct_positions[0] + 1 if correct_positions else 0
        ranks.append(best_rank)
        per_query.append({
            "query": q_entry["path"],
            "label": q_entry["label"],
            "best_correct_rank": best_rank,
            "top_match": ranked[0]["title"] if ranked else None,
            "top_score": ranked[0]["composite_score"] if ranked else None,
        })

    n = len(per_query)
    sweep = {}
    for thr in (0.35, 0.45, 0.55, 0.65, 0.75):
        kept = [p for p in per_query
                if (p["top_score"] or 0) >= thr and p["best_correct_rank"] == 1]
        offered = [p for p in per_query if (p["top_score"] or 0) >= thr]
        sweep[f"{thr:.2f}"] = {
            "queries_above_threshold": len(offered),
            "correct_at_1": len(kept),
            "precision_at_1": round(len(kept) / len(offered), 3) if offered else None,
        }

    return {
        "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "dataset_root": str(Path(root).resolve()),
        "mode": "full composite (image + text context)" if use_text_context else "image cosine only",
        "num_queries": n,
        "num_gallery": len(gallery_items),
        "precision_at_1": round(sum(1 for r in ranks if r == 1) / n, 3),
        "hit_at_3": round(sum(1 for r in ranks if 1 <= r <= 3) / n, 3),
        "hit_at_5": round(sum(1 for r in ranks if 1 <= r <= 5) / n, 3),
        "mrr": round(sum((1.0 / r) if r else 0.0 for r in ranks) / n, 3),
        "threshold_sweep": sweep,
        "per_query": per_query,
    }


def _embed_entry(entry: Dict[str, Any]) -> Optional[str]:
    if entry.get("vector"):
        return entry["vector"]
    vec = extract_image_features(entry["path"])
    entry["vector"] = vec
    return vec


def _rank_image_only(query: QueryItem, gallery: List[QueryItem]) -> List[Dict[str, Any]]:
    q_model, q_vec = load_embedding(query.image_feature_vector)
    scored = []
    for item in gallery:
        i_model, i_vec = load_embedding(item.image_feature_vector)
        score = 0.0
        if q_vec and i_vec and q_model == i_model:
            score = compute_cosine_similarity(q_vec, i_vec)
        scored.append({"item_id": item.id, "title": item.title,
                       "composite_score": round(score, 3)})
    scored.sort(key=lambda x: x["composite_score"], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def format_report(metrics: Dict[str, Any]) -> str:
    """Markdown report. Refuses to invent numbers: only echoes a measured run."""
    if "error" in metrics:
        return f"# Matcher Evaluation\n\nEvaluation could not run: {metrics['error']}\n"
    lines = [
        "# Lost & Found AI Matcher - Evaluation Report",
        "",
        f"- Run: {metrics['generated_at']}",
        f"- Dataset: `{metrics['dataset_root']}`",
        f"- Mode: {metrics['mode']}",
        f"- Queries: {metrics['num_queries']} | Gallery images: {metrics['num_gallery']}",
        "",
        "## Measured results (this dataset only)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Precision@1 | {metrics['precision_at_1']:.3f} |",
        f"| Hit@3 | {metrics['hit_at_3']:.3f} |",
        f"| Hit@5 | {metrics['hit_at_5']:.3f} |",
        f"| MRR | {metrics['mrr']:.3f} |",
        "",
        "## Threshold sweep (share of queries whose top-1 is correct)",
        "",
        "| Min composite | Queries above | Correct @1 | Precision@1 |",
        "|---|---|---|---|",
    ]
    for thr, s in metrics["threshold_sweep"].items():
        p = "-" if s["precision_at_1"] is None else f"{s['precision_at_1']:.3f}"
        lines.append(f"| {thr} | {s['queries_above_threshold']} | {s['correct_at_1']} | {p} |")
    lines += ["", "## Per-query outcome", ""]
    for q in metrics["per_query"]:
        rank_txt = f"rank {q['best_correct_rank']}" if q["best_correct_rank"] else "MISS"
        lines.append(f"- `{q['label']}` / {Path(q['query']).name}: {rank_txt} "
                     f"(top: {q['top_match']}, score {q['top_score']})")
    lines += ["", "> These figures describe ONLY the evaluated dataset. They are not a",
              "> general accuracy claim for real campus photographs.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deterministic synthetic sample dataset (procedure smoke-test only)
# ---------------------------------------------------------------------------

_SHAPES = {
    "wallet": ("rectangle", (40, 40, 180), (170, 60, 60)),      # maroon wallet-ish block
    "bottle": ("circle", (200, 120, 60), (40, 120, 200)),       # blue bottle blob
    "keys": ("triangle", (60, 180, 60), (220, 200, 220)),       # green keys token
    "earphones": ("cross", (180, 60, 180), (90, 90, 90)),       # purple band shape
}


def _draw_label(canvas: np.ndarray, label: str, variant: int) -> np.ndarray:
    kind, color, accent = _SHAPES[label]
    h, w = canvas.shape[:2]
    cx, cy = w // 2, h // 2
    s = 60 + variant * 8
    if kind == "rectangle":
        cv2.rectangle(canvas, (cx - s, cy - s // 2), (cx + s, cy + s // 2), color, -1)
        cv2.rectangle(canvas, (cx - s // 2, cy - 6), (cx + s // 2, cy + 6), accent, -1)
    elif kind == "circle":
        cv2.circle(canvas, (cx, cy), s, color, -1)
        cv2.circle(canvas, (cx, cy - s // 2), s // 4, accent, -1)
    elif kind == "triangle":
        pts = np.array([[cx, cy - s], [cx - s, cy + s], [cx + s, cy + s]], np.int32)
        cv2.fillPoly(canvas, [pts], color)
        cv2.circle(canvas, (cx, cy), s // 3, accent, -1)
    elif kind == "cross":
        cv2.rectangle(canvas, (cx - s, cy - s // 4), (cx + s, cy + s // 4), color, -1)
        cv2.circle(canvas, (cx - s, cy), s // 3, accent, -1)
        cv2.circle(canvas, (cx + s, cy), s // 3, accent, -1)
    return canvas


def generate_synthetic_dataset(root: str, seed: int = 360) -> Dict[str, int]:
    """
    Creates queries/<label>/x2 and gallery/<label>/x3 deterministic images per
    label so the evaluation PROCEDURE can run end-to-end without real photos.
    """
    rng = np.random.default_rng(seed)
    base = Path(root)
    counts = {}
    for label in _SHAPES:
        qdir = base / "queries" / label
        gdir = base / "gallery" / label
        qdir.mkdir(parents=True, exist_ok=True)
        gdir.mkdir(parents=True, exist_ok=True)
        for i in range(2):
            canvas = np.full((224, 224, 3), 235, np.uint8)
            noise = rng.integers(0, 12, canvas.shape, dtype=np.uint8)
            canvas = cv2.add(canvas, noise)
            _draw_label(canvas, label, i)
            cv2.imwrite(str(qdir / f"query_{i}.jpg"), canvas)
        for i in range(3):
            canvas = np.full((224, 224, 3), 235, np.uint8)
            noise = rng.integers(0, 12, canvas.shape, dtype=np.uint8)
            canvas = cv2.add(canvas, noise)
            _draw_label(canvas, label, i)
            cv2.imwrite(str(gdir / f"item_{i}.jpg"), canvas)
        counts[label] = 5
    return counts
