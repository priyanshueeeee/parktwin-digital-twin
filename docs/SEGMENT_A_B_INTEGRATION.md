# Segment A ↔ Segment B Integration Guide (Living Document)

> **Maintenance rule:** This document is a living contract owned on `segment-b-service-ui` and updated whenever any API contract, adapter method, persistence schema, or environment variable changes. Every PR touching Segment B's adapter boundary or endpoints **must** append an entry to the [Living Changelog](#9-living-changelog) at the bottom of this file.

## 1. Purpose & Non-Overlapping Ownership

ParkTwin splits delivery cleanly between:

| Segment | Branch | Owned Paths | Responsibility |
|---|---|---|---|
| **Segment A** | `segment-a-model-twin` | `ml/**`, `backend/app/domain/**`, `backend/app/services/inference.py`, `backend/app/services/trajectory.py`, `backend/app/services/simulation.py`, `backend/app/services/adapter.py`, `backend/tests/unit/**` | UCI dataset validation, leakage-safe training, UPDRS inference artifact, trajectory slope math, isolated simulation math, and real `TwinEnginePort` implementation |
| **Segment B** | `segment-b-service-ui` | `backend/app/api/**`, `backend/app/persistence/**`, `backend/app/main.py`, `backend/app/config.py`, `backend/tests/contract/**`, `backend/tests/integration/**`, `frontend/**`, `infra/**`, `docker-compose.yml`, `.github/workflows/segment-b-ci.yml`, `docs/SEGMENT_A_B_INTEGRATION.md` | FastAPI REST API, auth/RBAC, idempotency, optimistic concurrency, PostgreSQL/Alembic persistence, observability, React/D3 dashboard, Docker Compose, and demo harness |

Segment B does **not** import training code (`ml/**`) or modify Segment A's paths. Integration happens exclusively through a single typed adapter seam: **`TwinEnginePort`**.

---

## 2. The Adapter Seam (`TwinEnginePort`)

Defined in `backend/app/api/engine_adapter.py`. Segment B calls **only** these 5 methods:

```python
class TwinEnginePort(Protocol):
    def is_available(self) -> bool: ...
    def get_model_metadata(self) -> EngineModelMetadata: ...
    def infer(
        self,
        features: dict[str, float | None],
        *,
        is_partial: bool,
    ) -> InferenceResult: ...
    def compute_trajectory(
        self,
        points: list[TrajectoryInputPoint],
        *,
        stale_threshold_days: int = 30,
        reference_time: datetime | None = None,
    ) -> TrajectoryResult: ...
    def simulate(
        self,
        trajectory: TrajectoryResult,
        *,
        levodopa_dose_change_mg: float,
        physical_therapy_sessions_per_week: int,
        adherence_ratio: float,
        horizon_days: int,
        step_days: int,
    ) -> SimulationOutput: ...
```

### Exact Dataclass Contracts

1. **`EngineModelMetadata`** (stored in `model_metadata` table and returned on every API response & `/ready`):
   - `model_version: str` (e.g. `"gbdt-updrs-v1.0.0"`)
   - `feature_version: str` (e.g. `"speech16-v1"`)
   - `assumptions_version: str` (e.g. `"sim-assumptions-v1"`)
   - `adapter_type: str` — **must return `"real"`** for Segment A's adapter (`"mock"` is reserved for `MockTwinEngineAdapter`)
   - `artifact_checksum: str` (SHA-256 hex digest of promoted model/preprocessing artifact)

2. **`InferenceResult`** (stored on every `state_estimates` row):
   - `estimated_total_updrs: float | None` (`None` when `is_partial=True` — **never fabricate UPDRS**)
   - `estimated_motor_updrs: float | None`
   - `total_updrs_ci_low: float | None`, `total_updrs_ci_high: float | None`
   - `motor_updrs_ci_low: float | None`, `motor_updrs_ci_high: float | None`
   - `confidence_score: float | None` (`0.0` to `1.0`)
   - `quality_flags: list[str]` (machine-readable codes such as `PARTIAL_BASELINE_FEATURES`, `LOW_SIGNAL_HARMONICS_RATIO`)
   - `model_version: str`, `feature_version: str`
   - **Fail-closed requirement:** If the artifact failed to load or is missing, raise `app.api.engine_adapter.ModelUnavailableError`. Segment B automatically rolls back the DB transaction and returns `503 MODEL_UNAVAILABLE` with zero partial state committed.

