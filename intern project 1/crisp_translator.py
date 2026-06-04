"""
CRISP Performance Translator — Command-Center Risk Monitoring Engine
====================================================================
Author: Abdulrahman Hashem | CMH7 Intern Project
Architecture: Severity Scoring + Escalation Logic + Incident Logging

Inspired by NOC/FOC monitoring patterns:
- Threshold-based severity classification (P1-P4)
- Time-based escalation triggers
- Incident auto-logging with driver attribution
- Runbook-style recommended actions

Usage:
    from crisp_translator import SeverityEngine, MockDataGenerator, StatusBoard
    
    # Generate mock data (or plug in real CRISP exports)
    generator = MockDataGenerator()
    data = generator.generate_shift_data()
    
    # Run the monitoring engine
    engine = SeverityEngine()
    results = engine.process_batch(data)
    
    # Render status board
    board = StatusBoard(engine)
    board.render(results)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import IntEnum


# ============================================
# SEVERITY LEVELS
# ============================================

class Severity(IntEnum):
    GREEN = 0   # P4 - Normal
    YELLOW = 1  # P3 - Watch
    ORANGE = 2  # P2 - Warning
    RED = 3     # P1 - Critical


SEVERITY_THRESHOLDS = {
    Severity.GREEN: (0, 85),
    Severity.YELLOW: (85, 95),
    Severity.ORANGE: (95, 100),
    Severity.RED: (100, float('inf'))
}

SEVERITY_LABELS = {
    Severity.GREEN: 'GREEN',
    Severity.YELLOW: 'YELLOW',
    Severity.ORANGE: 'ORANGE',
    Severity.RED: 'RED'
}


# ============================================
# DATA MODELS
# ============================================

@dataclass
class Incident:
    """An incident is any non-GREEN severity event."""
    incident_id: str
    timestamp: datetime
    zone: str
    severity: str
    utilization: float
    drivers: List[str]
    compound_score: int
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class Escalation:
    """Triggered when a zone stays RED beyond threshold."""
    zone: str
    started_at: datetime
    escalated_at: datetime
    duration_minutes: float
    message: str


@dataclass
class ActionCard:
    """Recommended response action for an active alert."""
    zone: str
    severity: str
    urgency: str  # IMMEDIATE or MONITOR
    actions: List[str]


# ============================================
# SEVERITY SCORING ENGINE
# ============================================

class SeverityEngine:
    """
    Core monitoring engine. Applies threshold-based severity scoring,
    compound factor analysis, escalation timers, and incident logging.
    
    Design pattern: mirrors AWS CloudWatch alarm logic —
    threshold breach -> state change -> action trigger -> incident log
    """
    
    # Runbook: maps drivers to recommended actions
    RUNBOOK = {
        'LABOR_GAP': 'Deploy additional headcount or flex labor to zone',
        'DOWNTIME': 'Engage RME for equipment status; reroute volume if possible',
        'RATE_DROP': 'Check for quality issues, system slowdowns, or training gaps',
        'WIP_BUILDUP': 'Clear WIP backlog; consider labor rebalance from adjacent zone',
        'CPT_WINDOW': 'Priority window approaching — escalate if not resolving within 10 min',
        'COMPOUND_UPGRADE': 'Multiple drivers active — investigate root cause immediately'
    }
    
    def __init__(self, escalation_threshold_minutes: int = 15):
        self.escalation_threshold_minutes = escalation_threshold_minutes
        self.incidents: List[Incident] = []
        self.escalations: List[Escalation] = []
        self.escalation_timers: Dict[str, datetime] = {}
        self._incident_counter = 0
    
    def classify_severity(self, utilization_pct: float) -> Severity:
        """Classify utilization into severity level."""
        for level, (low, high) in SEVERITY_THRESHOLDS.items():
            if low <= utilization_pct < high:
                return level
        return Severity.RED
    
    def detect_drivers(self, record: dict) -> Tuple[List[str], int]:
        """
        Analyze compound factors beyond raw utilization.
        Returns (drivers_list, compound_score).
        """
        drivers = []
        score = 0
        
        if record.get('wip_units', 0) > 80:
            drivers.append('WIP_BUILDUP')
            score += 1
        
        if record.get('throughput_rate_uph', 999) < 120:
            drivers.append('RATE_DROP')
            score += 1
        
        if record.get('downtime_minutes', 0) > 0:
            drivers.append('DOWNTIME')
            score += 1
        
        if record.get('labor_headcount', 99) < 10:
            drivers.append('LABOR_GAP')
            score += 1
        
        if record.get('cpt_window', False):
            drivers.append('CPT_WINDOW')
            score += 1
        
        return drivers, score
    
    def score_zone(self, record: dict) -> dict:
        """
        Score a single zone reading. Returns full context:
        base severity, compound factors, final severity, drivers.
        """
        util = record['utilization_pct']
        base_severity = self.classify_severity(util)
        drivers, compound_score = self.detect_drivers(record)
        
        # Compound upgrade logic
        final_severity = base_severity
        if compound_score >= 3 and base_severity <= Severity.YELLOW:
            final_severity = Severity.ORANGE
            drivers.append('COMPOUND_UPGRADE')
        elif compound_score >= 2 and base_severity == Severity.YELLOW:
            final_severity = Severity.ORANGE
            drivers.append('COMPOUND_UPGRADE')
        
        return {
            'zone': record['zone'],
            'timestamp': record['timestamp'],
            'utilization_pct': util,
            'base_severity': SEVERITY_LABELS[base_severity],
            'final_severity': SEVERITY_LABELS[final_severity],
            'priority': int(final_severity),
            'compound_score': compound_score,
            'drivers': drivers
        }
    
    def check_escalation(self, zone: str, severity: str, timestamp: datetime) -> Optional[Escalation]:
        """Track RED duration and trigger escalation if threshold exceeded."""
        if severity == 'RED':
            if zone not in self.escalation_timers:
                self.escalation_timers[zone] = timestamp
                return None
            elapsed = (timestamp - self.escalation_timers[zone]).total_seconds() / 60
            if elapsed >= self.escalation_threshold_minutes:
                esc = Escalation(
                    zone=zone,
                    started_at=self.escalation_timers[zone],
                    escalated_at=timestamp,
                    duration_minutes=round(elapsed, 1),
                    message=f'ESCALATION: {zone} RED for {elapsed:.0f} min. Immediate intervention required.'
                )
                self.escalations.append(esc)
                return esc
        else:
            self.escalation_timers.pop(zone, None)
        return None
    
    def log_incident(self, score_result: dict) -> Optional[Incident]:
        """Log non-GREEN events as incidents."""
        if score_result['final_severity'] != 'GREEN':
            self._incident_counter += 1
            inc = Incident(
                incident_id=f"INC-{self._incident_counter:04d}",
                timestamp=score_result['timestamp'],
                zone=score_result['zone'],
                severity=score_result['final_severity'],
                utilization=score_result['utilization_pct'],
                drivers=score_result['drivers'],
                compound_score=score_result['compound_score']
            )
            self.incidents.append(inc)
            return inc
        return None
    
    def generate_action_card(self, score_result: dict) -> Optional[ActionCard]:
        """Generate runbook-style action recommendation."""
        actions = [
            f"\u2022 {self.RUNBOOK[d]}" 
            for d in score_result['drivers'] 
            if d in self.RUNBOOK
        ]
        if not actions:
            return None
        return ActionCard(
            zone=score_result['zone'],
            severity=score_result['final_severity'],
            urgency='IMMEDIATE' if score_result['final_severity'] == 'RED' else 'MONITOR',
            actions=actions
        )
    
    def process_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process an entire batch of readings through the engine."""
        results = []
        for _, row in df.iterrows():
            score = self.score_zone(row.to_dict())
            self.check_escalation(score['zone'], score['final_severity'], score['timestamp'])
            self.log_incident(score)
            results.append(score)
        return pd.DataFrame(results)
    
    def get_summary(self) -> dict:
        """Return engine state summary."""
        return {
            'total_incidents': len(self.incidents),
            'total_escalations': len(self.escalations),
            'active_escalation_timers': dict(self.escalation_timers),
            'severity_counts': {
                sev: len([i for i in self.incidents if i.severity == sev])
                for sev in ['YELLOW', 'ORANGE', 'RED']
            }
        }


