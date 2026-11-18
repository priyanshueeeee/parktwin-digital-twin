# System Architecture

## 1. Architectural intent

The system is a modular digital twin service with a clear boundary between:

1. data validation and feature preparation;
2. model inference;
3. persistent twin state;
4. trajectory calculation;
5. isolated intervention simulation;
6. REST transport; and
7. dashboard presentation.

The design keeps observed data immutable, makes every estimate traceable, and prevents hypothetical simulation state from changing the production twin.

## 2. Context diagram

```text
                         +----------------------+
                         | Clinician / reviewer |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | React/D3 dashboard   |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | REST API service     |
                         +---+--------------+---+
                             |              |
                             v              v
                 +----------------+   +-------------------+
                 | Twin state     |   | Simulation service |
                 | & trajectory   |   | (scenario only)   |
                 +-------+--------+   +---------+---------+
                         |                        |
                         +-----------+------------+
                                     v
                         +----------------------+
                         | PostgreSQL           |
                         | twins, observations,|
                         | estimates, audit     |
                         +----------------------+

  Approved dataset ---> training/evaluation pipeline ---> versioned model artifact
                                                         |
                                                         v
                                                  inference service
```

## 3. Container responsibilities

### 3.1 Data and ML pipeline

Responsibilities:

- ingest the approved dataset;
- validate schema and ranges;
- create leakage-safe splits;
- transform the 16 voice metrics;
- train and evaluate Total and Motor UPDRS regressors;
- publish a versioned artifact and evaluation report.

It must not write directly into live patient or twin tables. Training outputs are promoted through an explicit artifact registration step.

### 3.2 Inference service

Responsibilities:

- load the approved model and preprocessing artifact;
- validate a feature vector;
- return UPDRS estimates and quality metadata;
- report model and feature versions;
- remain deterministic for the same artifact, inputs, and configuration.

If the model cannot load, the service must fail closed with a clear operational error rather than silently using a different model.

### 3.3 Twin state service

Responsibilities:

- create a twin from a baseline;
- append valid observations;
- preserve immutable raw observations;
- maintain the latest derived state;
- enforce timestamp and concurrency rules;
- call the inference and trajectory components.

Derived state can be recomputed from immutable records. This provides a recovery path if a calculation algorithm changes.

### 3.4 Trajectory engine

Responsibilities:

- order observations by time;
- combine observed and estimated UPDRS values;
- calculate the documented slope;
- apply minimum-history and quality rules;
- return point estimates, windows, and flags.

Suggested prototype rule: calculate slope only when a twin has at least two valid time-separated observations. The exact window and robust regression method must be configured and recorded, not hidden in code.

### 3.5 Simulation service

Responsibilities:

- clone the current derived state into a scenario;
- validate intervention inputs and horizon;
- apply a versioned hypothetical response function;
- recalculate a scenario-only trajectory;
- return baseline and scenario series with assumptions.

It must never update the observed observation table or production latest-state fields.

### 3.6 REST API

Responsibilities:

- authenticate and authorize requests;
- validate request schemas;
- map domain results to stable response schemas;
- emit request IDs and structured errors;
- expose OpenAPI documentation;
- enforce rate limits and payload-size limits appropriate for the prototype.

### 3.7 Dashboard

Responsibilities:

- collect and display valid inputs;
- render observed, estimated, and simulated series distinctly;
- show quality, uncertainty, timestamps, and model versions;
- make hypothetical output visually unmistakable;
- provide useful loading and error states;
- never calculate a clinical value locally without showing its source and version.

### 3.8 Voice capture and datapoint boundary

Voice capture is a product-surface responsibility, while voice validation and feature conversion are Segment A responsibilities.

- Segment B may capture microphone input after consent and send an approved PCM WAV payload.
- Segment A validates format, duration, sample rate, size, and signal quality in memory.
- A feature extractor emits a `VoiceDataPoint` with a feature method version and quality flags.
- The inference adapter consumes the datapoint and returns traceable estimates.
- Raw audio is not retained by default and must not appear in ordinary logs.
- The current `demo_signal_proxy_v1` extractor is a demonstration proxy, not a validated biomedical extractor.
- A future validated extractor may replace the proxy while preserving the datapoint and inference contracts.

