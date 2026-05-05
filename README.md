# PhishGuard — ML-Based Phishing Email Detection System

> **97.62% accuracy · ROC-AUC 0.9972 · F1 Score 0.9778**  
> A full-stack phishing detection system powered by a soft-voting ML ensemble, served through a Flask REST API and integrated directly into Gmail via a Chrome extension.

---

## Table of Contents

- [Overview](#overview)
- [Demo](#demo)
- [Features](#features)
- [Architecture](#architecture)
- [Dataset](#dataset)
- [Model](#model)
- [Performance](#performance)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Running the API](#running-the-api)
  - [Loading the Chrome Extension](#loading-the-chrome-extension)
  - [Using the Web Dashboard](#using-the-web-dashboard)
- [API Reference](#api-reference)
- [Security Considerations](#security-considerations)
- [Limitations & Future Work](#limitations--future-work)
- [Team](#team)
- [References](#references)

---

## Overview

Phishing emails remain the most common entry point for malware, ransomware, and cyberattacks. Rule-based filters and blocklists are easily evaded by attackers who constantly adapt their language and tactics. PhishGuard takes a different approach: instead of matching keywords, it learns the deep structural and linguistic patterns that distinguish phishing emails from legitimate ones.

The system was trained on **70,986 real-world emails** (53% phishing, 47% legitimate) and combines three complementary classifiers into a single ensemble that consistently outperforms each individual model.

---

## Demo

### Chrome Extension (Gmail)
1. Open any email in Gmail.
2. Click the **PhishGuard** icon in the Chrome toolbar.
3. Hit **Analyze Current Email**.
4. The popup instantly shows the verdict, phishing probability, and risk level.

### Web Dashboard
Navigate to `http://127.0.0.1:5004` while the API is running. Paste any email subject and body, configure URL and IP-URL flags manually, and get a full threat breakdown with a visual meter and recommended action.

### cURL
```bash
curl -X POST http://127.0.0.1:5004/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "URGENT verify your account",
    "body": "Click here to confirm your password or your account will be suspended",
    "url_count": 3,
    "has_ip_url": 1,
    "html_flag": 0
  }'
```

---

## Features

**Machine Learning**
- Soft-voting ensemble: Random Forest + Gradient Boosting + Logistic Regression
- 8,000+ dimensional feature space combining TF-IDF text vectors and 20+ handcrafted structural features
- Decision threshold tuned to 0.60 to minimize false negatives (missed phishing)

**Handcrafted Features (examples)**
- `body_urgent_words` — hits on pressure tokens: *urgent, verify, suspend, click, password, free, winner*
- `display_name_mismatch` — catches brand impersonation (display name says "PayPal" but sending domain doesn't match)
- `lookalike_domain` — detects typosquatting using edit-distance comparison against known brands
- `ip_url_ratio` — fraction of URLs using raw IP addresses instead of domain names
- `replyto_mismatch` — flags Business Email Compromise (BEC) patterns

**Deployment**
- Flask REST API on port 5004
- Chrome Extension (Manifest V3) with Gmail DOM integration
- Standalone web dashboard for manual analysis and `.eml` file uploads

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                             │
│                                                                 │
│   ┌────────────────────┐       ┌──────────────────────────┐    │
│   │  Chrome Extension  │       │      Web Dashboard       │    │
│   │  (Manifest V3)     │       │  (HTML + CSS + Vanilla   │    │
│   │                    │       │        JS)               │    │
│   │  content.js        │       │  http://127.0.0.1:5004   │    │
│   │  (Gmail DOM scraper│       │                          │    │
│   │  → popup.js)       │       │                          │    │
│   └─────────┬──────────┘       └────────────┬─────────────┘    │
│             │  HTTP POST /analyze            │ HTTP POST        │
└─────────────┼────────────────────────────────┼─────────────────┘
              │                                │
┌─────────────▼────────────────────────────────▼─────────────────┐
│                      FLASK REST API (port 5004)                 │
│                                                                 │
│   GET  /              → Serves web dashboard                    │
│   POST /analyze       → JSON email fields → prediction          │
│   POST /predict_eml   → Raw .eml file → prediction             │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────┐
│                     ML PIPELINE (.pkl)                          │
│                                                                 │
│  engineer_features()                                            │
│       ↓                                                         │
│  ColumnTransformer                                              │
│  ├── TF-IDF (5,000 dims)  → text_combined column               │
│  ├── SimpleImputer (median) → numeric features                  │
│  └── StandardScaler        → normalized numerics               │
│       ↓                                                         │
│  VotingClassifier (soft, weighted)                              │
│  ├── Random Forest      (weight: 3)                             │
│  ├── Gradient Boosting  (weight: 2)                             │
│  └── Logistic Regression (weight: 1)                            │
│       ↓                                                         │
│  Threshold (0.60) → label: phishing / legitimate                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Dataset

The model was trained on a curated collection of real-world phishing and legitimate emails sourced from public phishing corpora and legitimate email archives.

| Property | Value |
|---|---|
| Total emails | 70,986 |
| Phishing | 37,383 (52.7%) |
| Legitimate | 33,603 (47.3%) |
| Class balance | Near-balanced — no resampling needed |
| Input features | 10 columns + 1 binary label |

**Download the dataset (Google Drive):**  
 The raw dataset is available in a google drive and this is the link : https://drive.google.com/file/d/16RtANqgI4E9dV22oBTQgq9mt_jGvsH2p/view?usp=sharing
Place the downloaded file at `data/final_dataset2.csv` before running the notebook.

---

## Model

The final classifier is a **soft-voting ensemble** of three scikit-learn models. All preprocessing and inference live inside a single `Pipeline` object serialized to `phishing_model.pkl`.

| Model | Weight | Standalone Accuracy | Notes |
|---|---|---|---|
| Random Forest (200 trees, depth 20) | 3 | ~96.5% | Best individual model; handles non-linear interactions |
| Gradient Boosting (lr=0.10, depth 5) | 2 | ~95.8% | Catches subtler patterns the RF misses |
| Logistic Regression (saga solver) | 1 | ~93.0% | Efficient on sparse TF-IDF matrices; adds robustness |
| **Soft Voting Ensemble** | — | **97.62%** | Consistently beats all three individual models |

The decision threshold is set to **0.60** (instead of the default 0.50). This raises the bar for calling an email "legitimate", reducing false negatives by ~15% with only a marginal increase in false positives — a deliberate trade-off for a security-critical application.

---

## Performance

Evaluated on a held-out test set of **14,198 emails** (stratified 80/20 split):

| Metric | Score |
|---|---|
| Accuracy | **97.62%** |
| Precision | 97.8% |
| Recall | 97.9% |
| F1 Score | **0.9778** |
| ROC-AUC | **0.9972** |

**Confusion matrix (approximate):**

| | Predicted: Legitimate | Predicted: Phishing |
|---|---|---|
| **Actual: Legitimate** | True Negative ~98% | False Positive ~2% |
| **Actual: Phishing** | False Negative ~2% | True Positive ~98% |

A ROC-AUC of 0.9972 means: given one random phishing email and one random legitimate email, the model assigns a higher phishing probability to the phishing one **99.72% of the time**.

---

## Project Structure

```
phishing-detector/
│
├── data/
│   └── final_dataset2.csv          # Dataset (download from Google Drive link above)
│
├── notebooks/
│   └── phishing_detector_final.ipynb  # End-to-end pipeline: EDA → training → export
│
├── src/
│   ├── api/
│   │   ├── app.py                  # Flask app — route handlers for /analyze and /predict_eml
│   │   ├── eml_parser.py           # Parses raw .eml files into model-ready fields
│   │   ├── phishing_model.pkl      # Serialized scikit-learn pipeline (generated by notebook)
│   │   ├── threshold.pkl           # Saved decision threshold (0.60)
│   │   ├── requirements.txt        # Python dependencies
│   │   ├── templates/              # Jinja2 HTML templates for the web dashboard
│   │   └── static/                 # CSS, JS, and icon assets for the web dashboard
│   │
│   └── extension/
│       ├── manifest.json           # Chrome Manifest V3: permissions, host rules, content script
│       ├── content.js              # Gmail DOM scraper — extracts email fields from the open tab
│       ├── popup.html              # Extension popup markup
│       └── popup.js               # Popup logic: extract → POST to API → render verdict
│
├── plots/
│   ├── eda_plots.png               # Class distribution, median char count, mean URL count
│   ├── evaluation_plots.png        # Confusion matrix and ROC curve
│   └── feature_importance.png      # Top-20 Random Forest feature importances
│
├── README.md
└── requirements.txt
```

---

## Getting Started

### Prerequisites

- Python 3.8 or higher
- `pip` available from the command line
- Google Chrome browser

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/phishing-detector.git
cd phishing-detector

# 2. Install Python dependencies
pip install -r src/api/requirements.txt

# 3. (Optional) Retrain the model — skip if phishing_model.pkl is already present
#    Download the dataset from Google Drive and place it at data/final_dataset2.csv
#    Then open and run: notebooks/phishing_detector_final.ipynb
```

### Running the API

```bash
cd src/api
python app.py
```

You should see:
```
Running on http://127.0.0.1:5004
```

Keep this terminal open. Closing it stops the API and breaks the Chrome extension.

### Loading the Chrome Extension

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer Mode** (toggle in the top-right corner)
3. Click **Load unpacked** and select the `src/extension/` folder
4. Click the puzzle-piece icon in the Chrome toolbar and **pin PhishGuard**
5. Go to [https://mail.google.com](https://mail.google.com) and **open an email fully** (not just a preview)
6. Click the PhishGuard icon → **Analyze Current Email**

The popup will display the verdict, phishing probability, confidence score, and risk level.

### Using the Web Dashboard

Navigate to [http://127.0.0.1:5004](http://127.0.0.1:5004) while the API is running.

The dashboard lets you enter an email subject and body manually, configure URL count and IP-URL flags, and run a full scan. Results include a visual threat meter, a signal breakdown, and a recommended action. You can also upload a raw `.eml` file directly.

---

## API Reference

### `POST /analyze`

Analyze a structured email payload.

**Request body (JSON):**

```json
{
  "subject": "URGENT verify your account",
  "body": "Click here to confirm your password or your account will be suspended",
  "from_email": "security@paypa1.com",
  "url_count": 3,
  "has_ip_url": 1,
  "html_flag": 0
}
```

**Response:**

```json
{
  "prediction": {
    "label": "phishing",
    "phishing_probability": 0.94,
    "confidence": 0.44,
    "risk_level": "high",
    "threshold": 0.60
  }
}
```

| Field | Type | Description |
|---|---|---|
| `label` | string | `"phishing"` or `"legitimate"` |
| `phishing_probability` | float [0,1] | Calibrated ensemble probability |
| `confidence` | float [0,1] | Distance from 0.50 — how certain the model is |
| `risk_level` | string | `"low"` (< 0.30) · `"medium"` (0.30–0.59) · `"high"` (≥ 0.60) |
| `threshold` | float | The threshold applied — 0.60 by default |

### `POST /predict_eml`

Upload a raw `.eml` file. The server extracts all fields automatically and returns the same prediction object plus the extracted fields.

### `GET /`

Serves the web dashboard.

---

## Security Considerations

| Area | Note |
|---|---|
| `phishing_model.pkl` | Uses Python's `pickle` format — **never load from untrusted sources**, as it can execute arbitrary code |
| `threshold.pkl` | Access-control this file; lowering the threshold could let phishing emails through |
| Flask server | Should be placed behind Gunicorn/uWSGI and served over HTTPS for any production use |
| CORS | The extension whitelists `localhost:5004`; all other origins should be blocked |
| Client-supplied fields | `url_count` and `has_ip_url` should be validated server-side — don't trust client values |
| Rate limiting | The API has no rate limit by default; add one before any public deployment |
| Extension permissions | `activeTab` + scripting are required; users should be informed before installation |
| Adversarial inputs | A sophisticated attacker with knowledge of the feature set could craft evasive emails; periodic retraining on fresh samples is the best countermeasure |

---

## Limitations & Future Work

**Current limitations:**
- The model was trained on historical data. Phishing tactics evolve, so performance will degrade over time without retraining.
- The Gmail extension scrapes the DOM, which may break if Gmail changes its HTML structure.

**Planned improvements:**
- Cloud deployment so the extension works team-wide without each member running a local server
- Active learning loop: route low-confidence predictions to human review and fold feedback into future training runs
- Email authentication signals — DMARC, SPF, and DKIM header parsing to complement content-based features
- Multilingual support via a multilingual TF-IDF vocabulary or transformer-based embeddings
- Integration with live threat feeds (PhishTank, OpenPhish) for real-time domain reputation checks
- Mobile companion app extending protection beyond the desktop Chrome browser

---

## Team

| Name | Role |
|---|---|
| **Zemmal Kounouz** | Team Leader |
| Khoumari Aya | Member |
| Chaabnia Enzo | Member |
| Traia Chaima | Member |
| Bouguezzana Malak | Member |

*Computer and Network Security Project — May 2026*

---

## References

- Breiman, L. (2001). *Random Forests.* Machine Learning, 45(1), 5–32.
- Friedman, J. H. (2001). *Greedy function approximation: A gradient boosting machine.* Annals of Statistics, 29(5), 1189–1232.
- Pedregosa, F. et al. (2011). *Scikit-learn: Machine Learning in Python.* JMLR, 12, 2825–2830.
- APWG Phishing Activity Trends Reports (2023–2024). https://apwg.org/trendsreports/
- Fette, I., Sadeh, N., & Tomasic, A. (2007). *Learning to detect phishing emails.* WWW '07.
- Basnet, R., Mukkamala, S., & Sung, A. H. (2008). *Detection of phishing attacks: A machine learning approach.* Studies in Computational Intelligence, 56, 373–383.
- [Chrome Extensions — Manifest V3](https://developer.chrome.com/docs/extensions/mv3/)
- [Flask Documentation v3.0](https://flask.palletsprojects.com/)
