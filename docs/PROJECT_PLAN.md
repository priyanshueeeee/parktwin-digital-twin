# Project Plan: Tasks, Checkpoints, and Acceptance Gates

This plan converts the supplied presentation into an executable delivery plan. It uses role-based ownership only; no individual names are used.

## Delivery strategy

Use one short shared setup phase, then split into two branches with non-overlapping ownership. Each contributor can build and test independently, using mocks or fixtures at the boundary. The branches merge only after their individual checkpoints pass.

```text
Shared contract freeze on main
              |
       +------+------+
       |             |
       v             v
Segment A       Segment B
Model + Twin    Service + UI
       |             |
       +------+------+
              v
       Merge and validate on main
```

The work-package IDs are identifiers, not people assignments.

## Branch setup and ownership

### Shared phase - Contract freeze on `main`

Complete this phase before creating the two feature branches. It is intentionally small and should be merged to `main` as one baseline commit.

Tasks:

- Create the repository layout, environment template, local commands, and CI checks.
- Create the data dictionary for the 16 speech features, UPDRS targets, timestamps, and pseudonymous patient references.
- Define domain and API schemas for `Twin`, `Observation`, `StateEstimate`, `TrajectoryPoint`, `SimulationScenario`, and `ModelMetadata`.
- Define the API error shape, request IDs, schema versioning, idempotency rules, and non-diagnostic metadata.
- Create synthetic fixtures that do not contain real patient data.
- Record the no-raw-data Git policy, privacy threat model, and minimum logging policy.

Shared-phase exit criteria:

- A clean checkout can run CI and load the synthetic fixtures.
- The data dictionary and API schemas are versioned and frozen.
- Both contributors agree on the interface between model/twin logic and the API.
- The two branches can be created from the same commit.

Create the branches from that commit:

```bash
git switch main
git switch -c segment-a-model-twin

git switch main
git switch -c segment-b-service-ui
```

### Segment A - Model and twin computation

**Branch:** `segment-a-model-twin`

**Goal:** Build the data pipeline, UPDRS estimator, twin state rules, trajectory engine, and isolated simulation math.

**Own these paths:**

- `ml/**`
- `backend/app/domain/**`
- `backend/app/services/inference.py`
- `backend/app/services/trajectory.py`
- `backend/app/services/simulation.py`
- `backend/tests/unit/model/**`
- `backend/tests/unit/domain/**`
- model evaluation reports and artifact metadata

Do not edit the shared contract files after branching. If a contract needs to change, open a change note and agree before modifying `main`.

Tasks:

- Validate the dataset shape, types, missingness, ranges, duplicates, patient identifiers, and timestamps.
- Implement feature preparation for jitter, shimmer, NHR, HNR, RPDE, and the remaining metrics.
- Build grouped and time-aware train/validation/test splits by patient.
- Train an interpretable regression baseline for Total and Motor UPDRS.
- Train at least one challenger model and compare metrics and error distributions.
- Persist preprocessing and model artifacts with model version and training-data checksum.
- Implement deterministic batch and single-observation inference.
- Implement twin state transitions for initialization, update, stale data, invalid data, and insufficient history.
- Implement chronological UPDRS series and documented `ΔUPDRS/Δt` calculation.
- Add minimum-history, data-quality, uncertainty, and confidence rules.
- Implement patient-specific tuning only behind a versioned feature flag and evaluation report.
- Implement isolated intervention response functions for the simulation service.
- Add deterministic fixtures for flat, worsening, improving, missing, duplicate, and out-of-order series.
- Publish a small adapter or mock contract that Segment B can call without importing training code.
- Provide model metadata, example responses, and a regression test report for the merge.

Segment A checkpoint:

- No patient leakage is detected.
- Training can be repeated from the same inputs with consistent metadata and metrics.
- Inference rejects invalid feature values.
- State and slope calculations match hand-checked fixtures.
- Simulation math cannot mutate observed state.
- The inference/trajectory adapter passes its contract tests.

### Segment B - Service and product surface

**Branch:** `segment-b-service-ui`