## 4. Domain model

```text
Twin 1 ---- many Observation
Twin 1 ---- many StateEstimate
Twin 1 ---- many SimulationScenario
SimulationScenario 1 ---- many ScenarioPoint
ModelMetadata 1 ---- many StateEstimate
```

### Twin

Suggested fields:

- `id`: opaque UUID;
- `external_reference`: optional pseudonymous reference, never a real name;
- `created_at`, `updated_at`;
- `status`: `active`, `insufficient_data`, `paused`, or `archived`;
- `latest_state_id`;
- `data_quality_summary`;
- `schema_version`.

### Observation

Suggested fields:

- `id`, `twin_id`;
- `observed_at`;
- the validated 16 speech metrics;
- optional observed Total and Motor UPDRS values;
- source and quality metadata;
- an idempotency key or source event ID;
- immutable creation metadata.

### StateEstimate

Suggested fields:

- `id`, `twin_id`, `observation_id`;
- estimated Total and Motor UPDRS;
- uncertainty or interval fields when supported;
- quality flags;
- `model_version`, `feature_version`;
- `created_at`.

### TrajectoryPoint

This can be materialized or computed on demand. It should include:

- timestamp;
- observed values, estimated values, or both;
- source type;
- scenario ID when simulated;
- quality flags.

### SimulationScenario

Suggested fields:

- `id`, `twin_id`;
- intervention parameters;
- forecast horizon and step size;
- assumptions version;
- baseline trajectory reference;
- output status;
- created timestamp;
- no mutation link to observed records.

### VoiceDataPoint

Suggested fields:

- opaque datapoint ID;
- canonical 16-feature vector;
- duration, sample rate, and channel count;
- feature method version;
- quality flags;
- raw-audio-retained flag, which defaults to `false`.

### InferenceResult

Suggested fields:

- datapoint ID and source;
- estimated Total and Motor UPDRS;
- model version and feature-set version;
- inference mode;
- raw and derived input features for traceability;
- warnings and quality flags.

### ScenarioPoint

Suggested fields:

- forecast day or timestamp;
- baseline and simulated Total UPDRS;
- optional baseline and simulated Motor UPDRS;
- scenario ID;
- assumptions version;
- hypothetical-output warning.

## 5. Data flow

```text
Raw approved data
    -> schema/range checks
    -> patient/time-aware split
    -> fit preprocessing on train only
    -> train regressors
    -> evaluate and register artifact
    -> serve inference

New observation
    -> request validation
    -> quality checks
    -> inference
    -> immutable observation write
    -> estimate write
    -> trajectory recalculation
    -> latest-state update
    -> API response

Voice capture path
    -> approved PCM WAV payload
    -> bounded in-memory audio validation
    -> quality checks
    -> proxy or validated biomedical feature extraction
    -> VoiceDataPoint
    -> inference adapter
    -> InferenceResult with warnings and model metadata
```

## 6. API contracts

All responses should include:

```json
{
  "request_id": "opaque-request-id",
  "schema_version": "v1",
  "data": {},
  "warnings": []
}
```

Error responses should follow one shape:

```json
{
  "request_id": "opaque-request-id",
  "schema_version": "v1",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The observation contains an unsupported feature value.",
    "fields": [
      {"name": "jitter_local", "reason": "must be non-negative"}
    ]
  }
}
```

### `POST /twin/create`

Input should contain a pseudonymous reference, baseline timestamp, a complete or explicitly partial feature vector, and optional baseline UPDRS values.

Processing:

1. validate schema, ranges, timestamp, and pseudonymous reference;
2. create the twin and baseline observation in one transaction;
3. run inference when the feature vector is sufficient;
4. calculate the initial derived state and quality flags;
5. return the twin ID, current estimate, and trajectory status.

