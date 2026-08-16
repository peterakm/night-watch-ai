# Night Watch AI

A live overnight monitoring dashboard for elderly-care wards — for wards or
care homes where only a handful of staff are doing rounds and nobody can
watch every monitor continuously. The doctor doesn't browse patient data; the
system watches it for them and pushes an alert the moment someone needs a
check, in-app, as a browser push notification, and with a sound.

**What it does:** a rule-based early-warning engine scores each patient's
vitals (heart rate, respiratory rate, SpO2, temperature, blood pressure)
against clinical thresholds and against that patient's own overnight trend.
The dashboard runs a simulated clock through the shift's readings, and the
instant any patient's NEWS2-lite risk band gets worse, an LLM (a free local
model via Ollama by default, or Claude) turns the rule engine's findings into
one short, urgent sentence — not a paragraph the doctor has to stop and read,
since they can already see the raw numbers. A separate CLI mode is also
available for generating a full end-of-shift text summary per patient.

**What it is not:** a diagnostic tool, a certified medical device, or a
substitute for in-person clinical judgment. Every summary is generated from
rule-engine output, not invented by the model, and every "medium"/"high"
result is meant to prompt a human check — not replace one. Do not use this
for real patient care without proper clinical validation, regulatory review
(e.g. FDA/CE as applicable), and integration with real monitoring hardware.

## How it works

```
vitals reading → NEWS2-lite rule engine → risk band per patient, every tick
                        │
                        ▼
              risk band got WORSE than its
              high-water mark this shift?
                        │ yes
                        ▼
           LLM writes one urgent sentence (ollama/qwen2.5:7b, free — or Claude)
                        │
                        ▼
        in-app alert panel + toast + browser push notification + sound
```

