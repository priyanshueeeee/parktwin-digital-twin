# Flow Sequences

This document explains how each part should be implemented and how data moves through the system. The sequences are intentionally explicit so they can become tests, API contracts, and demo scripts.

## 1. Training and model publication

```text
Dataset source
    |
    v
Acquire -> checksum -> store outside Git
    |
    v
Validate schema, types, ranges, missingness, duplicates
    |
    v
Split by patient and time
    |
    v
Fit preprocessing on training data only
    |
    v
Train baseline and challenger regressors
    |
    v
Evaluate population and per-patient metrics
    |
    v
Register model + preprocessing + data checksum + report
    |
    v
Promote an approved artifact for inference
```

Implementation sequence:

1. Add a dataset adapter that maps source columns to the internal data dictionary.
2. Fail the pipeline on missing required columns or unexpected units.
3. Produce a machine-readable validation report before training.
4. Generate patient-grouped and time-aware partitions.
5. Fit imputation/scaling/feature-selection steps only on training data.
6. Train a simple interpretable baseline first.
7. Train a challenger only after the baseline has reproducible metrics.
8. Evaluate Total and Motor UPDRS separately.
9. Save model, preprocessing, configuration, feature list, code version, source checksum, and metrics together.
10. Promote the artifact only when leakage and reproducibility checks pass.

Required tests:

- schema validation rejects malformed input;
- patient IDs do not overlap across the intended partitions;
- preprocessing cannot be fit using validation/test data;
- the same artifact produces the same prediction for the same input;
- model metadata is complete.

## 2. Twin creation flow

```text
Client
  -> POST /twin/create
  -> authenticate and authorize
  -> validate pseudonymous reference and baseline
  -> begin transaction
  -> create Twin
  -> persist immutable baseline Observation
  -> run state estimator
  -> persist StateEstimate
  -> calculate initial trajectory status
  -> commit
  -> return twin ID, estimate, warnings, and request ID
```

How to implement:

1. Require a client-generated idempotency key or derive one from a safe source event ID.
2. Validate every speech metric against schema and configured bounds.
3. Allow partial baseline only if the response clearly says the twin is `insufficient_data`.
4. Do not create a fake UPDRS value when the estimator cannot run.
5. Store the baseline observation unchanged.
6. Run the model through the same inference path used by later updates.
7. Calculate a trajectory only if the minimum history rule permits it.
8. Return model metadata and quality flags so the UI can explain the state.

Failure behavior:

- invalid payload: `400 VALIDATION_ERROR`;
- unauthorized twin context: `401` or `403`;
- duplicate idempotency key with same payload: return the original result safely;
- duplicate key with different payload: `409 IDEMPOTENCY_CONFLICT`;
- model unavailable: `503 MODEL_UNAVAILABLE`, with no partial state committed.

## 3. Continuous update flow

```text
New speech feature vector
  -> POST /twin/update
  -> validate access, schema, range, and timestamp
  -> check idempotency and ordering
  -> run model inference
  -> write immutable observation
  -> write state estimate
  -> recalculate trajectory and quality flags
  -> optimistic latest-state update
  -> return updated state
```

How to implement:

1. Confirm the twin exists and the caller can access it.
2. Reject an observation with an invalid timestamp or make the out-of-order policy explicit.
3. Check whether the source event was already accepted.
4. Validate the full feature vector; do not silently drop unknown fields.
5. Run inference with a pinned artifact.
6. Persist the observation and estimate in one transaction.
7. Recalculate the slope using all valid points in the configured window.
8. Set warnings for sparse history, low-quality input, extrapolation, or stale model metadata.
9. Use optimistic concurrency so two updates cannot silently replace each other.
10. Return the updated trajectory summary, not only the new scalar estimate.

## 4. Trajectory retrieval flow

