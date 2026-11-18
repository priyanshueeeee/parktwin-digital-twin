# ParkTwin: Parkinson's Progression Digital Twin as a Service

ParkTwin is a research-oriented, non-diagnostic digital twin service for estimating Parkinson's disease progression from longitudinal speech features, tracking an individual trajectory, and exploring intervention scenarios.

The project turns periodic voice observations into an estimated UPDRS state, maintains a patient-specific longitudinal twin, and exposes the result through a REST API and clinician-facing dashboard.

> **Safety boundary:** This is a prototype for estimation, visualization, and what-if analysis. It must not be used as a primary diagnostic, prescribing, or treatment-decision system.

## Project goals

- Map automated speech features to estimated Total and Motor UPDRS values.
- Track progression over time instead of relying only on isolated assessments.
- Maintain a patient-specific state and estimate a trajectory slope (`ΔUPDRS/Δt`).
- Simulate hypothetical therapy changes, including Levodopa and physical therapy inputs.
- Present uncertainty, model quality, and trajectory changes clearly in a short clinical-review workflow.
- Keep the prototype reproducible, testable, privacy-aware, and easy to extend.

## Source-derived scope

The attached presentation defines the initial prototype boundary:

| Area | Baseline scope |
|---|---|
| Dataset | UCI Parkinson's Telemonitoring Dataset |
| Size | 5,875 observations, 42 patients, approximately 6 months of longitudinal data |
| Input | 16 biomedical speech metrics, including jitter, shimmer, NHR, HNR, and RPDE |
| Targets | Total UPDRS and Motor UPDRS estimates |
| Core analysis | Longitudinal deterioration and patient-specific slope tuning |
| Service | REST API for twin creation, updates, trajectories, and simulations |
| Frontend | Interactive trajectory dashboard with baseline and intervention controls |
| Performance target | Recalculate the vertical-slice trajectory within 500 ms under prototype load |
| Prototype constraint | Non-diagnostic; data must be handled according to medical telemonitoring privacy practices |

The presentation also names a less-than-10% prediction-error question. This plan treats that as a validation target to measure, not as an achieved result.

## Product behavior

The intended user journey is:

1. Create a twin from a baseline patient profile, speech metrics, and available UPDRS values.
2. Submit new voice observations as they become available.
3. Re-estimate the current state and update the longitudinal trajectory.
4. Review observed and predicted UPDRS values, confidence/quality indicators, and the estimated slope.
5. Adjust intervention inputs in a sandboxed simulation.
6. Compare baseline and simulated trajectories without changing the observed record.

## High-level architecture

```text
Speech observations / baseline data
                |
                v
     Validation and feature preparation
                |
                v
        UPDRS state estimator
                |
                v
 Patient-specific digital twin state
                |
       +--------+---------+
       |                  |
       v                  v
 Trajectory engine   Intervention simulator
       |                  |
       +--------+---------+
                v
             REST API
                |
                v
        Clinician dashboard
```

The detailed design is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and the request-by-request behavior is in [docs/FLOW_SEQUENCES.md](docs/FLOW_SEQUENCES.md).

## Two-contributor branch plan

After the shared API, data, and safety contracts are frozen, split the work into two branches:

| Branch | Segment | Primary ownership |
|---|---|---|
| `codex/segment-a-model-twin` | Model and twin computation | `ml/`, domain logic, inference, trajectory, and simulation math |
| `codex/segment-b-service-ui` | Service and product surface | REST API, persistence, frontend, infrastructure, and integration harness |

Segment A publishes a stable inference/trajectory interface and synthetic fixtures. Segment B initially uses those fixtures or a mock adapter, then switches to the real implementation during the final merge. This keeps both branches productive without requiring either contributor to wait for the other.

Recommended collaboration order:

1. Freeze the shared contracts on `main`: schemas, data dictionary, error format, synthetic fixtures, and safety rules.
2. Create both branches from that same commit.
3. Keep shared contract files read-only on the two feature branches.
4. Run each branch's tests independently.
5. Merge Segment A first, then merge Segment B and replace its mock adapter with the real model/twin implementation.
6. Run the end-to-end, performance, privacy, and demo checks on `main`.

The complete task split, file ownership, checkpoints, and merge checklist are in [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).

## Recommended repository structure

```text
.
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── FLOW_SEQUENCES.md
│   └── PROJECT_PLAN.md
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── domain/
│   │   ├── services/
│   │   ├── persistence/
│   │   └── main.py
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── api/
│   │   ├── state/
│   │   └── charts/
│   └── tests/
├── ml/
│   ├── data/
│   ├── features/
│   ├── training/
│   ├── evaluation/
│   └── artifacts/
├── infra/
│   ├── docker/
│   └── migrations/
└── .github/workflows/
```

The names above are a proposed implementation layout, not a requirement from the presentation.