# ============================================
# MOCK DATA GENERATOR
# ============================================

class MockDataGenerator:
    """
    Generates realistic CRISP-like data for development and testing.
    Replace with real data ingestion when access is granted.
    """
    
    ZONES = {
        'PC_Singles': {'base_util': 88, 'volatility': 15, 'risk_weight': 1.0},
        'PC_Multis': {'base_util': 82, 'volatility': 12, 'risk_weight': 0.9},
        'SLAM': {'base_util': 70, 'volatility': 10, 'risk_weight': 0.7},
        'Sorter_Chutes': {'base_util': 65, 'volatility': 8, 'risk_weight': 0.6},
        'Dock_Loadout': {'base_util': 75, 'volatility': 11, 'risk_weight': 0.8}
    }
    
    CPT_HOURS = [5, 11, 13, 16]
    
    def generate_shift_data(self, date=None, interval_minutes=30, shift_start=2, shift_end=18):
        """Generate a full shift of mock data."""
        if date is None:
            date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        base_time = date.replace(hour=shift_start)
        windows = int((shift_end - shift_start) * 60 / interval_minutes) + 1
        time_slots = [base_time + timedelta(minutes=interval_minutes * i) for i in range(windows)]
        
        records = []
        for zone, params in self.ZONES.items():
            for t in time_slots:
                peak_boost = 0
                if t.hour in self.CPT_HOURS:
                    peak_boost = np.random.uniform(8, 20)
                elif t.hour in [h - 1 for h in self.CPT_HOURS]:
                    peak_boost = np.random.uniform(3, 10)
                
                util = params['base_util'] + peak_boost + np.random.normal(0, params['volatility'] * 0.5)
                util = max(20, min(120, util))
                
                records.append({
                    'timestamp': t,
                    'zone': zone,
                    'utilization_pct': round(util, 1),
                    'wip_units': int(np.random.poisson(50) * (util / 80)),
                    'throughput_rate_uph': max(10, int(np.random.normal(150, 20) * (100 / max(util, 50)))),
                    'labor_headcount': int(np.random.normal(12, 2)),
                    'downtime_minutes': int(np.random.exponential(3)) if np.random.random() < 0.15 else 0,
                    'cpt_window': t.hour in self.CPT_HOURS
                })
        
        return pd.DataFrame(records)