```text
Dashboard
  -> GET /twin/{id}/trajectory
  -> authorize
  -> load observations and estimates by time range
  -> load selected scenario if requested
  -> calculate or load derived slope
  -> attach quality and model metadata
  -> return series for rendering
```

How to implement:

1. Default to the production twin's observed and estimated data only.
2. Require an explicit scenario ID for hypothetical data.
3. Return a stable point shape with timestamp, value, source type, and warnings.
4. Include the slope definition and units in the response.
5. Return `insufficient_data` rather than a zero or placeholder slope.
6. Preserve the distinction between observed UPDRS, model-estimated UPDRS, and simulated values.
7. Bound query ranges and paginate or downsample safely for long histories.

## 5. Intervention simulation flow

```text
User adjusts scenario controls
  -> POST /twin/{id}/simulate
  -> authorize and snapshot current twin state
  -> validate intervention parameters and horizon
  -> create isolated scenario
  -> apply versioned hypothetical response function
  -> calculate scenario trajectory
  -> compare with baseline
  -> return scenario only; do not mutate observed state
```

How to implement:

1. Require explicit scenario parameters and forecast horizon.
2. Enforce safe bounds and reject unsupported combinations.
3. Read the twin at a consistent version so the baseline is reproducible.
4. Copy derived state into an in-memory or scenario-specific structure.
5. Apply intervention response assumptions as a pure function.
6. Recalculate trajectory points at a documented time step.
7. Return the assumptions version, parameter values, baseline series, scenario series, and warnings.
8. Store the scenario for reproducibility if persistence is enabled, but never write it into observed history.
9. Label every result `hypothetical` in both API and UI.

The response function must be treated as a prototype assumption until supported by appropriately designed data. The system must not output a medication recommendation, dose instruction, or clinical directive.

## 6. Dashboard rendering flow

```text
Open patient/twin
  -> load baseline and current trajectory
  -> render data-quality and safety status
  -> render observed and estimated lines
  -> display slope and model metadata
  -> accept scenario controls
  -> request simulation
  -> render baseline and hypothetical lines together
  -> allow reset without altering the twin
```

How to implement:

1. Keep server state authoritative.
2. Use a loading state while trajectory data is fetched.
3. Render an empty state for insufficient history.
4. Use separate styles and legends for observed, estimated, and simulated points.
5. Display timestamp, units, slope definition, and data coverage near the chart.
6. Show warnings before the user interprets a low-quality or sparse trajectory.
7. Debounce slider changes or require an explicit Simulate action to avoid excessive requests.
8. Keep the last valid result visible while a new simulation is running, with a clear pending state.
9. Provide Reset Scenario to return to baseline without a write request.
10. Include the non-diagnostic disclaimer in the main experience, not only in documentation.

## 7. Patient-specific tuning flow

```text
Population model estimate
  -> collect multiple valid observations for one twin
  -> verify minimum history and quality
  -> estimate individual response adjustment
  -> compare tuned vs untuned error in evaluation
  -> enable only behind a versioned feature flag
  -> show tuning status and limitations
```

How to implement:

1. Start with the population model as the default.
2. Define a minimum number and time span of observations before tuning.
3. Estimate only a bounded adjustment, such as an intercept or slope correction.
4. Do not tune on a single observation.
5. Evaluate tuning with a held-out future observation or time block.
6. Store the tuning method and version with the estimate.
7. Revert to the population model when history becomes stale or quality falls below threshold.

## 8. Error and recovery flow

```text
Error detected
  -> classify validation / authorization / conflict / model / persistence / timeout
  -> log redacted event with request ID
  -> return stable public error
  -> preserve immutable records if a derived calculation fails
  -> retry only safe operations
  -> expose degraded state when necessary
```

Rules:

- Never retry a non-idempotent write without an idempotency key.
- Never commit an observation without either its estimate or an explicit processing status.
- If trajectory calculation fails after the immutable write, mark derived state stale and provide a recoverable job or reprocessing path.
- Do not expose stack traces, SQL, raw features, or identifiers in client errors.