1. **`nightwatch/scoring.py`** — a lite adaptation of
   [NEWS2](https://www.rcp.ac.uk/improving-care/resources/national-early-warning-score-news-2/),
   the standard UK clinical early-warning score, applied to whatever vitals a
   passive monitor can supply (it omits the AVPU consciousness check and the
   supplemental-oxygen SpO2 scale, since neither is available from a sensor).
   On top of NEWS2's absolute thresholds, it also flags when a patient has
   drifted more than 2 standard deviations from *their own* baseline for the
   shift — often the earliest sign of overnight deterioration, before any
   single reading crosses an absolute danger threshold.
2. **`nightwatch/data.py`** — loads a real Kaggle vitals dataset (see below)
   to calibrate elderly population baselines, and/or generates a synthetic
   overnight multi-patient dataset (~15% of patients, always at least one,
   given a slow, progressive deterioration curve — everyone else draws from
   a healthy normal distribution, which essentially never crosses NEWS2's
   "high" threshold by chance) so the demo runs without needing the
   real dataset.
3. **`nightwatch/api.py`** — the dashboard's backend. Monitoring is turned
   on/off, not run for a fixed duration: a background clock generates one
   new reading per patient every 5 real seconds (each representing 20
   simulated minutes) for as long as it's on, so vitals arrive progressively
   the way a real monitor would, instead of the whole night being dumped at
   once. Every tick, it
   re-scores every patient and compares against a per-patient *high-water
   mark* risk band — only a band that's genuinely worse than anything seen
   so far fires an alert. That high-water mark only drops back down after 3
   consecutive improved readings, which is deliberate hysteresis: without it,
   a single noisy reading hovering right at a NEWS2 threshold can flip back
   and forth and re-fire the same alert every few seconds (this happened
   during development — same patient, same wording, twice, 10 seconds apart
   — before the fix).
4. **`nightwatch/summarize.py`** — sends the rule engine's structured output
   (never raw, unprocessed vitals alone) to an LLM. Two prompts: a full
   3-5 sentence summary (CLI only) and a one-sentence urgent alert line
   (dashboard) that names the finding driving the escalation and says to
   check the patient now — it doesn't restate numbers the doctor can already
   see on the stat tiles.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt -e .
copy .env.example .env
```

Defaults to a free, local model via [Ollama](https://ollama.com) — no API
key, no cost. Make sure `ollama serve` is running and pull the model once:

```bash
ollama pull qwen2.5:7b
```

## Run the demo (synthetic data, no download needed)

```bash
python -m nightwatch.cli demo --patients 5 --hours 9
```

Generates a synthetic overnight shift (11pm-8am by default) for 5 patients
(~15% deteriorating), scores every patient, prints a summary for each to the
console, and writes a Markdown shift report to `output/`.

## Dashboard (FastAPI + React)

A live browser ward view: a patient list sorted by risk band (highest
first), color-coded risk badges, a stat-tile breakdown of vitals per
patient, plain-language reasoning for the current risk level, a shift clock,
and an **alerts panel** that's the actual point of the app — the doctor
reacts to what shows up there, they don't have to go looking.

Monitoring is **turned on and off**, not run for a fixed duration — there's
no "hours" setting. The moment the doctor clicks **Start monitoring**
becomes the shift's start time, synced to their actual wall clock; readings
then arrive at a fast, compressed demo pace (one new reading every 5 real
seconds, each representing 20 simulated minutes — so you can actually watch
a shift play out instead of waiting hours) for as long as monitoring stays
on. Clicking **Stop monitoring** freezes the clock right there; the ward's
final state, vitals history, and every alert stay in place for review —
nothing is cleared until the next Start.

The alerts panel is split into two columns — **High, go now** and **Medium
& Low-Medium** — so a critical alert is never buried under lower-priority
ones. Each column has its own count badge, color-coded to match. The High
column's badge specifically hides while you're already looking at a
High-risk patient's detail view — you don't need the reminder for the thing
you're currently doing; the Medium/Low-Medium badge keeps showing regardless,
since something less urgent but still worth knowing about could be
happening elsewhere.

Each alert has a two-step lifecycle so the ward's status stays accurate
mid-response, not just before/after:

1. **New** — just fired, nobody's responded yet.
2. **Checking** — a doctor clicked it and is on their way. Lets a second
   person glance at the panel and see "someone's already on this" instead of
   duplicating the trip.
3. **Checked** — the doctor has actually seen the patient in person. The
   alert dims and drops out of the open-alert count.

The risk badge itself is also stabilized against single noisy readings: it
shows a *sustained* risk level (rises immediately, only falls after 3
consecutive improved readings) rather than the raw instantaneous score,
which otherwise can flicker between colors for patients who were never
really in trouble — a random reading brushing a threshold, then back to
normal next reading. This was a real issue caught during development (see
the hysteresis note above) and fixed the same way for both alerts and the
badge.

**Backend** (from the project root, with `.venv` active):

```bash
uvicorn nightwatch.api:app --port 8000
```

**Frontend** (first time only: `cd frontend && npm install`):

```bash
cd frontend
npm run dev
```

Then open <http://localhost:5173>. Click **Start monitoring** to begin —
the clock starts ticking and readings appear progressively, the way a real
monitor would. Click a patient for full vitals/score/trend detail. Click
**Enable desktop alerts** to also get browser push notifications (needs a
one-time permission grant); a chime plays and a toast pops up for every new
alert regardless. The theme selector supports system/light/dark.

The frontend expects the API at `http://localhost:8000` by default; override
with `VITE_API_URL` in `frontend/.env` if you run the backend elsewhere.

**Running this yourself — avoid duplicate backend processes.** This app
keeps its current shift *in memory, per process*. If you restart the backend
without fully stopping the old one first (a new terminal, a `Ctrl+C` that
didn't land, re-running the command), you can end up with two independent
processes both listening — and depending on which one answers a given
request, the dashboard will show wildly inconsistent data (this happened
during development and looked exactly like a data-corruption bug before the
cause was found). Before starting the backend, confirm nothing already owns
port 8000:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
```

If that returns something, stop it (`Stop-Process -Id <OwningProcess> -Force`)
before running `uvicorn` again.

## Using real data

The demo works out of the box with synthetic vitals built from standard
clinical reference ranges. The rule engine's population baselines can also be
calibrated against a real dataset: the CC0-licensed **Human Vital Sign
Dataset** from Kaggle (200,020 rows, ages 18–89, includes heart rate,
respiratory rate, SpO2, temperature, blood pressure, and a labeled risk
category). <https://www.kaggle.com/datasets/nasirayub2/human-vital-sign-dataset>

`data/raw/` and `data/processed/` are gitignored (raw data and derived
baselines don't belong in version control), so on a fresh checkout you'll
need to redo these two steps — download, then calibrate:

```bash
# Requires a Kaggle account + API token saved to ~/.kaggle/kaggle.json
# (kaggle.com -> Settings -> API -> Create New Token)
kaggle datasets download -d nasirayub2/human-vital-sign-dataset -p data/raw --unzip

python -m nightwatch.cli calibrate --csv data/raw/human_vital_signs_dataset_2024.csv
```

`calibrate` filters the dataset to the 69,352 rows aged 65+ and writes
per-vital mean/standard-deviation baselines to
`data/processed/elderly_baselines.json`. `demo` picks this file up
automatically — once it exists, any patient without enough of their own
readings yet for a personal baseline is compared against these real-data
elderly norms instead of the hardcoded clinical-reference defaults in
`data.py`.

Other elderly/vitals-monitoring datasets worth exploring for a production
version: search Kaggle/PhysioNet for ICU or nursing-home-specific vitals —
most require an application or data-use agreement (e.g. MIMIC-IV, eICU) and
were out of scope for this prototype's same-day setup.

## Model choice

Two backends are supported, set via `NIGHTWATCH_PROVIDER` in `.env` or
`--provider` on the CLI:

- **`ollama`** (default) — a locally-run open model via
  [Ollama](https://ollama.com), entirely free, no API key, runs on your own
  machine. Defaults to `qwen2.5:7b`. Requires `ollama serve` running locally
  with the model pulled (`ollama pull qwen2.5:7b`). Noticeably less nuanced
  than Claude for this kind of clinical writing — it occasionally comments
  on a borderline reading the rule engine didn't actually flag (subscore < 2)
  rather than sticking strictly to the given flags. Review its summaries
  more carefully, especially anything it says beyond the listed flags.

- **`anthropic`** — Claude via the Anthropic API. Better clinical-writing
  quality and more disciplined about sticking to the given findings; has a
  small per-call cost. Defaults to `claude-sonnet-5`. Override the model
  with `NIGHTWATCH_MODEL` / `--model`:
  - `claude-haiku-4-5` — cheapest, for very high patient volumes
  - `claude-opus-5` — most careful reasoning, for the highest-stakes deployments

  The system prompt is sent with prompt caching enabled, so running the demo
  across many patients in one shift only pays full price for the first call.

```bash
python -m nightwatch.cli demo               # ollama, free, default
python -m nightwatch.cli demo --provider anthropic --model claude-sonnet-5
```

## Project layout

```
src/nightwatch/
  data.py         # Kaggle loader, population baselines, synthetic generator
  scoring.py      # NEWS2-lite rule engine + personal-trend detection
  summarize.py    # LLM calls (Ollama/Claude): full summary + short alert line
  cli.py          # `demo` and `calibrate` commands
  api.py          # FastAPI backend: simulated clock, escalation detection,
                   # alert generation, in-memory shift state
frontend/         # React + TypeScript dashboard (Vite)
  src/App.tsx              # polling loop, notification diffing, layout
  src/components/
    PatientCard.tsx          # ward-list card
    PatientDetail.tsx        # vitals / NEWS2 breakdown / trend detail
    NotificationPanel.tsx    # the alerts list — the app's main surface
    ShiftClock.tsx           # simulated time + progress bar
    Toast.tsx                # transient pop-up for new alerts
    StatTile.tsx, RiskBadge.tsx
  src/lib/
    api.ts            # typed fetch client for the FastAPI backend
    audio.ts           # synthesized alert chime (Web Audio API)
    pushNotify.ts       # browser Notification API wrapper
data/raw/         # place the downloaded Kaggle CSV here
data/processed/   # calibrated baseline JSON lands here
output/           # generated shift-summary Markdown reports (CLI only)
```
