"""
CRISP Performance Translator - Command-Center Dashboard
========================================================
Run with: streamlit run dashboard.py

A NOC-style monitoring dashboard for CMH7 outbound operations.
Displays real-time zone severity, escalation timers, incident log,
and action cards.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time

# ============================================
# PAGE CONFIG
# ============================================
st.set_page_config(
    page_title="CMH7 Outbound Monitor",
    page_icon="\U0001F5A5",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================
# CUSTOM CSS - Dark NOC-style theme
# ============================================
st.markdown("""
<style>
    .stApp {
        background-color: #0D1B2A;
        color: #E0E0E0;
    }
    .header-bar {
        background: linear-gradient(90deg, #1A1A2E 0%, #16213E 100%);
        padding: 12px 24px;
        border-radius: 8px;
        border-bottom: 3px solid #FF6B35;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .header-title {
        font-size: 22px;
        font-weight: 700;
        color: #FFFFFF;
        letter-spacing: 1px;
    }
    .header-live {
        color: #00C853;
        font-size: 14px;
        font-weight: 600;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    .zone-card {
        background: #1B2838;
        border-radius: 10px;
        padding: 16px;
        margin: 6px 0;
        border-left: 4px solid;
        transition: all 0.3s ease;
    }
    .zone-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .zone-card.green { border-left-color: #00C853; }
    .zone-card.yellow { border-left-color: #FFD600; }
    .zone-card.orange { border-left-color: #FF6B35; }
    .zone-card.red { border-left-color: #FF1744; background: #2A1520; }
    .zone-name {
        font-size: 14px;
        font-weight: 600;
        color: #FFFFFF;
        margin-bottom: 4px;
    }
    .zone-util {
        font-size: 28px;
        font-weight: 700;
        margin: 4px 0;
    }
    .zone-util.green { color: #00C853; }
    .zone-util.yellow { color: #FFD600; }
    .zone-util.orange { color: #FF6B35; }
    .zone-util.red { color: #FF1744; }
    .zone-severity {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 1px;
        padding: 2px 8px;
        border-radius: 4px;
        display: inline-block;
    }
    .zone-severity.green { background: rgba(0,200,83,0.15); color: #00C853; }
    .zone-severity.yellow { background: rgba(255,214,0,0.15); color: #FFD600; }
    .zone-severity.orange { background: rgba(255,107,53,0.15); color: #FF6B35; }
    .zone-severity.red { background: rgba(255,23,68,0.15); color: #FF1744; }
    .alert-banner {
        background: linear-gradient(90deg, #2A1520 0%, #1B2838 100%);
        border: 1px solid #FF1744;
        border-radius: 8px;
        padding: 14px 20px;
        margin: 8px 0;
    }
    .alert-title {
        color: #FF1744;
        font-weight: 700;
        font-size: 13px;
        margin-bottom: 6px;
    }
    .alert-action {
        color: #AAAAAA;
        font-size: 12px;
        margin: 3px 0;
    }
    .incident-row {
        background: #1B2838;
        border-radius: 6px;
        padding: 8px 14px;
        margin: 4px 0;
        font-size: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .incident-id { color: #00BFA5; font-weight: 600; }
    .incident-zone { color: #FFFFFF; }
    .metric-card {
        background: #1B2838;
        border-radius: 8px;
        padding: 14px;
        text-align: center;
    }
    .metric-value {
        font-size: 24px;
        font-weight: 700;
        color: #FFFFFF;
    }
    .metric-label {
        font-size: 11px;
        color: #888888;
        letter-spacing: 0.5px;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}
</style>
""", unsafe_allow_html=True)


# ============================================
# ENGINE LOGIC (inline for single-file demo)
# ============================================

SEVERITY_THRESHOLDS = {
    'GREEN': (0, 85),
    'YELLOW': (85, 95),
    'ORANGE': (95, 100),
    'RED': (100, float('inf'))
}

RUNBOOK = {
    'LABOR_GAP': 'Deploy additional headcount or flex labor to zone',
    'DOWNTIME': 'Engage RME for equipment status; reroute if possible',
    'RATE_DROP': 'Check for quality issues, system slowdowns, or training gaps',
    'WIP_BUILDUP': 'Clear WIP backlog; consider labor rebalance from adjacent zone',
    'CPT_WINDOW': 'Priority window approaching - escalate if not resolving',
    'COMPOUND_UPGRADE': 'Multiple drivers active - investigate root cause immediately'
}

ZONES = {
    'PC_Singles': {'base_util': 88, 'volatility': 15},
    'PC_Multis': {'base_util': 82, 'volatility': 12},
    'SLAM': {'base_util': 70, 'volatility': 10},
    'Sorter_Chutes': {'base_util': 65, 'volatility': 8},
    'Dock_Loadout': {'base_util': 75, 'volatility': 11}
}

CPT_HOURS = [5, 11, 13, 16]


def classify_severity(util):
    for level, (low, high) in SEVERITY_THRESHOLDS.items():
        if low <= util < high:
            return level
    return 'RED'


def generate_current_reading():
    """Generate a single time-slice of data (simulates live refresh)."""
    now = datetime.now()
    hour = now.hour if 2 <= now.hour <= 18 else 11

    records = []
    for zone, params in ZONES.items():
        peak_boost = 0
        if hour in CPT_HOURS:
            peak_boost = np.random.uniform(8, 20)
        elif hour in [h - 1 for h in CPT_HOURS]:
            peak_boost = np.random.uniform(3, 10)

        util = params['base_util'] + peak_boost + np.random.normal(0, params['volatility'] * 0.5)
        util = max(20, min(120, util))

        drivers = []
        wip = int(np.random.poisson(50) * (util / 80))
        tput = max(10, int(np.random.normal(150, 20) * (100 / max(util, 50))))
        labor = int(np.random.normal(12, 2))
        downtime = int(np.random.exponential(3)) if np.random.random() < 0.15 else 0

        if wip > 80: drivers.append('WIP_BUILDUP')
        if tput < 120: drivers.append('RATE_DROP')
        if downtime > 0: drivers.append('DOWNTIME')
        if labor < 10: drivers.append('LABOR_GAP')
        if hour in CPT_HOURS: drivers.append('CPT_WINDOW')

        base_sev = classify_severity(util)
        final_sev = base_sev
        compound = len(drivers)
        if compound >= 3 and base_sev in ('GREEN', 'YELLOW'):
            final_sev = 'ORANGE'
            drivers.append('COMPOUND_UPGRADE')
        elif compound >= 2 and base_sev == 'YELLOW':
            final_sev = 'ORANGE'
            drivers.append('COMPOUND_UPGRADE')

        records.append({
            'zone': zone,
            'utilization_pct': round(util, 1),
            'severity': final_sev,
            'wip_units': wip,
            'throughput_rate': tput,
            'labor_headcount': labor,
            'downtime_min': downtime,
            'drivers': drivers,
            'compound_score': compound
        })

    return pd.DataFrame(records)


# ============================================
# SESSION STATE
# ============================================
if 'incidents' not in st.session_state:
    st.session_state.incidents = []
if 'escalation_start' not in st.session_state:
    st.session_state.escalation_start = {}
if 'refresh_count' not in st.session_state:
    st.session_state.refresh_count = 0


# ============================================
# RENDER DASHBOARD
# ============================================

# Header
st.markdown("""
<div class="header-bar">
    <div>
        <span class="header-title">CMH7 OUTBOUND - COMMAND CENTER</span>
    </div>
    <div class="header-live">&#9679; LIVE</div>
</div>
""", unsafe_allow_html=True)

# Generate current data
data = generate_current_reading()
st.session_state.refresh_count += 1

# Log incidents
for _, row in data.iterrows():
    if row['severity'] in ('ORANGE', 'RED'):
        st.session_state.incidents.append({
            'id': f"INC-{len(st.session_state.incidents)+1:04d}",
            'time': datetime.now().strftime('%H:%M:%S'),
            'zone': row['zone'],
            'severity': row['severity'],
            'util': row['utilization_pct'],
            'drivers': row['drivers']
        })
        if row['severity'] == 'RED' and row['zone'] not in st.session_state.escalation_start:
            st.session_state.escalation_start[row['zone']] = time.time()
    else:
        st.session_state.escalation_start.pop(row['zone'], None)

st.session_state.incidents = st.session_state.incidents[-50:]

# --- Top metrics row ---
col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)

red_count = len(data[data['severity'] == 'RED'])
orange_count = len(data[data['severity'] == 'ORANGE'])
yellow_count = len(data[data['severity'] == 'YELLOW'])
green_count = len(data[data['severity'] == 'GREEN'])

with col_m1:
    st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#FF1744">{red_count}</div><div class="metric-label">RED ZONES</div></div>', unsafe_allow_html=True)
with col_m2:
    st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#FF6B35">{orange_count}</div><div class="metric-label">ORANGE ZONES</div></div>', unsafe_allow_html=True)
with col_m3:
    st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#FFD600">{yellow_count}</div><div class="metric-label">YELLOW ZONES</div></div>', unsafe_allow_html=True)
with col_m4:
    st.markdown(f'<div class="metric-card"><div class="metric-value" style="color:#00C853">{green_count}</div><div class="metric-label">GREEN ZONES</div></div>', unsafe_allow_html=True)
with col_m5:
    st.markdown(f'<div class="metric-card"><div class="metric-value">{len(st.session_state.incidents)}</div><div class="metric-label">INCIDENTS</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Main layout: zones + alerts ---
col_zones, col_alerts = st.columns([3, 2])

with col_zones:
    st.markdown("### Zone Status")

    priority_map = {'RED': 0, 'ORANGE': 1, 'YELLOW': 2, 'GREEN': 3}
    data_sorted = data.copy()
    data_sorted['priority'] = data_sorted['severity'].map(priority_map)
    data_sorted = data_sorted.sort_values('priority')

    for _, row in data_sorted.iterrows():
        sev_class = row['severity'].lower()
        drivers_str = ', '.join([d.replace('_', ' ').title() for d in row['drivers']]) if row['drivers'] else 'Normal operations'

        st.markdown(f"""
        <div class="zone-card {sev_class}">
            <div class="zone-name">{row['zone'].replace('_', ' ')}</div>
            <div class="zone-util {sev_class}">{row['utilization_pct']:.1f}%</div>
            <span class="zone-severity {sev_class}">{row['severity']}</span>
            <div style="color:#888; font-size:11px; margin-top:6px;">{drivers_str}</div>
        </div>
        """, unsafe_allow_html=True)

with col_alerts:
    st.markdown("### Active Alerts & Actions")

    alerts = data[data['severity'].isin(['ORANGE', 'RED'])]

    if len(alerts) == 0:
        st.markdown("""
        <div style="background:#1B2838; border-radius:8px; padding:24px; text-align:center; margin-top:10px;">
            <div style="font-size:32px; margin-bottom:8px;">&#9989;</div>
            <div style="color:#00C853; font-weight:600;">All Zones Nominal</div>
            <div style="color:#888; font-size:12px;">No active alerts</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        for _, alert in alerts.iterrows():
            urgency_label = "IMMEDIATE" if alert['severity'] == 'RED' else "MONITOR"
            urgency_icon = "&#128680;" if alert['severity'] == 'RED' else "&#9889;"
            actions_html = ""
            for d in alert['drivers']:
                if d in RUNBOOK:
                    actions_html += f'<div class="alert-action">&#8226; {RUNBOOK[d]}</div>'

            timer_html = ""
            if alert['zone'] in st.session_state.escalation_start:
                elapsed = (time.time() - st.session_state.escalation_start[alert['zone']]) / 60
                remaining = max(0, 15 - elapsed)
                if remaining > 0:
                    timer_html = f'<div style="color:#FF6B35; font-size:11px; margin-top:6px;">&#9201; Escalates in {remaining:.0f} min</div>'
                else:
                    timer_html = f'<div style="color:#FF1744; font-size:11px; margin-top:6px; font-weight:600;">&#9888; ESCALATED ({elapsed:.0f} min RED)</div>'

            st.markdown(f"""
            <div class="alert-banner">
                <div class="alert-title">{urgency_icon} {urgency_label} - {alert['zone'].replace('_', ' ')} ({alert['utilization_pct']:.1f}%)</div>
                {actions_html}
                {timer_html}
            </div>
            """, unsafe_allow_html=True)

    # Incident log
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Recent Incidents")

    recent = st.session_state.incidents[-8:][::-1]
    if recent:
        for inc in recent:
            sev_color = {'RED': '#FF1744', 'ORANGE': '#FF6B35', 'YELLOW': '#FFD600'}.get(inc['severity'], '#888')
            st.markdown(f"""
            <div class="incident-row">
                <span class="incident-id">{inc['id']}</span>
                <span class="incident-zone">{inc['zone']}</span>
                <span style="color:{sev_color}; font-weight:600;">{inc['severity']}</span>
                <span style="color:#888; font-size:11px;">{inc['time']}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#888; font-size:12px; text-align:center;">No incidents yet</div>', unsafe_allow_html=True)

# Footer
st.markdown(f"""
<div style="text-align:center; color:#555; font-size:11px; padding:20px 10px 10px;">
    CRISP Performance Translator v0.1 | CMH7 Outbound | Refresh #{st.session_state.refresh_count} |
    Built by Abdulrahman Hashem
</div>
""", unsafe_allow_html=True)