**Goal:** Build persistence, REST endpoints, dashboard behavior, local deployment, and the integration harness around the frozen contracts.

**Own these paths:**

- `backend/app/api/**`
- `backend/app/persistence/**`
- `backend/tests/contract/**`
- `backend/tests/integration/**`
- `frontend/**`
- `infra/**`
- Docker Compose, migrations, health checks, and demo scripts

Use a mock inference/trajectory adapter or the shared synthetic fixtures until Segment A publishes its implementation. This keeps the branch independently runnable.

Tasks:

- Implement database migrations, indexes, audit events, and optimistic concurrency.
- Implement `POST /twin/create` with baseline validation and idempotency.
- Implement `POST /twin/update` with timestamp ordering, feature validation, inference adapter calls, and state updates.
- Implement `GET /twin/{id}/trajectory` with date-range, series, and scenario filters.
- Implement `POST /twin/{id}/simulate` as a read-only scenario operation.
- Store model and feature versions on every estimate.
- Add authentication and authorization hooks.
- Add OpenAPI documentation and endpoint contract tests.
- Create baseline initialization and patient/twin selection views.
- Display observed versus estimated Total and Motor UPDRS over time.
- Display slope, coverage, model version, last update, and quality warnings.
- Add intervention controls and render baseline versus hypothetical trajectories.
- Add loading, empty, error, stale-data, and insufficient-history states.
- Add accessibility, keyboard navigation, chart labels, and color-independent status cues.
- Add Docker Compose, environment configuration, migrations, health checks, and a synthetic demo seed.
- Add browser and API integration tests for the critical path.

Segment B checkpoint:

- All four endpoints work against a clean database with the mock adapter.
- Duplicate and concurrent requests have documented, tested behavior.
- The dashboard completes the workflow using synthetic fixtures.
- Observed, estimated, and simulated series are visually distinct.
- Local deployment and demo commands work from a clean checkout.

## Merge plan

### Before merging

Both contributors must:

- rebase or update their branch from the shared contract commit;
- run formatting, linting, type checks, unit tests, and branch-specific integration tests;
- confirm no personal names, raw patient data, or raw voice data are present in code, fixtures, logs, or screenshots;
- attach model metrics or API/UI test evidence to the merge request;
- list any contract changes instead of silently changing shared files.

### Merge order

Merge Segment A first because it provides the real inference, trajectory, and simulation implementation that Segment B currently reaches through an adapter.

```bash
git switch main
git merge --no-ff segment-a-model-twin

# Update Segment B from main, replace its mock adapter, and rerun its tests.
git switch segment-b-service-ui
git merge main

git switch main
git merge --no-ff segment-b-service-ui
```

If a shared contract conflict appears, stop the merge and resolve the contract on `main` first. Do not resolve it by making the API, model, and UI silently disagree.

### Final integration checkpoint

After both merges on `main`:

- Replace the mock adapter with Segment A's real adapter.
- Run database migrations from a clean database.
- Run the end-to-end test from twin creation through simulation.
- Verify simulation does not change observed history.
- Measure trajectory recalculation against the 500 ms prototype target.
- Run security, privacy, browser, API, model regression, and performance checks.
- Run the synthetic demo and record the model, API, and UI versions.
- Update release notes with limitations and unsupported use cases.

## Final integration, validation, and demonstration tasks

These tasks happen only after both branches are merged. They should not be duplicated on both feature branches.

- Connect the dashboard to the real model/twin adapter.
- Run contract, regression, performance, security, and privacy checks.
- Verify deployment, health checks, migrations, rollback, and artifact loading.
- Prepare a short demonstration showing baseline, update, trajectory, and simulation.
- Confirm a reviewer can distinguish observed evidence, model estimates, and hypothetical output.
- Record the less-than-10% error target as measured evidence or an unmet target; never present it as achieved without results.

## Checkpoint schedule

### Checkpoint 1 - Contract freeze

Review on `main` before branching.

- Data dictionary complete.
- Domain objects and endpoint schemas agreed.
- Privacy and non-diagnostic boundaries documented.
- Synthetic fixtures available.
- Mock inference/trajectory adapter shape agreed.

