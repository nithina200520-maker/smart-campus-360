# SMART CAMPUS 360 — KNOWN LIMITATIONS & FUTURE ENHANCEMENTS

> Honest-boundaries document for the college demonstration. Everything listed under
> *Limitations* is a real boundary of the current build — the system never claims
> otherwise on screen or in this pack.

## 1. Known limitations (current build)

### Money & external services
1. **Payments are sandbox-simulated.** The default provider is a deterministic built-in
   gateway; no real money is captured, settled or refunded. Stripe support is
   **test-mode only** (startup refuses live keys). Real settlement requires a
   commercial account, live keys, HTTPS, and a fresh round of production testing that
   has **not** been performed for this submission.
2. **Notifications are in-app only.** There is no email, SMS or mobile-push delivery;
   a user who never opens the site sees nothing. External channels would need
   credentialed providers and new code paths.
3. **No production deployment exists.** Docker/Compose provides a reproducible
   *production-style* image, but the project has only been operated on a local
   development machine and a single Docker instance — no load, uptime or penetration
   testing on public infrastructure has been done.

### Data authenticity
4. **All campus content is labelled sample data.** Navigation nodes/edges/floor plans,
   menu items, slots and demo reports carry `is_sample_data = true` / `[SAMPLE]` names;
   distances and coordinates are illustrative, **not** survey-verified measurements of
   the real GEC Mosalehosahalli campus.
5. **AI accuracy is measured only on a small controlled dataset.** Precision@1 = 1.000
   holds for the 8-query/12-image evaluation set (see [TESTING.md](TESTING.md) §3); real
   photographs with varied angle, lighting and clutter will score lower. Similarity is
   decision support — never proof of ownership (workflow enforces this).
6. **QR pickup assumes a scanner-capable device or manual code entry** at the counter;
   no dedicated hardware integration is shipped.

### Platform & UX
7. **No pinch-zoom on touch devices** for the canvas map (buttons and drag work;
   documented since Phase 10).
8. **Web-only.** No native Android/iOS app and no offline PWA mode; phone access is via
   browser on the college network.
9. **Session-based auth tuned for campus scale.** Flask server sessions, single
   Gunicorn deployment; no horizontal-scaling session store (Redis) or SSO with any
   college directory exists.
10. **Migrations are scripted, not automated.** `migrate_phase2…8.py` run in order with
    automatic backups; there is no Alembic-style auto-migration pipeline for arbitrary
    version jumps.
11. **English-only interface.** No Kannada/Hindi localisation.
12. **Fixed five-role RBAC.** No custom roles or per-department permission granularity.

---

## 2. Future enhancements (roadmap)

### Phase 12 candidates — institutional hardening
* **Live payment gateway onboarding** (UPI intent / card) with production credential
  management, HTTPS enforcement, PCI-aware flows and a full live-mode test cycle.
* **Email + SMS + push notification adapters** for matches, claim decisions, order
  readiness and refund completion (provider-abstracted like the payment layer).
* **Verified campus data import:** survey-grade building/floor register, measured edge
  distances, real photography drive, then unpublish all `[SAMPLE]` content.
* **Alembic migration pipeline + CI/CD** (automated test gate on every merge).

### Phase 13 candidates — capability growth
* **Native/PWA mobile client** with offline slot browsing and camera capture for
  instant lost-item reporting.
* **Real GIS basemap** (Leaflet/OpenStreetMap overlay) alongside the schematic canvas,
  with pinch-zoom and accessibility (WCAG AA) improvements.
* **Image-based search from the camera roll** and text+image hybrid matching
  (CLIP-class embeddings) to raise real-world match quality.
* **Multi-language UI** (English / ಕನ್ನಡ / Hindi) via message catalogues.

### Phase 14 candidates — campus ecosystem integration
* Staff-directory SSO for automatic teacher verification; student USN directory sync.
* Canteen analytics: demand forecasting per slot, waste reduction suggestions.
* Feedback & rating loops for canteen orders and Lost & Found handling.
* Extension blueprint slots for library (book issue/return), attendance and fee modules
  on the same RBAC + audit backbone.
* Fine-grained permissions, report scheduling and CSV/PDF export of admin analytics.

[← Demonstration pack](PROJECT_REPORT.md)
