# ParkTwin Demo Run Guide: Quick & Local

This document provides the exact commands to run ParkTwin locally for your demo. Follow the steps below in order.

---

## 🚀 Fast Local Run (No Docker Needed — Recommended for Demo)

The backend is configured to use a local SQLite database (`parktwin_dev.db`) and the deterministic prototype model adapter out of the box.

### Step 1: Start the Backend Server (Terminal 1)
Open a PowerShell window in the project root (`c:\Users\tanay\Desktop\parktwin-digital-twin`):

```powershell
$env:PYTHONPATH="backend"
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
```
* **Status Check:** You should see `Application startup complete` and `Uvicorn running on http://127.0.0.1:8000`.
* **API Documentation:** Interactive Swagger docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

### Step 2: Seed the Demo Patient Cohorts (Terminal 2)
Open a second PowerShell window in the project root to populate realistic synthetic patients:

```powershell
.\backend\.venv\Scripts\python.exe infra/scripts/seed_demo.py --base-url http://localhost:8000
```

This creates 3 clinical demo patients:
1. `SYN-PT-1001`: Gradual worsening trajectory over 10 weeks.
2. `SYN-PT-2004`: Stable trajectory with mild week-to-week fluctuations.
3. `SYN-PT-3009`: Incomplete baseline testing safety handling (`insufficient_data`).

---

### Step 3: Start the Frontend Dashboard (Terminal 3)
Open a third terminal window in the project root:

```powershell
cd frontend
npm run dev
```

* Open your browser at: **[http://localhost:5173](http://localhost:5173)**
* The dashboard is pre-configured to automatically connect to `http://localhost:8000` using the default clinician key (`dev-clinician-key`).

---

## ⚡ 5-Second Pre-Demo Health & SLA Verification
Before starting your presentation, you can verify that all API contracts, simulation math, and the sub-500ms latency SLA are passing by running:

```powershell
.\backend\.venv\Scripts\python.exe infra/scripts/run_demo.py --in-process
```

Expected output:
```json
{
  "production_history_unchanged": true,
  "meets_500ms_target": true
}
```

---

## 🔄 Fresh Reset (If You Want a Clean Slate During the Demo)
If you submitted test observations or ran simulations and want to reset the database back to clean demo data:

1. Stop the backend server in Terminal 1 (`Ctrl + C`).
2. Delete the local SQLite database file:
   ```powershell
   Remove-Item parktwin_dev.db -ErrorAction SilentlyContinue
   ```
3. Restart the backend (Step 1).
4. Run the seed script again (Step 2).
5. Refresh your browser at [http://localhost:5173](http://localhost:5173).

---

## 🐳 Alternative: Run via Docker Compose (If Docker Desktop is Open)
If you prefer running everything in containers with PostgreSQL:

```bash
# 1. Start containers (Database, API, and Nginx Frontend)
docker compose up --build -d

# 2. Seed data via the API container
docker compose exec api python infra/scripts/seed_demo.py --base-url http://localhost:8000

# 3. Open the dashboard
# Frontend is served at: http://localhost:8080
# Backend is served at:  http://localhost:8000
```

---

## 📋 5-Minute Demo Flow Cheat Sheet

1. **System Health & Safety Disclaimer:**
   * Point out the green **API Ready** badge and the **Research Prototype / Non-Diagnostic** banner at the top.
2. **Cohort Comparison (Left Sidebar):**
   * Click **`SYN-PT-1001`**: Show a worsening trajectory (+5.24 pts/30d slope).
   * Click **`SYN-PT-2004`**: Show a stable patient (+0.03 pts/30d slope).
   * Click **`SYN-PT-3009`**: Point out the safety feature—with only 1 observation, the system refuses to guess a trend and displays `Insufficient data`.
3. **Trajectory & Confidence Intervals:**
   * Click on **`SYN-DEMO-D4039B55`** or **`SYN-PT-1001`**.
   * Explain the chart: solid teal dots are clinical clinic visits, purple dashed diamonds are voice-estimated UPDRS points, and the shaded purple envelope is the 95% Confidence Interval.
4. **Live Voice Ingestion:**
   * Scroll down to **Submit Voice Observation**.
   * Click **"Autofill Synthetic Sample"** (loads 16 acoustic features: Jitter, Shimmer, NHR, HNR).
   * Click **"Submit Observation"**.
   * Highlight the instant recalculation of the trajectory curve and slope.
5. **What-If Scenario Simulation:**
   * In the **Simulation Panel**, adjust:
     * *Levodopa Dose Change:* `+150 mg`
     * *Physical Therapy:* `3 sessions / week`
     * *Adherence:* `90%`
   * Check **"I acknowledge simulation results are hypothetical"**.
   * Click **"Run Simulation"**.
   * Point out the green dashed counterfactual line showing projected disease stabilization against the worsening baseline.
6. **Acoustic Biomarkers & Governance Tabs:**
   * Switch to **Voice Biomarkers & Ledger** to inspect baseline-to-latest deltas.
   * Switch to **Governance, Export & Audit** and click **Export CSV** to show clinical research export.
