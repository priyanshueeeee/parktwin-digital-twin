# Segment A Extensions

Segment A now covers more than the original baseline model path. It provides a controlled place for feature experiments, model-approach comparison, scenario simulation, and inference-mode demonstrations from voice datapoints.

## Capability matrix

| Capability | Current status | Boundary |
|---|---|---|
| Canonical 16-feature schema | Implemented | `ml/data/schema.py` |
| Raw and derived feature vectors | Implemented | `ml/features/engineering.py` |
| Candidate model registry | Implemented | `ml/models/approaches.py` |
| Deterministic inference demo | Implemented | `ml/inference/demo.py` |
| In-memory WAV datapoint extraction | Implemented as a demo proxy | `ml/voice/audio.py` |
| Versioned multi-scenario simulation | Implemented | `backend/app/services/simulation.py` |
| Trained Elastic Net/tree/quantile models | Implemented | Training pipeline, metrics, manifests, and joblib artifacts |
| Research biomedical speech extractor | Implemented as evaluation-ready | `research_acoustic_v1_approx`; clinical validation still requires reference audio/features |
| Browser microphone recording | Segment B integration | Captures audio and sends an approved format to Segment A |

## 1. Expanded feature engineering

The original dataset has 16 voice metrics. Segment A preserves all raw values and can add deterministic derived features:

- jitter-family mean and standard deviation;
- shimmer-family mean and standard deviation;
- perturbation ratio;
- harmonicity ratio;
- nonlinear-complexity mean from RPDE, DFA, and PPE;
- `log1p` transforms for skewed jitter and shimmer values.

Every feature vector carries a `feature_set_version`. A model artifact must record the exact feature-set version used during training. Derived features are candidate predictors, not validated biomarkers.

### Rules

1. Do not mutate source rows.
2. Reject missing, non-numeric, or non-finite values before feature construction.
3. Keep raw features available for interpretation and ablation tests.
4. Compare raw-only, derived-only, and raw-plus-derived matrices.
5. Fit any learned imputation, scaling, selection, or dimensionality reduction on training data only.
6. Report feature distributions and per-patient drift before model promotion.

## 2. Additional modeling approaches

The approach registry makes the experiment plan explicit:

| Approach | Role | Main evidence required |
|---|---|---|
| Elastic Net | Interpretable population baseline | grouped/time-aware MAE, RMSE, R², coefficient stability |
| Random Forest | Nonlinear challenger | held-out patient performance, calibration, feature importance stability |
| Histogram Gradient Boosting | Strong tabular challenger | time-block performance, robustness to feature interactions |
| Quantile Regression | Uncertainty reporting | interval coverage and interval width |
| Patient-calibrated residual | Bounded personalization | future-observation validation and calibration drift |
| Demo heuristic | Local inference demonstration only | deterministic behavior and visible warnings |

The registry does not select a model automatically. A future training pipeline should:

1. run every eligible approach against the same patient-level splits;
2. compare population and per-patient errors;
3. report missingness and quality strata;
4. evaluate calibration or prediction intervals;
5. select a model only with a recorded promotion decision;
6. preserve the baseline even when a challenger scores better;
7. keep patient-specific tuning behind a feature flag.

## 3. Inference-mode demonstration

`DemoInferenceAdapter` demonstrates the full path without pretending to be a trained clinical model:

```text
features
  -> feature engineering
  -> deterministic demo estimator
  -> Total UPDRS estimate
  -> Motor UPDRS estimate
  -> model version, feature version, warnings, and trace data
```

The result includes:

- the datapoint ID;
- raw input features;
- derived features;
- model and feature versions;
- inference mode and source;
- estimated Total and Motor UPDRS;
- warnings such as `DEMO_HEURISTIC_MODEL` and `NON_CLINICAL_ESTIMATE`.

The demo adapter is useful for UI wiring, contract tests, and a local presentation. It must be replaced by a promoted model artifact for any real evaluation.

## 4. Voice recording and datapoint path

Segment A defines the processing boundary; Segment B will later provide browser capture.

```text
Browser microphone capture
        |
        v
Approved PCM WAV payload
        |
        v
In-memory quality checks
        |
        v
Proxy or validated biomedical feature extractor
        |
        v
VoiceDataPoint
        |
        v
InferenceInput
        |
        v
InferenceResult
```

The current extractor accepts PCM WAV bytes and emits a 16-feature `VoiceDataPoint` using `demo_signal_proxy_v1`. It calculates quality flags for short recordings, low sample rate, low signal, clipping, and silence. It never returns or stores raw audio.

### Capture contract

The future API/UI boundary should provide:

- opaque datapoint ID;
- audio format and sample rate;
- capture duration;
- a bounded payload size and duration;
- consent and processing-purpose metadata;
- no real name in the model payload;
- an explicit retention choice, defaulting to no raw-audio retention.

The browser should send PCM WAV or a server-side conversion should be added as a separately reviewed component. The current standard-library extractor does not silently decode WebM, Opus, or arbitrary container formats.

### Quality behavior

Quality flags are returned with the datapoint rather than hidden. The inference layer passes them through to the result. A later API/UI layer can decide whether to block inference, show a warning, or allow a demo result, but the model layer must not silently discard them.

## 5. Expanded simulation

The simulation service supports:

- normalized Levodopa and physical-therapy scenario intensities;
- a configurable forecast horizon and time step;
- Total and optional Motor UPDRS trajectories;
- baseline and simulated points side by side;
- multiple isolated scenarios;
- sensitivity analysis across intervention levels;
- a versioned assumptions object;
- explicit hypothetical and non-treatment warnings.

The prototype assumes that interventions alter a progression slope and may have a bounded response effect. These are engineering assumptions for a what-if visualization, not causal or clinical effect estimates.

### Simulation invariants

- Observed history is never mutated.
- Scenario output is always marked hypothetical.
- Inputs are bounded and validated.
- Scores are clamped to the UPDRS display range of 0 to 199.
- Every result carries an assumptions version.
- Sensitivity analysis varies one parameter at a time.
- No output recommends a dose, treatment, or clinical action.

## 6. Completed implementation stages

1. Leakage-safe patient/time splitting is implemented.
2. Elastic Net, tree, and quantile training is implemented.
3. Model artifact metadata, joblib serialization, and trained inference are implemented.
4. Quantile interval output and coverage metrics are implemented.
5. A research acoustic extractor and reference-comparison harness are implemented.
6. Segment B browser capture and API upload remain integration work.
7. End-to-end audio-to-dashboard testing remains integration work.

The UCI tabular file is sufficient for model training but does not validate the audio extractor because it contains precomputed feature columns rather than raw audio. The extractor therefore remains evaluation-ready, not clinically validated.

## 7. Acceptance criteria

- Feature-set versions are present in inference results and future model artifacts.
- Raw audio is not retained by default.
- Demo inference is deterministic and clearly labeled non-clinical.
- Simulation results are isolated from observed state.
- Scenario sensitivity results are reproducible.
- Quality flags are visible to downstream consumers.
- No real patient identifiers or raw recordings appear in fixtures, logs, or screenshots.