Decision: create both feature branches only if the contracts are stable.

### Checkpoint 2A - Segment A model and twin baseline

Review on `segment-a-model-twin`.

- Dataset validation report complete.
- Leakage-safe split verified.
- Baseline model metrics recorded.
- Inference artifact can run from a clean environment.
- State and trajectory fixtures pass.
- Adapter contract tests pass.

Decision: publish the adapter and model metadata so Segment B can replace its mock implementation.

### Checkpoint 2B - Segment B service and UI baseline

Review on `segment-b-service-ui`.

- Twin creation, update, trajectory retrieval, and simulation endpoints are callable.
- Persistence and error behavior work with the mock adapter.
- The dashboard workflow works with synthetic fixtures.
- Local deployment and demo commands work from a clean checkout.

Decision: allow Segment B to merge after Segment A is merged and the adapter is replaced.

### Checkpoint 3 - Segment A merge readiness

Review before merging Segment A into `main`.

- Branch-specific unit, model regression, and contract tests pass.
- Model artifacts and evaluation metadata are available.
- No shared contract files were changed silently.
- The real adapter can be imported without the training pipeline.

Decision: merge Segment A first.

### Checkpoint 4 - Segment B merge readiness

Review after updating Segment B from the merged `main`.

- Replace the mock adapter with Segment A's real implementation.
- Endpoint, frontend, and integration tests pass with the real adapter.
- Database migrations, health checks, and demo commands pass from clean state.
- Observed, estimated, and simulated data remain distinct.

Decision: merge Segment B into `main`.

### Checkpoint 5 - Final integrated release candidate

Review on `main` after both merges.

- Critical path passes from a clean environment.
- Performance target and test results are recorded.
- Demo uses synthetic or approved de-identified data.
- Security, privacy, browser, API, and model regression checks pass.
- Known limitations, model version, and rollback steps are documented.

Decision: release as a research prototype only, or return specific failed gates to Segment A or Segment B.

## Cross-cutting acceptance criteria

- **Correctness:** calculations match hand-checked fixtures and documented formulas.
- **Reproducibility:** model and preprocessing artifacts can be regenerated from versioned code and a recorded data checksum.
- **Privacy:** no raw audio is stored by the prototype unless explicitly added with a separate threat model and consent flow.
- **Safety:** the system never presents simulation output as observed clinical evidence.
- **Performance:** the documented vertical slice meets the 500 ms trajectory recalculation target under prototype load.
- **Observability:** every estimate and simulation is traceable to a model version, feature version, request ID, and timestamp.
- **Usability:** a new reviewer can complete the demo after reading the README.

## Risks and mitigations

| Risk | Effect | Mitigation |
|---|---|---|
| Patient leakage in validation | Inflated performance | Grouped patient-level and time-aware splits with automated checks |
| Recording or feature quality variation | Unstable estimates | Quality flags, validation thresholds, and visible insufficient-data states |
| Sparse longitudinal history | Misleading slope | Minimum-history rules and uncertainty display |
| Simulation interpreted as treatment advice | Safety harm | Hypothetical labeling, range checks, disclaimers, and no clinical recommendations |
| Model artifact drift | Inconsistent results | Version every artifact and store its metadata with each estimate |
| Duplicate or out-of-order updates | Corrupt state | Idempotency keys, timestamp policy, optimistic concurrency, and audit events |
| Sensitive data in logs or demos | Privacy exposure | Structured redacted logs and synthetic demo fixtures |
| 500 ms target missed | Poor interactive experience | Profile each stage, cache safe reads, precompute stable trajectory data, and report tradeoffs |

## Definition of ready for a task

A task is ready when its input schema, expected output, owner role, test strategy, dependency, and acceptance condition are written down. Tasks that change model behavior also need a model-versioning and evaluation note before implementation.

## Definition of done for a release

A release is done only when all checkpoint gates pass, the critical path is tested, the demo is reproducible, limitations are explicit, and the artifact remains clearly non-diagnostic.