## 9. End-to-end vertical slice

```text
Synthetic baseline
  -> create twin
  -> read initial state
  -> submit weekly update
  -> read trajectory and slope
  -> run intervention simulation
  -> verify observed history is unchanged
  -> render dashboard
```

Acceptance test:

1. Seed one synthetic twin with a baseline.
2. Confirm the response contains a stable twin ID and model metadata.
3. Submit at least one later observation.
4. Confirm the new observation is immutable and the estimate is versioned.
5. Retrieve the trajectory and verify chronological order and slope behavior.
6. Run a simulation and verify the scenario is labeled hypothetical.
7. Retrieve the production trajectory again and verify it is byte-for-byte unchanged except for normal request metadata.
8. Measure end-to-end trajectory recalculation against the 500 ms target.
9. Run the browser critical-path test against the same API.

## 10. Release and demonstration flow

```text
Clean checkout
  -> install dependencies
  -> start database
  -> apply migrations
  -> load synthetic fixture
  -> start API and frontend
  -> run health checks
  -> execute demo script
  -> collect test and performance evidence
  -> publish model/API/UI versions and limitations
```

The demo must show:

- baseline twin creation;
- an update from new voice features;
- an updated trajectory and slope;
- an intervention scenario;
- the separation between observed data and hypothetical output;
- the non-diagnostic limitation.

No personal names, raw patient data, or unapproved identifiers should appear in the demo, screenshots, logs, or example payloads.

## 11. Voice capture to inference-mode datapoint

```text
Browser microphone capture
  -> consent and bounded recording
  -> approved PCM WAV payload
  -> in-memory format and quality validation
  -> proxy or validated feature extraction
  -> VoiceDataPoint with feature method/version
  -> InferenceInput
  -> inference adapter
  -> InferenceResult with estimates, trace data, and warnings
```

How to implement:

1. Capture audio only after an explicit user action and consent state.
2. Enforce a maximum duration and payload size before processing.
3. Use PCM WAV for the initial contract; do not silently accept arbitrary browser containers.
4. Process the payload in memory and discard raw bytes after extraction.
5. Emit duration, sample rate, channel count, feature method, and quality flags.
6. Keep the current `demo_signal_proxy_v1` output visibly marked as a proxy, not a clinical feature extractor.
7. Pass quality flags into inference results rather than hiding them.
8. Return raw and derived datapoints, model version, feature-set version, and warnings for the demo view.
9. Never put raw audio, real names, or full feature payloads into ordinary logs.
10. If a validated biomedical extractor replaces the proxy, keep the same datapoint contract and add a new extractor version.

Segment B owns the browser microphone component and API upload. Segment A owns this processing boundary, the feature contract, and inference behavior.

## 12. Multi-scenario simulation and sensitivity flow

```text
Current twin state and slope
  -> construct isolated scenario requests
  -> validate horizon, step, and normalized intensities
  -> apply versioned assumptions
  -> calculate baseline and scenario points
  -> compare scenarios or vary one parameter
  -> return hypothetical results and warnings
```

How to implement:

1. Read a consistent snapshot of the current derived twin state.
2. Build one immutable request per scenario; do not mutate the production twin.
3. Bound the Levodopa and physical-therapy intensities to the documented normalized range.
4. Apply a named assumptions version and record it in every result.
5. Calculate baseline and simulated Total UPDRS, plus Motor UPDRS when available.
6. Clamp display scores to the supported 0-199 range without hiding that clamping occurred.
7. Mark all scenario points as hypothetical and non-treatment guidance.
8. For sensitivity analysis, vary one parameter at a time and keep all other inputs fixed.
9. Compare final values and deltas against the same baseline trajectory.
10. Return the assumptions, warnings, and scenario IDs so the UI can explain the result.

The simulator is a visualization and engineering test tool. It must not output a dose, treatment plan, or causal clinical claim.
