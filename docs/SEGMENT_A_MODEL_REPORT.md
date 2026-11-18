# Segment A Model and Extractor Report

This report records the first reproducible training run and the current speech-extractor validation boundary. It is evidence for a research prototype, not a clinical validation report.

## Training source and protocol

- Dataset: [UCI Parkinsons Telemonitoring](https://archive.ics.uci.edu/dataset/189/parkinson)
- Rows loaded: 5,875
- Patients: 42
- Feature matrix: raw 16 features plus deterministic derived features
- Feature-set version: `feature-set-v1-derived-v1`
- Split: future-time holdout per patient
- Training rows: 4,684
- Test rows: 1,191
- Patients in train/test: 42/42; this is a temporal test, not an unseen-patient test
- Model version: `parktwin-segment-a-v1`
- Targets: `total_UPDRS` and `motor_UPDRS`
- Artifacts: generated under ignored `ml/artifacts/total/` and `ml/artifacts/motor/`

The source file contains precomputed voice measures and UPDRS targets. It does not provide raw audio for validating an audio feature extractor.

## Total UPDRS future-time results

| Approach | MAE | RMSE | R² |
|---|---:|---:|---:|
| Elastic Net | 8.4067 | 10.5654 | 0.0792 |
| Random Forest | 7.2830 | 9.2589 | 0.2929 |
| Histogram Gradient Boosting | 7.5547 | 9.4811 | 0.2585 |
| Quantile Regression median | 8.3760 | 10.9870 | 0.0043 |

Quantile interval coverage was 0.7498 with mean interval width 26.0163.

## Motor UPDRS future-time results

| Approach | MAE | RMSE | R² |
|---|---:|---:|---:|
| Elastic Net | 6.4776 | 7.8980 | 0.1044 |
| Random Forest | 5.6603 | 7.1150 | 0.2732 |
| Histogram Gradient Boosting | 5.8804 | 7.2916 | 0.2367 |
| Quantile Regression median | 6.6639 | 8.1267 | 0.0518 |

Quantile interval coverage was 0.7271 with mean interval width 20.0076.

## Interpretation

- Random Forest had the lowest MAE in this first temporal evaluation for both targets.
- The less-than-10% error question from the presentation is not demonstrated by this run. The result must not be described as meeting that target.
- The temporal split tests future observations from known patients. A separate grouped-patient evaluation is still required before making claims about generalization to unseen patients.
- The quantile intervals are not calibrated clinical confidence intervals; coverage must be evaluated and calibrated on a separate validation protocol.

## Reproduction

```bash
python3 -m ml.training.cli \
  --data data/raw/parkinsons_updrs.data \
  --output ml/artifacts/total \
  --target total_UPDRS \
  --feature-mode raw_plus_derived \
  --split future

python3 -m ml.training.cli \
  --data data/raw/parkinsons_updrs.data \
  --output ml/artifacts/motor \
  --target motor_UPDRS \
  --feature-mode raw_plus_derived \
  --split future
```

The raw dataset and generated joblib artifacts are ignored by Git. Record their checksums and manifest files in an approved experiment store before promoting a model.

## Biomedical extractor status

Segment A now includes `research_acoustic_v1_approx`, which calculates pitch-period, jitter, shimmer, harmonicity, and entropy/fractal-style features from bounded PCM WAV input. It also includes a reference-comparison harness.

The extractor is not clinically validated. The UCI training file contains extracted feature columns rather than raw speech, so it cannot establish agreement between audio and the dataset's source feature computation. Clinical or production promotion requires:

1. approved raw speech and consent/retention controls;
2. a trusted reference extractor or reference feature vectors;
3. per-feature tolerance and failure analysis;
4. quality-stratified and speaker-stratified evaluation;
5. reproducible evidence reviewed separately from model accuracy.
