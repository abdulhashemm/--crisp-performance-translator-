[README.md](https://github.com/user-attachments/files/28606690/README.md)
# CRISP Performance Translator
## Command-Center Risk Monitoring for CMH7 Outbound

**Author:** Abdulrahman Hashem | CMH7 Intern Project (Summer 2026)

---

## What Is This?

A Python-based monitoring system that sits on top of CRISP data and adds:
- **Severity scoring** (GREEN/YELLOW/ORANGE/RED) based on utilization thresholds
- **Escalation logic** (auto-escalates if a zone stays RED >15 min)
- **Incident logging** (every breach gets an ID, timestamp, zone, drivers)
- **Action cards** (runbook-style recommendations per alert)
- **Shift handoff reports** (structured end-of-shift summary)
- **Web dashboard** (dark NOC-style Streamlit UI)

Framed as infrastructure-style operational reliability tooling — the same patterns used in AWS FOC, NOC, and Data Center operations.

---

## Quick Start

### 1. Install dependencies
```bash
pip install pandas numpy streamlit openpyxl
```

### 2. Run the dashboard
```bash
streamlit run dashboard.py
```
Opens at `http://localhost:8501` with live mock data.

### 3. Run with real data
```python
from data_connector import CRISPConnector, run_pipeline

# One-liner: file -> scored results
results, engine = run_pipeline('your_crisp_export.csv')

# Generate shift report
from shift_report import ShiftReport
report = ShiftReport(engine, results)
report.generate()                    # Print to console
report.export_markdown('handoff.md') # Save as Markdown
report.export_html('handoff.html')   # Save as styled HTML
```

---

## Project Structure

```
crisp-performance-translator/
├── README.md                  # This file
├── requirements.txt           # Python dependencies
├── crisp_translator.py        # Core engine (severity, escalation, incidents)
├── data_connector.py          # Data ingestion (CSV/Excel/JSON -> normalized)
├── dashboard.py               # Streamlit web dashboard (NOC-style)
├── shift_report.py            # End-of-shift handoff report generator
├── sample_crisp_export.csv    # Sample data for testing
└── docs/
    └── proposal.pptx          # Project proposal presentation
```

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  DATA SOURCES   │     │  SCORING ENGINE  │     │    OUTPUTS      │
│                 │     │                  │     │                 │
│ CRISP exports   │────>│ Severity scoring │────>│ Dashboard (web) │
│ REDO signals    │     │ Escalation logic │     │ Shift reports   │
│ Station data    │     │ Incident logging │     │ Alert cards     │
│ Labor/downtime  │     │ Action cards     │     │ Incident log    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
     (data_connector.py)    (crisp_translator.py)   (dashboard.py / shift_report.py)
```

---

## Module Reference

### `crisp_translator.py` — Core Engine
- `SeverityEngine` — main class
  - `.classify_severity(util)` — threshold classification
  - `.detect_drivers(record)` — compound factor analysis
  - `.score_zone(record)` — full zone scoring
  - `.check_escalation(zone, severity, timestamp)` — escalation timers
  - `.log_incident(score_result)` — auto-logging
  - `.generate_action_card(score_result)` — runbook actions
  - `.process_batch(df)` — batch processing
- `MockDataGenerator` — realistic test data
- `StatusBoard` — terminal NOC display

### `data_connector.py` — Data Ingestion
- `CRISPConnector` — main class
  - `.load(path)` — auto-detect and load any format
  - `.load_csv()`, `.load_excel()`, `.load_json()`, `.load_clipboard()`
  - `.normalize(df)` — clean and standardize for engine
  - `.detect_columns(df)` — debug column mapping
  - `.create_sample_csv()` — generate test data
- `run_pipeline(file_path)` — one-liner end-to-end

### `dashboard.py` — Web UI
- Dark NOC-style theme
- Zone status cards (severity-colored)
- Active alert banners with runbook actions
- Escalation countdown timers
- Incident log (last 50 events)
- Top-level severity counters

### `shift_report.py` — Handoff Reports
- `ShiftReport(engine, results_df)` — main class
  - `.generate()` — console output
  - `.export_markdown(path)` — Markdown file
  - `.export_html(path)` — styled HTML report

---

## Severity Levels

| Level  | Utilization | Priority | Action |
|--------|-------------|----------|--------|
| GREEN  | < 85%       | P4       | Normal operations |
| YELLOW | 85 - 95%    | P3       | Watch — monitor closely |
| ORANGE | 95 - 100%   | P2       | Warning — prepare intervention |
| RED    | > 100%      | P1       | Critical — immediate action |

Severity can be **upgraded** by compound factors (WIP buildup + labor gap + CPT window = auto-upgrade).

---

## Resume Framing

> "Built a command-center style monitoring system for outbound operations using severity-based alerting, escalation logic, incident tracking, and automated shift handoff reports — applying the same patterns used in AWS Infrastructure, FOC, and NOC environments."

---

## Next Steps
- [ ] Get real CRISP data access (confirm export format)
- [ ] Pilot with PC_Singles or PC_Multis
- [ ] Validate outputs with PA/AM on the floor
- [ ] Add historical trend analytics
- [ ] Deploy on AWS (S3 + Lambda + QuickSight)
- [ ] Present to leadership

---

*CRISP Performance Translator v0.1 | CMH7 Outbound | Summer 2026*
