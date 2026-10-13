# Lost & Found AI Matcher - Evaluation Report

- Run: 2026-10-13 08:26:38
- Dataset: `C:\Users\nithi\OneDrive\Documents\COLLEGE CAMPUS ANTIGRAVITY\evaluation\lost_found_dataset`
- Mode: image cosine only
- Queries: 8 | Gallery images: 12

## Measured results (this dataset only)

| Metric | Value |
|---|---|
| Precision@1 | 1.000 |
| Hit@3 | 1.000 |
| Hit@5 | 1.000 |
| MRR | 1.000 |

## Threshold sweep (share of queries whose top-1 is correct)

| Min composite | Queries above | Correct @1 | Precision@1 |
|---|---|---|---|
| 0.35 | 8 | 8 | 1.000 |
| 0.45 | 8 | 8 | 1.000 |
| 0.55 | 8 | 8 | 1.000 |
| 0.65 | 8 | 8 | 1.000 |
| 0.75 | 8 | 8 | 1.000 |

## Per-query outcome

- `bottle` / query_0.jpg: rank 1 (top: item_0, score 1.0)
- `bottle` / query_1.jpg: rank 1 (top: item_1, score 0.987)
- `earphones` / query_0.jpg: rank 1 (top: item_0, score 1.0)
- `earphones` / query_1.jpg: rank 1 (top: item_1, score 1.0)
- `keys` / query_0.jpg: rank 1 (top: item_0, score 1.0)
- `keys` / query_1.jpg: rank 1 (top: item_1, score 1.0)
- `wallet` / query_0.jpg: rank 1 (top: item_0, score 1.0)
- `wallet` / query_1.jpg: rank 1 (top: item_1, score 1.0)

> These figures describe ONLY the evaluated dataset. They are not a
> general accuracy claim for real campus photographs.