3. **`TrajectoryInputPoint` -> `TrajectoryResult`**:
   - Input points contain immutable raw observations paired with stored estimates (`observation_id`, `observed_at`, `is_partial`, `observed_total_updrs`, `observed_motor_updrs`, `estimated_total_updrs`, `estimated_motor_updrs`, CI bounds, `quality_flags`).
   - Output `TrajectoryResult`:
     - `status`: `"active"` or `"insufficient_data"`
     - `observed_points: list[dict]` (`source_type="observed"`, `hypothetical=False`)
     - `estimated_points: list[dict]` (`source_type="estimated"`, `hypothetical=False`, includes CI bounds)
     - `slope: dict` with keys:
       - `status`: `"computed"` or `"insufficient_data"` (**never return `0.0` when `< 2` time-separated points exist; return `None`!**)
       - `method`: documented regression method identifier (e.g. `"theil_sen_180d"` or `"ordinary_least_squares_full_window"`)
       - `window_description`: human-readable window definition
       - `units`: `"updrs_points_per_30_days"`
       - `total_updrs_per_30_days`, `motor_updrs_per_30_days`, `total_updrs_per_day`, `motor_updrs_per_day`: `float | None`
       - `observation_count_used: int`, `time_span_days: float`
     - `coverage: dict` (`total_observations`, `estimated_observations`, `observed_updrs_count`, `first_observed_at`, `last_observed_at`, `time_span_days`, `is_stale`, `stale_threshold_days`)
     - `quality_flags: list[str]`, `warnings: list[str]`

4. **`SimulationOutput`** (pure function; must **never** mutate inputs or touch the database):
   - `assumptions_version: str`, `model_version: str`
   - `hypothetical: bool` (must always be `True`)
   - `baseline_series: list[dict]` (`timestamp`, `day_offset`, `source_type="estimated"`, `total_updrs`, `motor_updrs`, `hypothetical=False`)
   - `scenario_series: list[dict]` (`timestamp`, `day_offset`, `source_type="simulated"`, `total_updrs`, `motor_updrs`, CI bounds, `hypothetical=True`)
   - `summary: dict` (`horizon_days`, `baseline_end_total_updrs`, `scenario_end_total_updrs`, `delta_total_updrs`, `baseline_end_motor_updrs`, `scenario_end_motor_updrs`, `delta_motor_updrs`, `hypothetical=True`)
   - `warnings: list[str]` (must include hypothetical/non-clinical disclaimer warning)

---

## 3. Data Dictionary: 16 Biomedical Speech Features

Segment B validates all incoming payloads strictly (`extra="forbid"`) before invoking `engine.infer(...)`. Segment A's feature pipeline must map UCI Telemonitoring source columns to these exact snake_case keys:

| API Key (`SpeechFeatures`) | UCI Source Column | Unit | Validated Range (Segment B) |
|---|---|---|---|
| `jitter_percent` | `Jitter(%)` | ratio | `[0.0, 1.0]` |
| `jitter_abs` | `Jitter(Abs)` | seconds | `[0.0, 0.01]` |
| `jitter_rap` | `Jitter:RAP` | ratio | `[0.0, 1.0]` |
| `jitter_ppq5` | `Jitter:PPQ5` | ratio | `[0.0, 1.0]` |
| `jitter_ddp` | `Jitter:DDP` | ratio | `[0.0, 3.0]` |
| `shimmer` | `Shimmer` | ratio | `[0.0, 1.0]` |
| `shimmer_db` | `Shimmer(dB)` | dB | `[0.0, 10.0]` |
| `shimmer_apq3` | `Shimmer:APQ3` | ratio | `[0.0, 1.0]` |
| `shimmer_apq5` | `Shimmer:APQ5` | ratio | `[0.0, 1.0]` |
| `shimmer_apq11` | `Shimmer:APQ11` | ratio | `[0.0, 1.0]` |
| `shimmer_dda` | `Shimmer:DDA` | ratio | `[0.0, 3.0]` |
| `nhr` | `NHR` | ratio | `[0.0, 5.0]` |
| `hnr` | `HNR` | dB | `[0.0, 60.0]` |
| `rpde` | `RPDE` | index | `[0.0, 1.0]` |
| `dfa` | `DFA` | exponent | `[0.0, 1.5]` |
| `ppe` | `PPE` | index | `[0.0, 2.0]` |

