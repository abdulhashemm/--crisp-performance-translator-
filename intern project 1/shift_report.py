"""
CRISP Performance Translator - Shift Handoff Report Generator
==============================================================
Author: Abdulrahman Hashem | CMH7 Intern Project

Generates a structured shift handoff report at end of shift.
Designed to mirror infrastructure incident handoff patterns:
- Executive summary (shift health score)
- Active/unresolved incidents carried over
- Escalation history
- Zone performance breakdown
- Recommended actions for incoming shift
- Trend flags (repeat offenders)

Usage:
    from shift_report import ShiftReport
    from crisp_translator import SeverityEngine
    
    engine = SeverityEngine()
    results = engine.process_batch(data)
    
    report = ShiftReport(engine, results)
    report.generate()           # Print to console
    report.export_markdown()    # Save as .md file
    report.export_html()        # Save as styled HTML
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from collections import Counter
import os


# ============================================
# SHIFT REPORT GENERATOR
# ============================================

class ShiftReport:
    """
    Generates end-of-shift handoff reports.
    
    Modeled after NOC/FOC shift handoff procedures:
    - What happened this shift
    - What's still active/unresolved
    - What the next shift should watch for
    - Trend patterns across shifts
    """
    
    SHIFT_NAMES = {
        'DAY': ('Day Shift', '06:00', '18:00'),
        'NIGHT': ('Night Shift', '18:00', '06:00'),
        'FRONT_HALF': ('Front Half', '06:00', '16:30'),
        'BACK_HALF': ('Back Half', '16:30', '06:00'),
    }
    
    def __init__(self, engine, results_df: pd.DataFrame, shift_type: str = 'DAY'):
        """
        Args:
            engine: SeverityEngine instance with incidents/escalations logged
            results_df: DataFrame of scored results from engine.process_batch()
            shift_type: 'DAY', 'NIGHT', 'FRONT_HALF', or 'BACK_HALF'
        """
        self.engine = engine
        self.results = results_df
        self.shift_type = shift_type
        self.shift_name = self.SHIFT_NAMES.get(shift_type, ('Custom Shift', '00:00', '23:59'))[0]
        self.generated_at = datetime.now()
        
        # Compute metrics
        self._compute_metrics()
    
    def _compute_metrics(self):
        """Pre-compute all report metrics."""
        incidents = self.engine.incidents
        escalations = self.engine.escalations
        
        # Health score (0-100, higher = healthier)
        total_readings = len(self.results)
        green_readings = len(self.results[self.results['final_severity'] == 'GREEN'])
        self.health_score = round((green_readings / total_readings) * 100) if total_readings > 0 else 0
        
        # Severity distribution
        self.severity_counts = self.results['final_severity'].value_counts().to_dict()
        
        # Incident stats
        self.total_incidents = len(incidents)
        self.red_incidents = len([i for i in incidents if i.severity == 'RED'])
        self.orange_incidents = len([i for i in incidents if i.severity == 'ORANGE'])
        
        # Escalation stats
        self.total_escalations = len(escalations)
        
        # Zone breakdown
        self.zone_summary = {}
        for zone in self.results['zone'].unique():
            zone_data = self.results[self.results['zone'] == zone]
            zone_incidents = [i for i in incidents if i.zone == zone]
            self.zone_summary[zone] = {
                'avg_util': zone_data['utilization_pct'].mean(),
                'max_util': zone_data['utilization_pct'].max(),
                'min_util': zone_data['utilization_pct'].min(),
                'time_in_red': len(zone_data[zone_data['final_severity'] == 'RED']),
                'time_in_orange': len(zone_data[zone_data['final_severity'] == 'ORANGE']),
                'incidents': len(zone_incidents),
                'worst_severity': zone_data['final_severity'].map(
                    {'GREEN': 0, 'YELLOW': 1, 'ORANGE': 2, 'RED': 3}
                ).max()
            }
        
        # Top drivers
        all_drivers = []
        for i in incidents:
            all_drivers.extend(i.drivers)
        self.top_drivers = Counter(all_drivers).most_common(5)
        
        # Repeat offenders (zones with most incidents)
        zone_incident_counts = Counter(i.zone for i in incidents)
        self.repeat_offenders = zone_incident_counts.most_common(3)
        
        # Unresolved items (zones that ended shift in non-GREEN)
        if len(self.results) > 0:
            last_timestamp = self.results['timestamp'].max()
            last_readings = self.results[self.results['timestamp'] == last_timestamp]
            self.unresolved = last_readings[last_readings['final_severity'].isin(['ORANGE', 'RED'])]
        else:
            self.unresolved = pd.DataFrame()
    
    # ------------------------------------------
    # CONSOLE OUTPUT
    # ------------------------------------------
    
    def generate(self):
        """Print full report to console."""
        print(self._build_text_report())
    
    def _build_text_report(self) -> str:
        """Build plain-text report."""
        lines = []
        w = 60
        
        # Header
        lines.append("=" * w)
        lines.append("  SHIFT HANDOFF REPORT")
        lines.append(f"  {self.shift_name} | CMH7 Outbound")
        lines.append(f"  Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * w)
        
        # Health Score
        lines.append("")
        health_bar = self._health_bar(self.health_score)
        health_label = self._health_label(self.health_score)
        lines.append(f"  SHIFT HEALTH: {self.health_score}/100 ({health_label})")
        lines.append(f"  {health_bar}")
        
        # Summary stats
        lines.append("")
        lines.append("  SUMMARY")
        lines.append("  " + "-" * (w - 4))
        lines.append(f"  Total readings:    {len(self.results)}")
        lines.append(f"  Total incidents:   {self.total_incidents}")
        lines.append(f"  Escalations:       {self.total_escalations}")
        lines.append(f"  RED events:        {self.red_incidents}")
        lines.append(f"  ORANGE events:     {self.orange_incidents}")
        
        # Severity breakdown
        lines.append("")
        lines.append("  SEVERITY DISTRIBUTION")
        lines.append("  " + "-" * (w - 4))
        for sev in ['GREEN', 'YELLOW', 'ORANGE', 'RED']:
            count = self.severity_counts.get(sev, 0)
            pct = count / len(self.results) * 100 if len(self.results) > 0 else 0
            bar = self._severity_bar(count, len(self.results))
            lines.append(f"  {sev:<7} {count:>3} ({pct:4.1f}%) {bar}")
        
        # Zone performance
        lines.append("")
        lines.append("  ZONE PERFORMANCE")
        lines.append("  " + "-" * (w - 4))
        lines.append(f"  {'Zone':<16} {'Avg':>5} {'Max':>5} {'Red':>4} {'Inc':>4}")
        lines.append("  " + "-" * 40)
        
        sorted_zones = sorted(self.zone_summary.items(), 
                            key=lambda x: -x[1]['worst_severity'])
        for zone, stats in sorted_zones:
            lines.append(
                f"  {zone:<16} {stats['avg_util']:>4.1f}% {stats['max_util']:>4.1f}% "
                f"{stats['time_in_red']:>3}  {stats['incidents']:>3}"
            )
        
        # Top drivers
        lines.append("")
        lines.append("  TOP INCIDENT DRIVERS")
        lines.append("  " + "-" * (w - 4))
        for driver, count in self.top_drivers:
            lines.append(f"  {driver:<20} {count} occurrences")
        
        # Unresolved items
        lines.append("")
        lines.append("  CARRY-OVER (unresolved at shift end)")
        lines.append("  " + "-" * (w - 4))
        if len(self.unresolved) > 0:
            for _, row in self.unresolved.iterrows():
                lines.append(f"  [!] {row['zone']:<16} {row['final_severity']:<7} {row['utilization_pct']:.1f}%")
        else:
            lines.append("  None - all zones GREEN at shift end")
        
        # Recommendations for next shift
        lines.append("")
        lines.append("  RECOMMENDATIONS FOR INCOMING SHIFT")
        lines.append("  " + "-" * (w - 4))
        recs = self._generate_recommendations()
        for i, rec in enumerate(recs, 1):
            lines.append(f"  {i}. {rec}")
        
        lines.append("")
        lines.append("=" * w)
        lines.append(f"  Report ID: SHR-{self.generated_at.strftime('%Y%m%d-%H%M')}")
        lines.append(f"  CRISP Performance Translator v0.1 | CMH7")
        lines.append("=" * w)
        
        return "\n".join(lines)
    
    # ------------------------------------------
    # MARKDOWN EXPORT
    # ------------------------------------------
    
    def export_markdown(self, output_path: Optional[str] = None) -> str:
        """Export report as Markdown file."""
        if output_path is None:
            output_path = f"shift_report_{self.generated_at.strftime('%Y%m%d_%H%M')}.md"
        
        md = []
        md.append(f"# Shift Handoff Report")
        md.append(f"**{self.shift_name}** | CMH7 Outbound | {self.generated_at.strftime('%Y-%m-%d %H:%M')}\n")
        
        # Health
        health_label = self._health_label(self.health_score)
        health_emoji = '\U0001f7e2' if self.health_score >= 80 else ('\U0001f7e1' if self.health_score >= 60 else '\U0001f534')
        md.append(f"## {health_emoji} Shift Health: {self.health_score}/100 ({health_label})\n")
        
        # Stats table
        md.append("## Summary\n")
        md.append("| Metric | Value |")
        md.append("|--------|-------|")
        md.append(f"| Total Readings | {len(self.results)} |")
        md.append(f"| Total Incidents | {self.total_incidents} |")
        md.append(f"| Escalations | {self.total_escalations} |")
        md.append(f"| RED Events | {self.red_incidents} |")
        md.append(f"| ORANGE Events | {self.orange_incidents} |")
        md.append("")
        
        # Zone table
        md.append("## Zone Performance\n")
        md.append("| Zone | Avg Util | Peak Util | Time in RED | Incidents |")
        md.append("|------|----------|-----------|-------------|-----------|")
        sorted_zones = sorted(self.zone_summary.items(), key=lambda x: -x[1]['max_util'])
        for zone, stats in sorted_zones:
            md.append(f"| {zone} | {stats['avg_util']:.1f}% | {stats['max_util']:.1f}% | {stats['time_in_red']} windows | {stats['incidents']} |")
        md.append("")
        
        # Drivers
        md.append("## Top Incident Drivers\n")
        for driver, count in self.top_drivers:
            md.append(f"- **{driver.replace('_', ' ').title()}**: {count} occurrences")
        md.append("")
        
        # Carry-over
        md.append("## Carry-Over Items\n")
        if len(self.unresolved) > 0:
            md.append("| Zone | Severity | Utilization |")
            md.append("|------|----------|-------------|")
            for _, row in self.unresolved.iterrows():
                md.append(f"| {row['zone']} | {row['final_severity']} | {row['utilization_pct']:.1f}% |")
        else:
            md.append("*All zones GREEN at shift end. No carry-over items.*")
        md.append("")
        
        # Recommendations
        md.append("## Recommendations for Incoming Shift\n")
        recs = self._generate_recommendations()
        for i, rec in enumerate(recs, 1):
            md.append(f"{i}. {rec}")
        md.append("")
        
        # Footer
        md.append("---")
        md.append(f"*Report ID: SHR-{self.generated_at.strftime('%Y%m%d-%H%M')} | CRISP Performance Translator v0.1 | CMH7*")
        
        content = "\n".join(md)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return output_path
    
    # ------------------------------------------
    # HTML EXPORT
    # ------------------------------------------
    
    def export_html(self, output_path: Optional[str] = None) -> str:
        """Export as styled HTML (command-center aesthetic)."""
        if output_path is None:
            output_path = f"shift_report_{self.generated_at.strftime('%Y%m%d_%H%M')}.html"
        
        health_color = '#00C853' if self.health_score >= 80 else ('#FFD600' if self.health_score >= 60 else '#FF1744')
        
        # Build zone rows
        zone_rows = ""
        sorted_zones = sorted(self.zone_summary.items(), key=lambda x: -x[1]['max_util'])
        for zone, stats in sorted_zones:
            sev_colors = {'0': '#00C853', '1': '#FFD600', '2': '#FF6B35', '3': '#FF1744'}
            color = sev_colors.get(str(stats['worst_severity']), '#888')
            zone_rows += f"""
            <tr>
                <td style="color:{color}; font-weight:600;">{zone}</td>
                <td>{stats['avg_util']:.1f}%</td>
                <td style="font-weight:600;">{stats['max_util']:.1f}%</td>
                <td>{stats['time_in_red']}</td>
                <td>{stats['incidents']}</td>
            </tr>"""
        
        # Build driver list
        driver_items = ""
        for driver, count in self.top_drivers:
            driver_items += f'<div class="driver-item"><span>{driver.replace("_", " ").title()}</span><span class="driver-count">{count}</span></div>'
        
        # Build carry-over
        carry_items = ""
        if len(self.unresolved) > 0:
            for _, row in self.unresolved.iterrows():
                sev_color = '#FF1744' if row['final_severity'] == 'RED' else '#FF6B35'
                carry_items += f'<div class="carry-item"><span style="color:{sev_color}; font-weight:600;">[{row["final_severity"]}]</span> {row["zone"]} at {row["utilization_pct"]:.1f}%</div>'
        else:
            carry_items = '<div style="color:#00C853;">All zones GREEN at shift end.</div>'
        
        # Build recommendations
        rec_items = ""
        recs = self._generate_recommendations()
        for i, rec in enumerate(recs, 1):
            rec_items += f'<div class="rec-item"><span class="rec-num">{i}</span>{rec}</div>'
        
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Shift Handoff Report - {self.generated_at.strftime('%Y-%m-%d')}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #0D1B2A; color: #E0E0E0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 24px; max-width: 900px; margin: 0 auto; }}
.header {{ background: linear-gradient(90deg, #1A1A2E, #16213E); padding: 20px 28px; border-radius: 10px; border-left: 4px solid #FF6B35; margin-bottom: 24px; }}
.header h1 {{ font-size: 20px; color: #fff; margin-bottom: 4px; }}
.header .meta {{ font-size: 12px; color: #888; }}
.health {{ background: #1B2838; border-radius: 10px; padding: 20px; text-align: center; margin-bottom: 20px; }}
.health-score {{ font-size: 48px; font-weight: 700; color: {health_color}; }}
.health-label {{ font-size: 13px; color: #888; letter-spacing: 1px; }}
.section {{ background: #1B2838; border-radius: 10px; padding: 18px; margin-bottom: 16px; }}
.section h2 {{ font-size: 14px; color: #FF6B35; margin-bottom: 12px; letter-spacing: 0.5px; text-transform: uppercase; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th {{ color: #888; text-align: left; padding: 6px 8px; border-bottom: 1px solid #2a3a4a; font-weight: 600; }}
td {{ padding: 8px; border-bottom: 1px solid #1a2a3a; }}
.metric-row {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 20px; }}
.metric-box {{ background: #1B2838; border-radius: 8px; padding: 14px; text-align: center; }}
.metric-val {{ font-size: 22px; font-weight: 700; }}
.metric-lbl {{ font-size: 10px; color: #888; text-transform: uppercase; }}
.driver-item {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #1a2a3a; font-size: 12px; }}
.driver-count {{ color: #FF6B35; font-weight: 600; }}
.carry-item {{ padding: 6px 0; font-size: 12px; border-bottom: 1px solid #1a2a3a; }}
.rec-item {{ display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; font-size: 12px; border-bottom: 1px solid #1a2a3a; }}
.rec-num {{ background: #FF6B35; color: #fff; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; flex-shrink: 0; }}
.footer {{ text-align: center; color: #555; font-size: 10px; padding: 16px 0; }}
</style>
</head>
<body>
<div class="header">
    <h1>Shift Handoff Report</h1>
    <div class="meta">{self.shift_name} | CMH7 Outbound | {self.generated_at.strftime('%Y-%m-%d %H:%M')}</div>
</div>

<div class="health">
    <div class="health-score">{self.health_score}</div>
    <div class="health-label">Shift Health Score ({self._health_label(self.health_score)})</div>
</div>

<div class="metric-row">
    <div class="metric-box"><div class="metric-val">{len(self.results)}</div><div class="metric-lbl">Readings</div></div>
    <div class="metric-box"><div class="metric-val" style="color:#FF1744">{self.total_incidents}</div><div class="metric-lbl">Incidents</div></div>
    <div class="metric-box"><div class="metric-val" style="color:#FF6B35">{self.total_escalations}</div><div class="metric-lbl">Escalations</div></div>
    <div class="metric-box"><div class="metric-val" style="color:#FF1744">{self.red_incidents}</div><div class="metric-lbl">RED Events</div></div>
    <div class="metric-box"><div class="metric-val" style="color:#FFD600">{self.orange_incidents}</div><div class="metric-lbl">ORANGE Events</div></div>
</div>

<div class="section">
    <h2>Zone Performance</h2>
    <table>
        <tr><th>Zone</th><th>Avg Util</th><th>Peak</th><th>RED Windows</th><th>Incidents</th></tr>
        {zone_rows}
    </table>
</div>

<div class="section">
    <h2>Top Incident Drivers</h2>
    {driver_items}
</div>

<div class="section">
    <h2>Carry-Over to Next Shift</h2>
    {carry_items}
</div>

<div class="section">
    <h2>Recommendations for Incoming Shift</h2>
    {rec_items}
</div>

<div class="footer">
    Report ID: SHR-{self.generated_at.strftime('%Y%m%d-%H%M')} | CRISP Performance Translator v0.1 | CMH7
</div>
</body>
</html>"""
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return output_path
    
    # ------------------------------------------
    # HELPER METHODS
    # ------------------------------------------
    
    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations for incoming shift."""
        recs = []
        
        # Unresolved zones
        if len(self.unresolved) > 0:
            zones = ', '.join(self.unresolved['zone'].tolist())
            recs.append(f"Monitor {zones} closely - carried over from previous shift at elevated severity.")
        
        # Repeat offenders
        if self.repeat_offenders:
            worst = self.repeat_offenders[0]
            recs.append(f"{worst[0]} had {worst[1]} incidents this shift - investigate root cause pattern.")
        
        # Driver-specific
        driver_names = [d[0] for d in self.top_drivers]
        if 'LABOR_GAP' in driver_names:
            recs.append("Labor gaps were a top driver - confirm staffing plan covers CPT windows.")
        if 'DOWNTIME' in driver_names:
            recs.append("Equipment downtime contributed to incidents - check RME status for pending repairs.")
        if 'RATE_DROP' in driver_names:
            recs.append("Rate drops detected - review training gaps or system issues in affected zones.")
        if 'WIP_BUILDUP' in driver_names:
            recs.append("WIP buildup signals detected - plan pre-emptive cleardowns before peak windows.")
        
        # CPT window warning
        recs.append("Key CPT windows to watch: 05:00, 11:00, 13:00, 16:00 - pre-position resources 30 min prior.")
        
        # Health-based
        if self.health_score < 60:
            recs.append("Shift health was below 60% - consider escalating capacity concerns to senior leadership.")
        
        return recs[:6]  # Cap at 6 recommendations
    
    def _health_bar(self, score: int, width: int = 30) -> str:
        """Create ASCII health bar."""
        filled = int(score / 100 * width)
        bar = "[" + "#" * filled + "." * (width - filled) + "]"
        return bar
    
    def _health_label(self, score: int) -> str:
        """Convert health score to label."""
        if score >= 90: return "Excellent"
        if score >= 80: return "Healthy"
        if score >= 70: return "Moderate"
        if score >= 60: return "At Risk"
        if score >= 40: return "Degraded"
        return "Critical"
    
    def _severity_bar(self, count: int, total: int, width: int = 20) -> str:
        """Create mini bar for severity distribution."""
        filled = int(count / total * width) if total > 0 else 0
        return "|" + "=" * filled + " " * (width - filled) + "|"


if __name__ == '__main__':
    print("ShiftReport module loaded. Use with SeverityEngine results.")
    print("  report = ShiftReport(engine, results_df)")
    print("  report.generate()")
    print("  report.export_markdown('handoff.md')")
    print("  report.export_html('handoff.html')")