# ============================================
# STATUS BOARD RENDERER
# ============================================

class StatusBoard:
    """Terminal-based NOC status board renderer."""
    
    ICONS = {'GREEN': '[OK]', 'YELLOW': '[!!]', 'ORANGE': '[**]', 'RED': '[XX]'}
    
    def __init__(self, engine: SeverityEngine):
        self.engine = engine
    
    def render(self, results_df: pd.DataFrame, at_time=None):
        """Render the status board at a given timestamp."""
        if at_time is None:
            at_time = results_df['timestamp'].max()
        
        latest = results_df[results_df['timestamp'] == at_time]
        
        print(f"\n{'=' * 62}")
        print(f"  CMH7 OUTBOUND — MONITORING STATUS BOARD")
        print(f"  {at_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"{'=' * 62}")
        print(f"\n  {'ZONE':<18} {'UTIL':>6} {'SEVERITY':>8}  DRIVERS")
        print(f"  {'-' * 56}")
        
        for _, row in latest.iterrows():
            icon = self.ICONS[row['final_severity']]
            drivers = ', '.join(row['drivers']) if row['drivers'] else '—'
            print(f"  {icon} {row['zone']:<14} {row['utilization_pct']:>5.1f}%  {row['final_severity']:<8} {drivers}")
        
        print(f"  {'-' * 56}")
        print(f"  Incidents this shift: {len(self.engine.incidents)}")
        print(f"  Escalations triggered: {len(self.engine.escalations)}")
        print(f"{'=' * 62}")


if __name__ == '__main__':
    # Demo run
    gen = MockDataGenerator()
    data = gen.generate_shift_data()
    
    engine = SeverityEngine(escalation_threshold_minutes=15)
    results = engine.process_batch(data)
    
    board = StatusBoard(engine)
    board.render(results, at_time=data['timestamp'].unique()[18])  # ~11:00
    
    print(f"\nEngine Summary: {engine.get_summary()}")