Additional validated fields:
- `external_reference`: `^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$` (pseudonymous token; rejects spaces/names/emails)
- `observed_at`: timezone-aware ISO-8601 UTC (`>= 2000-01-01`, not `> now + 5m`)
- `observed_total_updrs`: optional float `[0.0, 199.0]`
- `observed_motor_updrs`: optional float `[0.0, 108.0]` (`<= observed_total_updrs` when both provided)
- Simulation intervention bounds:
  - `levodopa_dose_change_mg`: `[-300.0, 600.0]`
  - `physical_therapy_sessions_per_week`: `[0, 7]`
  - `adherence_ratio`: `[0.0, 1.0]`
  - `horizon_days`: `[7, 180]`, `step_days`: `[1, 30]` (`step_days <= horizon_days`)
  - `acknowledge_hypothetical`: must be `true`

---

## 4. Zero-Friction Wiring Recipe (Swapping Mock → Real Adapter)

Segment B already includes a dynamic real-adapter loader in `backend/app/api/engine_adapter.py`:

```python
build_engine_adapter(
    adapter_name="real",
    real_adapter_path="app.services.adapter:build_real_engine_adapter",
)
```

### Steps for Segment A + Merge Day

1. In Segment A (`backend/app/services/adapter.py`), expose a factory function `build_real_engine_adapter() -> TwinEnginePort` (or any dotted path `module:callable` implementing the 5 `TwinEnginePort` methods) that loads the promoted model artifact without importing training pipelines.
2. Merge `segment-a-model-twin` into `main` first, then merge `main` into `segment-b-service-ui`.
3. Set environment variables (`.env` and `docker-compose.yml`):
   ```bash
   PARKTWIN_ENGINE_ADAPTER=real
   PARKTWIN_REAL_ADAPTER_PATH=app.services.adapter:build_real_engine_adapter
   PARKTWIN_TOTAL_ARTIFACT_PATH=ml/artifacts/total/random_forest-total_UPDRS.joblib
   PARKTWIN_MOTOR_ARTIFACT_PATH=ml/artifacts/motor/random_forest-motor_UPDRS.joblib
   ```

   The adapter maps Segment B's API key `jitter_abs` to Segment A's canonical
   `jitter_absolute` feature name. Both promoted artifacts must use the same
   feature mode and feature-set version; missing or incompatible artifacts fail
   closed with `MODEL_UNAVAILABLE`.
4. Start the API and verify `/ready`:
   - `checks.inference_adapter` must report `"ok"`
   - `model_metadata.adapter_type` will automatically switch to `"real"` (and display `[real]` in the React dashboard header!).
