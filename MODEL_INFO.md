# ParkTwin: Machine Learning Architecture & Model Guide
*A Beginner-Friendly Guide to How the Model Works, How it Was Trained, Weights vs. Trees, Inputs, Outputs, and Predictions*

---

## 1. The Big Picture: What Problem is the Model Solving?

In traditional software engineering, humans write exact rules:
> *`if jitter > 0.005 then patient is severe`*

In medicine, human biology is far too complex for simple `if/else` rules. Parkinson's disease affects speech through a tangled combination of vocal tremors, loudness fluctuations, breathiness, and vocal cord chaos.

**Machine Learning (ML)** solves this by looking at thousands of historical examples where we have:
1. The **patient's voice measurements** (the input $X$).
2. The **neurologist's verified clinical score** (the target $y$, called **UPDRS**).

The ML algorithm learns the mathematical patterns connecting the voice measurements to the UPDRS score. When a new voice recording arrives from a patient at home, the model predicts their UPDRS score.

Because the target we are predicting is a continuous number (e.g. `48.1`), this is a **Regression** task (as opposed to classification, which predicts discrete categories like "cat" vs "dog").

---

## 2. What Dataset Was the Model Trained On?

The model was developed and benchmarked on the gold-standard research dataset in this domain:
* **Dataset Name:** [UCI Parkinson's Telemonitoring Dataset](https://archive.ics.uci.edu/dataset/189/parkinson)
* **Creator / Origin:** Oxford University & 10 medical centers across the US.
* **Size:** **5,875 voice recordings** across **42 early-stage Parkinson's patients**.
* **Time Span:** ~6 months of longitudinal telemonitoring.
* **Recording Protocol:** Patients had an at-home telecommunication device. Once or twice weekly, they held a steady vowel sound (*"aaah"*) into a microphone for 5 seconds.
* **Ground Truth:** Throughout the 6 months, neurologists performed regular in-person clinical exams to record the patients' true **Motor UPDRS** (`0–108`) and **Total UPDRS** (`0–199`) scores.

---

## 3. Does it Use Weights & Biases, or a Formula, or Decision Trees?

This is the most common question when learning ML. In ParkTwin, the system actually implements **multiple candidate modeling approaches** in `ml/models/approaches.py` and `ml/models/training.py`:

```
+--------------------------------------------------------------------------------------------------+
|                                    CANDIDATE MODEL FAMILIES                                      |
+--------------------------------------------------------------------------------------------------+
|                                                                                                  |
|  1. ElasticNet (Linear Regression)    ---> Uses explicit WEIGHTS and a BIAS (a linear formula)   |
|  2. Random Forest (Ensemble Trees)    ---> Uses 200 DECISION TREES (if/else branching rules)     |
|  3. HistGradientBoosting (GBDT)       ---> Uses SEQUENTIAL GRADIENT BOOSTED TREES                |
|  4. Quantile Regression               ---> Predicts CONFIDENCE INTERVALS (10th & 90th percentile)|
|  5. Demo Heuristic Engine (In Dashboard) -> Fast deterministic physiological formula for UI demo  |
+--------------------------------------------------------------------------------------------------+
```

Here is exactly how each works:

### Approach A: ElasticNet — "Yes, it uses Weights and Biases (a Linear Formula)!"
ElasticNet is a regularized linear model. It learns an explicit algebraic formula:

$$\text{Estimated UPDRS} = b + (w_1 \cdot x_1) + (w_2 \cdot x_2) + \dots + (w_n \cdot x_n)$$

* **$x_1, x_2, \dots$** are the voice features (Jitter, Shimmer, NHR, etc.).
* **$w_1, w_2, \dots$** are the **Weights** (coefficients). A weight determines how much each feature influences the disease score. If feature $x_1$ has a positive weight $+15.2$, higher jitter increases the estimated UPDRS.
* **$b$** is the **Bias** (y-intercept). It represents the baseline UPDRS score when all normalized features are at zero.
* **How it learns:** During training, the computer starts with random weights. It measures how far off its guesses are (using **Mean Squared Error**) and uses optimization to tweak $w$ and $b$ until errors are minimized.

---

### Approach B: Random Forest — "No Weights/Biases; It Uses an Army of Decision Trees!"
In the benchmarks (`docs/SEGMENT_A_MODEL_REPORT.md`), **Random Forest achieved the best performance** ($\text{MAE} \approx 7.28$ UPDRS points).

Random Forest does **not** use a single mathematical formula or weights and biases. Instead, it builds **200 Decision Trees** (`n_estimators=200`).

#### What a single Decision Tree looks like:
```text
                  Is Jitter (%) > 0.005?
                         /      \
                      YES        NO
                      /            \
         Is Shimmer > 0.03?       Is NHR > 0.02?
              /     \                 /     \
           YES       NO            YES       NO
           /           \           /           \
     UPDRS=52.4    UPDRS=41.1  UPDRS=36.0   UPDRS=22.5
```

#### Why a "Forest"?
A single tree can be brittle and overfit to noise. A **Random Forest** creates 200 different trees, where each tree is trained on a random slice of patients and looks at random subsets of features.
* When a new voice recording arrives, **all 200 trees cast an independent prediction**.
* The algorithm **averages all 200 predictions** together to produce the final estimated UPDRS!
* This ensemble averaging cancels out random noise and creates a smooth, highly accurate prediction.

---

### Approach C: The Demo Engine (`mock-updrs-v0.1.0` in your screenshot)
In your running dashboard screenshot, you see `mock-updrs-v0.1.0 [mock]`. 
* **What is it?** It is a fast, deterministic, calibrated simulation engine (`DemoInferenceAdapter` in `ml/inference/demo.py`).
* **Why does it exist?** It allows anyone (including you tomorrow!) to run and demonstrate the entire full-stack app, submit voice recordings, and run simulations with **instant sub-15ms response times** without having to download 50MB model binary files or raw clinical datasets into the git repository.
* **How does it compute UPDRS?** It calculates a physiological symptom burden index from the 16 features:
  $$\text{Burden} = 0.35 \cdot \text{JitterSignal} + 0.35 \cdot \text{ShimmerSignal} + 0.15 \cdot \text{NoiseSignal} + 0.15 \cdot \text{Complexity}$$
  $$\text{Total UPDRS} = \text{clamp}\Big(18.0 + 85.0 \cdot \text{Burden} + 8.0 \cdot \text{PPE},\ 0,\ 199\Big)$$

---

## 4. The Inputs: What Does the Model Take In?

The model accepts **16 raw biomedical speech metrics** extracted from a 5-second recording of a sustained vowel *"aaah"*:

| # | Feature Name | Category | What It Measures Physically | Typical Normal Range |
|---|---|---|---|---|
| 1 | `jitter_percent` | Pitch Instability | Relative cycle-to-cycle variation in pitch frequency | $0.001 - 0.005$ ($0.1\% - 0.5\%$) |
| 2 | `jitter_abs` | Pitch Instability | Absolute pitch variation in microseconds | $0.00001 - 0.00004$ s |
| 3 | `jitter_rap` | Pitch Instability | Relative Average Perturbation (removes pitch drift) | $0.001 - 0.003$ |
| 4 | `jitter_ppq5` | Pitch Instability | 5-point Period Perturbation Quotient | $0.001 - 0.003$ |
| 5 | `jitter_ddp` | Pitch Instability | Average absolute difference of differences between cycles | $0.003 - 0.009$ |
| 6 | `shimmer` | Volume Instability | Relative cycle-to-cycle variation in sound wave amplitude | $0.01 - 0.03$ ($1\% - 3\%$) |
| 7 | `shimmer_db` | Volume Instability | Amplitude variation expressed in decibels (dB) | $0.1 - 0.3$ dB |
| 8 | `shimmer_apq3` | Volume Instability | 3-point Amplitude Perturbation Quotient | $0.005 - 0.015$ |
| 9 | `shimmer_apq5` | Volume Instability | 5-point Amplitude Perturbation Quotient | $0.007 - 0.020$ |
| 10 | `shimmer_apq11`| Volume Instability | 11-point Amplitude Perturbation Quotient | $0.010 - 0.025$ |
| 11 | `shimmer_dda` | Volume Instability | Average absolute difference between consecutive amplitudes | $0.015 - 0.045$ |
| 12 | `nhr` | Noise & Leakage | Noise-to-Harmonics Ratio (breathy air turbulence) | $0.005 - 0.020$ |
| 13 | `hnr` | Vocal Quality | Harmonics-to-Noise Ratio in dB (higher is clearer voice) | $20.0 - 35.0$ dB |
| 14 | `rpde` | Nonlinear Chaos | Recurrence Period Density Entropy (unpredictability) | $0.30 - 0.55$ |
| 15 | `dfa` | Signal Scaling | Detrended Fluctuation Analysis (fractal vocal scaling) | $0.55 - 0.75$ |
| 16 | `ppe` | Pitch Dysphonia | Pitch Period Entropy (impaired pitch control) | $0.10 - 0.25$ |

### Engineered (Derived) Features
Before passing features to the models, `ml/features/engineering.py` also computes **domain-specific derived features** that combine individual metrics:
* `jitter_family_mean`: Average across all 5 jitter algorithms.
* `shimmer_family_mean`: Average across all 6 shimmer algorithms.
* `nonlinear_complexity_mean`: Mean of RPDE, DFA, and PPE.
* `harmonicity_ratio`: Ratio of harmonic signal strength to acoustic noise.

---

## 5. The Outputs: What Does the Model Produce?

When the model finishes inference, it returns a structured dataclass containing:

1. **`estimated_total_updrs` (Float, e.g. `48.1`):** The primary estimate of overall disease burden on the 0–199 scale.
2. **`estimated_motor_updrs` (Float, e.g. `35.8`):** The estimated physical motor impairment subscore on the 0–108 scale.
3. **`total_updrs_ci_low` & `total_updrs_ci_high` (Floats, e.g. `44.9` to `51.3`):** The 95% Confidence Interval bounds (uncertainty envelope).
4. **`confidence_score` (Float between 0.0 and 1.0):** Data quality indicator.
5. **`quality_flags` (List of Strings):** Safety alerts (e.g., `PARTIAL_BASELINE_FEATURES`, `LOW_SIGNAL_HARMONICS_RATIO`).

---

## 6. How Did Training Prevent "Data Leakage"? (Crucial ML Concept)

In medical machine learning, **Data Leakage** is the #1 reason algorithms fail when deployed in hospitals. 

### What is Data Leakage in Longitudinal Studies?
If a patient has 100 recordings across 6 months, and you randomly shuffle all recordings into training and test sets, the model will memorize that specific patient’s unique voice timbre. When tested, it looks 99% accurate in the lab, but fails completely on new patients in the real world.

### How ParkTwin Solved This:
In `ml/models/training.py`, two strict validation strategies were implemented:

1. **Future-Time Holdout Split (`future`):**
   * For every patient, the model trains **only on their earlier recordings** (first 80% of time) and is evaluated **only on their future recordings** (last 20% of time).
   * This mirrors real clinical practice: the model can only use past data to predict the future.
2. **Grouped-Patient Split (`grouped_patient`):**
   * Uses `GroupShuffleSplit` so that **no patient appears in both the training set and the test set**.
   * It trains on 32 patients and tests on 10 completely unseen patients to verify that the model generalizes to new humans.
3. **Training-Set-Only Preprocessing:**
   * Feature scalers (`StandardScaler`) are fit **only on training data** and applied to test data, preventing distribution leakage.

---

## 7. Step-by-Step: How a Prediction Happens (Runtime Execution)

Here is the exact journey of a single prediction from start to finish:

```
[Patient Records "aaah"]
          |
          v
[1. Acoustic Extraction]  ---> Generates 16 numerical coefficients (Jitter, Shimmer, NHR, etc.)
          |
          v
[2. Pydantic Validation]   ---> backend/app/api/schemas.py ensures:
                                - All 16 numbers are finite and within physiologically valid ranges
                                - No personal names, emails, or PII exist in the payload
          |
          v
[3. Feature Engineering]   ---> ml/features/engineering.py calculates derived features
                                (jitter_family_mean, shimmer_family_mean, nonlinear_complexity)
          |
          v
[4. Model Inference]       ---> Active TwinEnginePort:
                                - Either 200 Random Forest decision trees cast their votes, OR
                                - ElasticNet evaluates the linear equation, OR
                                - Demo heuristic evaluates the calibrated burden index
          |
          v
[5. Range Clamping]        ---> Clamps Total UPDRS to [0, 199] and Motor UPDRS to [0, 108]
          |
          v
[6. Trajectory Update]     ---> Trajectory Engine updates the patient's state ledger and
                                recalculates the progression slope: ΔUPDRS / 30 days
          |
          v
[7. D3 Dashboard Display]  ---> Returns JSON in <20 ms with Server-Timing headers to the UI
```

---

## 8. Summary Comparison Table (Cheat Sheet for Your Demo)

| Concept | ElasticNet | Random Forest | Demo Heuristic (Active in UI) |
|---|---|---|---|
| **Underlying Math** | Linear formula with Weights & Bias | 200 branching Decision Trees | Weighted burden formula |
| **Formula Used?** | Yes: $y = \sum w_i x_i + b$ | No: Tree split thresholds | Yes: Calibrated non-linear formula |
| **How It Learns** | Gradient descent / Coordinate descent | Bagging (Bootstrap Aggregation) | Pre-calibrated clinical constants |
| **Feature Scaling** | Requires `StandardScaler` | Does not require scaling | Normalizes bounds internally |
| **Accuracy (MAE)** | $8.41$ UPDRS points | **$7.28$ UPDRS points (Best)** | Deterministic prototype baseline |
| **Inference Time** | $< 2$ ms | $\sim 5$ ms | $< 1$ ms |
| **Primary Advantage** | Highly interpretable weights | Captures complex nonlinear relationships | Instant, zero-setup demo reliability |

---

## 9. Quick Answers to Evaluator Questions Tomorrow

**Q: Did you write the formula yourself or did the model learn it?**
> *"The production Random Forest model learned its branching decisions automatically from the 5,875 recordings in the UCI dataset by minimizing Mean Squared Error. The active UI demo engine uses a pre-calibrated deterministic physiological formula so that the full-stack dashboard can be demonstrated immediately with sub-20ms responsiveness without needing external 50MB model binary files checked into git."*

**Q: Does your model use weights and biases?**
> *"Our ElasticNet linear regression model explicitly learns weights ($w$) for each acoustic feature and a bias ($b$) intercept. However, our top-performing challenger model is a Random Forest Regressor, which uses an ensemble of 200 decision trees rather than linear weights and biases."*

**Q: How do you know the model isn't just memorizing patients?**
> *"We implemented a Grouped-Patient Split where patients in the test partition never appear in the training partition, as well as a Future-Time Split where the model is only tested on future observations from subsequent months to prevent temporal data leakage."*