### `POST /twin/update`

Input should contain the twin ID, observation timestamp, all required features, optional observed UPDRS, and an idempotency key.

Processing:

1. authorize access to the twin;
2. reject duplicate idempotency keys as safe repeats;
3. validate feature values and timestamp policy;
4. run inference using the registered model;
5. persist the immutable observation and estimate;
6. recalculate the derived state and slope;
7. update the latest state with optimistic concurrency;
8. return the new estimate, slope status, and warnings.

### `GET /twin/{id}/trajectory`

Query parameters should include an optional start/end time, series selection, and scenario selection.

Response should include observed points, estimated points, slope, data coverage, quality flags, model metadata, and a non-diagnostic warning. No simulation data should appear unless explicitly requested by scenario ID.

### `POST /twin/{id}/simulate`

Input should include a scenario label, Levodopa and/or physical-therapy parameters, forecast horizon, step size, and an explicit acknowledgment that the result is hypothetical.

Processing:

1. authorize access to the twin;
2. load a consistent read snapshot;
3. validate parameter ranges and horizon;
4. create an isolated scenario record;
5. apply the versioned intervention response function;
6. calculate scenario points without writing production observations;
7. return baseline and scenario trajectories plus assumptions and warnings.

## 7. Persistence and consistency

- Use transactions for twin creation and observation-plus-estimate writes.
- Use optimistic concurrency on latest-state updates.
- Keep raw observations immutable; corrections should create a new event or an audited correction record.
- Index by `twin_id, observed_at` for trajectory queries.
- Store model and feature versions on each estimate.
- Store audit events for create, update, simulation, model promotion, and administrative access.
- Keep derived values recomputable from the immutable event history.
- Do not persist raw audio in the prototype; persist only approved derived datapoint metadata when needed for reproducibility.

## 8. Security and privacy

Minimum prototype controls:

- use pseudonymous IDs, not names, in the service;
- encrypt transport and database storage in deployed environments;
- apply least-privilege service accounts;
- validate and constrain all payloads;
- redact feature payloads and identifiers from logs;
- separate development, test, and production data;
- use synthetic fixtures in demos and automated tests;
- define retention and deletion behavior before storing real patient data;
- document consent and access-control assumptions if the prototype moves beyond public/de-identified data.

The prototype should not store raw audio unless a separate consent, retention, encryption, and threat-model decision is approved.

## 9. Observability

Record metrics for:

- request count, status, and latency by endpoint;
- validation failures by safe error code;
- inference latency;
- trajectory recalculation latency;
- simulation latency;
- model load failures;
- count of insufficient-data states;
- data-quality warning rates.

Do not record raw speech, feature vectors, or real identifiers in ordinary application logs.

## 10. Deployment shape

Local development can use Docker Compose with:

- API container;
- frontend container or local dev server;
- PostgreSQL;
- optional object storage for model artifacts.

The first deployed environment should add:

- managed secrets;
- TLS termination;
- authenticated access;
- database backups and migration checks;
- artifact registry or immutable artifact storage;
- health/readiness endpoints;
- alerting for API errors, model load failures, and latency regressions.

## 11. Performance plan

The 500 ms criterion should be measured end to end for the vertical slice and broken down into:

- request validation;
- model inference;
- database write/read;
- trajectory calculation;
- response serialization.

Use representative synthetic fixtures and document concurrency, hardware, dataset size, and whether the measurement is cold or warm. Optimize only after profiling. Safe options include indexes, bounded history windows, cached model loading, and precomputed derived trajectory values.

## 12. Architecture decisions to record

Before implementation, record decisions for:

- exact slope window and regression method;
- missing-data and outlier policy;
- uncertainty representation;
- model promotion criteria;
- feature-set and audio-extractor promotion criteria;
- voice payload format, retention, and consent policy;
- patient-specific tuning procedure;
- intervention response assumptions;
- authentication and authorization model;
- retention, deletion, and correction semantics.

These decisions materially affect interpretation and must not be left implicit.