5. For any existing twins previously estimated with `mock-updrs-v0.1.0`, call **`POST /twin/{twin_id}/recompute`** (or click **Recompute with Active Model** in the dashboard's *Governance, Export & Audit* tab) to re-estimate all immutable raw observations using Segment A's promoted model artifact while preserving full audit lineage.

---

## 5. REST Endpoints Surface Summary (v1)

| Method | Endpoint | Role | Purpose |
|---|---|---|---|
| `GET` | `/health` | Public | Liveness probe & non-diagnostic notice |
| `GET` | `/ready` | Public | Readiness probe (PostgreSQL + inference adapter fail-closed check) |
| `GET` | `/metrics` | Public | Safe latency/error/warning counters (zero PII) |
| `GET` | `/twins` | Any auth | List accessible pseudonymous twins for dashboard selector |
| `POST` | `/twin/create` | `clinician`/`admin` | Baseline validation, idempotency, transactional twin+observation+estimate create |
| `POST` | `/twin/update` | `clinician`/`admin` | Append immutable voice observation, timestamp/OCC checks, trajectory recalculation |
| `GET` | `/twin/{id}/trajectory` | Reader/Owner | Chronological observed & estimated points, slope, coverage, calibration MAE, optional `scenario_id` |
| `POST` | `/twin/{id}/simulate` | Reader/Owner | Read-only hypothetical scenario simulation (isolated table, never mutates twin) |
| `GET` | `/twin/{id}/scenarios` | Reader/Owner | List saved hypothetical scenarios for overlay/comparison |
| `GET` | `/twin/{id}/observations` | Reader/Owner | Immutable observation ledger & baseline-to-latest acoustic biomarker deltas |
| `PATCH` | `/twin/{id}/status` | `clinician`/`admin` | Optimistic-concurrency lifecycle transition (`active`, `paused`, `archived`) |
| `POST` | `/twin/{id}/recompute` | `clinician`/`admin` | Re-run active model inference & trajectory over immutable observations |
| `GET` | `/twin/{id}/audit` | Reader/Owner | Redacted compliance audit trail |
| `GET` | `/twin/{id}/export` | Reader/Owner | Pseudonymous JSON or CSV clinical research export (`?format=json|csv`) |

Every response emits:
- `X-Request-ID`, `X-Process-Time-Ms`, and `Server-Timing` (`inference;dur=..., trajectory;dur=..., simulation;dur=..., total;dur=...`)
- Security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.

---

## 6. Merge-Day Verification Checklist

Run these exact checks after switching `PARKTWIN_ENGINE_ADAPTER=real`:

- [ ] **Migrations from clean DB:** `alembic -c infra/migrations/alembic.ini upgrade head`
- [ ] **Backend contract & integration suite:** `cd backend && pytest` (with real adapter fixture enabled)
- [ ] **Fail-closed model check:** Point artifact path to invalid file -> verify `/ready` returns `503` and `POST /twin/create` returns `503 MODEL_UNAVAILABLE` with zero DB rows created
- [ ] **Simulation immutability & 500 ms target:** `python infra/scripts/run_demo.py --base-url http://localhost:8000` -> verify `production_history_unchanged: true` and `max_recalc_ms < 500` (inspect `Server-Timing` breakdown for `inference` vs `trajectory`)
- [ ] **Synthetic seed idempotency:** Run `python infra/scripts/seed_demo.py` twice and confirm identical twin UUIDs
- [ ] **Frontend typecheck, tests & build:** `cd frontend && npm run typecheck && npm test && npm run build`
- [ ] **UI visual verification:** Confirm header badge reads `[real]`, observed/estimated/simulated series remain visually distinct, warnings render above chart, and non-diagnostic banner stays visible
- [ ] **Privacy audit:** Verify logs, `/metrics`, `/audit`, and `/export` contain zero raw audio, personal names, or raw feature dumps in logs.

---

## 7. Known Integration Decisions to Align Before Production

1. **Slope regression method:** Mock uses `ordinary_least_squares_full_window`. Segment A may return a robust estimator (e.g., Theil-Sen or Huber over a bounded window) — ensure `slope.method` and `slope.window_description` reflect the actual algorithm so the dashboard displays it verbatim.
2. **Uncertainty intervals:** Mock populates symmetric CI bounds (`*_ci_low`, `*_ci_high`). If Segment A provides conformal or quantile prediction intervals, map them to the exact same fields; if unavailable for a model variant, return `None` (dashboard omits CI shading gracefully).
3. **Patient-specific tuning flag:** If Segment A adds a feature-flagged personalization mode, expose its status in `quality_flags` (e.g. `PERSONALIZED_TUNING_ACTIVE`) or `model_version` suffix so every estimate remains traceable.

---

## 8. Quick Local Commands

```bash
# Full stack via Docker Compose
docker compose up --build

# Seed 3 synthetic cohorts (idempotent)
python infra/scripts/seed_demo.py --base-url http://localhost:8000

# Run end-to-end demo + 500 ms latency check
python infra/scripts/run_demo.py --base-url http://localhost:8000
```

---

## 9. Living Changelog

| Date | Version | Branch / Commit | Summary of Contract & Integration Updates |
|---|---|---|---|
| 2026-11-18 | `v1.0.0` | `segment-b-service-ui` (`2f4e7f4`) | Initial Segment B REST API (`/twin/create`, `/twin/update`, `/twin/{id}/trajectory`, `/twin/{id}/simulate`, `/twins`, `/health`, `/ready`, `/metrics`), SQLAlchemy/Alembic schema (`0001_initial_schema`), `TwinEnginePort` + `MockTwinEngineAdapter`, React/D3 dashboard, Docker Compose, and demo scripts. |
| 2026-11-18 | `v1.1.0` | `segment-b-service-ui` (current) | Added pluggable `PARKTWIN_ENGINE_ADAPTER=real` dynamic loader (`PARKTWIN_REAL_ADAPTER_PATH`), twin lifecycle management (`PATCH /twin/{id}/status`), derived-state recomputation (`POST /twin/{id}/recompute`) for model artifact upgrades, voice biomarker ledger (`GET /twin/{id}/observations`), redacted audit viewer (`GET /twin/{id}/audit`), pseudonymous JSON/CSV export (`GET /twin/{id}/export`), `calibration_summary` (observed-vs-estimated MAE), `Server-Timing` & HTTP security headers, and multi-tab clinical dashboard UI. |