## Reference technology choices

These choices keep model code and service code in the same language while matching the presentation's React/D3 direction:

- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy.
- **Modeling:** pandas, scikit-learn, NumPy, joblib or an equivalent artifact format.
- **Database:** PostgreSQL for twin state, observations, model metadata, and audit events.
- **Frontend:** React with TypeScript and D3 or a charting wrapper built on D3.
- **Packaging:** Docker Compose for local development; a managed container runtime for deployment.
- **Testing:** pytest, contract tests, frontend component tests, and Playwright or an equivalent browser test runner.

Equivalent technologies are acceptable if the API contracts, model lineage, performance targets, and safety boundaries remain unchanged.

## Local development plan

The following is the intended setup once implementation begins:

```bash
# Start the local service dependencies
docker compose up -d db

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend, in a second terminal
cd frontend
npm install
npm run dev
```

The project should provide a checked-in `.env.example`, database migrations, a synthetic demo seed command, and a documented way to place the permitted UCI dataset outside version control.

## API summary

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/twin/create` | Validate a baseline and initialize a new twin |
| `POST` | `/twin/update` | Ingest a new voice observation and update state |
| `GET` | `/twin/{id}/trajectory` | Retrieve observed and predicted trajectory data |
| `POST` | `/twin/{id}/simulate` | Run an isolated intervention scenario |

Every endpoint must return a request identifier, a schema version, model version, and data-quality indicators where applicable. Full request and response behavior is defined in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Modeling approach

### Data preparation

1. Acquire the permitted dataset through the approved source.
2. Store the raw file outside version control and record its checksum.
3. Validate columns, types, ranges, missingness, duplicate rows, and patient identifiers.
4. Preserve patient and time ordering; do not randomly mix observations from the same patient across train and test sets.
5. Standardize numeric features using parameters fit on the training partition only.
6. Produce a versioned feature table and a data-quality report.

### State estimation

Start with an interpretable regression baseline, such as regularized linear regression, then compare it with a tree-based regressor. Evaluate both Total UPDRS and Motor UPDRS. Report MAE, RMSE, R², calibration or interval coverage if uncertainty is implemented, and per-patient error distributions.

Use grouped, time-aware validation. A patient must not appear in both training and validation partitions for a generalization experiment. If the product later supports personalization, evaluate the personalization procedure separately so its benefit is not confused with population-level performance.

### Trajectory engine

For each twin, keep:

- observed observations;
- estimated UPDRS state at each timestamp;
- a robust slope estimate over a defined time window;
- data coverage and quality flags;
- model and feature versions;
- uncertainty or confidence information where supported.

Do not silently fill missing values or silently replace observations. Preserve the original record and expose imputation or exclusion decisions in metadata.

### Intervention simulation

The simulator should be an explicit scenario model, not a causal claim. It must:

- copy the current twin state into an immutable scenario;
- accept validated intervention parameters and a time horizon;
- apply versioned, documented response assumptions;
- return baseline and simulated trajectories together;
- report uncertainty, unsupported parameter ranges, and the model version;
- never overwrite observed history or the production twin state.

Until clinically supported response data exists, simulation output must be labeled hypothetical.

## Definition of done

A vertical slice is complete when a user can create a twin, submit a valid update, retrieve a recalculated trajectory, run a simulation, and see the result in the dashboard. The slice is accepted only when:

- API and UI contracts are covered by automated tests.
- Invalid, missing, and out-of-range inputs return useful errors.
- The trajectory recalculation meets the 500 ms prototype target under a documented test load.
- Model artifacts are versioned and reproducible.
- Patient-level leakage checks pass.
- Simulation cannot mutate observed data.
- Logs contain no raw voice data or unnecessary personal identifiers.
- The non-diagnostic disclaimer is visible in the UI and API documentation.
- A clean installation and demo run are documented.

## Documentation map

- [Project plan, tasks, checkpoints, and acceptance gates](docs/PROJECT_PLAN.md)
- [System architecture, data contracts, security, and deployment](docs/ARCHITECTURE.md)
- [Flow sequences for data, API, UI, modeling, simulation, and release](docs/FLOW_SEQUENCES.md)

## Known limitations

- The prototype is bounded by one telemonitoring dataset and should not be assumed to represent all populations or recording conditions.
- Speech features can be affected by recording quality, language, fatigue, environment, and comorbidities.
- A prediction of UPDRS is not a clinical assessment.
- Intervention simulation is only as credible as its response assumptions and validation data.
- Performance and error targets are prototype acceptance goals, not evidence of clinical readiness.

## Source and anonymization note

This documentation is derived from the supplied presentation. Human names and name-based ownership labels have intentionally been removed; work is assigned by capability and work-package ID instead. The presentation's content has been converted into implementation requirements, checkpoints, and recommended engineering details.
