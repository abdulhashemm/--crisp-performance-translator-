"""
CRISP Performance Translator - Data Connector Module
=====================================================
Author: Abdulrahman Hashem | CMH7 Intern Project

Handles ingestion of real CRISP data from various formats:
- CSV exports (manual download from CRISP UI)
- Excel exports (.xlsx)
- Clipboard paste (for quick ad-hoc analysis)
- Future: API integration, S3 bucket polling

Usage:
    from data_connector import CRISPConnector
    
    connector = CRISPConnector()
    
    # From a CSV export
    data = connector.load_csv('crisp_export_20260604.csv')
    
    # From Excel
    data = connector.load_excel('crisp_report.xlsx', sheet_name='Utilization')
    
    # From clipboard (paste from CRISP UI)
    data = connector.load_clipboard()
    
    # Auto-detect format
    data = connector.load('path/to/file.csv')
    
    # Validate and normalize to engine-ready format
    clean_data = connector.normalize(data)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Union
import logging
import json
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger('CRISPConnector')


# ============================================
# COLUMN MAPPING CONFIGURATION
# ============================================
# CRISP exports may have different column names.
# This mapping normalizes them to our internal schema.

DEFAULT_COLUMN_MAP = {
    # Timestamp columns (try these in order)
    'timestamp_candidates': [
        'timestamp', 'Timestamp', 'TIMESTAMP',
        'date_time', 'DateTime', 'DATE_TIME',
        'time', 'Time', 'TIME',
        'window_start', 'Window Start', 'WINDOW_START',
        'cpt_window', 'CPT Window', 'CPT_WINDOW',
        'report_time', 'Report Time'
    ],
    # Zone/process columns
    'zone_candidates': [
        'zone', 'Zone', 'ZONE',
        'process', 'Process', 'PROCESS',
        'process_path', 'Process Path', 'PROCESS_PATH',
        'area', 'Area', 'AREA',
        'department', 'Department',
        'path', 'Path'
    ],
    # Utilization columns
    'utilization_candidates': [
        'utilization_pct', 'Utilization', 'UTILIZATION',
        'utilization_%', 'Utilization %', 'UTILIZATION_%',
        'util', 'Util', 'UTIL',
        'capacity_utilization', 'Capacity Utilization',
        'pct_utilized', 'forecast_utilization',
        'Forecast Utilization', 'Forecasted Utilization'
    ],
    # WIP / volume columns
    'wip_candidates': [
        'wip_units', 'WIP', 'wip',
        'wip_count', 'WIP Count',
        'units_in_process', 'Units In Process',
        'backlog', 'Backlog', 'BACKLOG',
        'volume', 'Volume'
    ],
    # Throughput columns
    'throughput_candidates': [
        'throughput_rate_uph', 'Throughput', 'THROUGHPUT',
        'rate', 'Rate', 'RATE',
        'uph', 'UPH', 'units_per_hour',
        'throughput_rate', 'Throughput Rate'
    ],
    # Labor columns
    'labor_candidates': [
        'labor_headcount', 'Headcount', 'HEADCOUNT',
        'labor', 'Labor', 'LABOR',
        'hc', 'HC', 'head_count',
        'associates', 'Associates', 'staffing'
    ],
    # Downtime columns
    'downtime_candidates': [
        'downtime_minutes', 'Downtime', 'DOWNTIME',
        'downtime_min', 'Downtime (min)',
        'equipment_downtime', 'Equipment Downtime',
        'dt_minutes', 'DT Minutes'
    ]
}

# Zone name normalization (CRISP may use different naming)
ZONE_ALIASES = {
    # PC Singles variations
    'pc_singles': 'PC_Singles',
    'pc singles': 'PC_Singles',
    'PC Singles': 'PC_Singles',
    'PC_SINGLES': 'PC_Singles',
    'singles': 'PC_Singles',
    'Singles': 'PC_Singles',
    'SINGLES': 'PC_Singles',
    # PC Multis variations
    'pc_multis': 'PC_Multis',
    'pc multis': 'PC_Multis',
    'PC Multis': 'PC_Multis',
    'PC_MULTIS': 'PC_Multis',
    'multis': 'PC_Multis',
    'Multis': 'PC_Multis',
    'MULTIS': 'PC_Multis',
    # SLAM
    'slam': 'SLAM',
    'Slam': 'SLAM',
    'SLAM Line': 'SLAM',
    # Sorter
    'sorter': 'Sorter_Chutes',
    'Sorter': 'Sorter_Chutes',
    'SORTER': 'Sorter_Chutes',
    'sorter_chutes': 'Sorter_Chutes',
    'Sorter/Chutes': 'Sorter_Chutes',
    'chutes': 'Sorter_Chutes',
    'Chutes': 'Sorter_Chutes',
    # Dock
    'dock': 'Dock_Loadout',
    'Dock': 'Dock_Loadout',
    'DOCK': 'Dock_Loadout',
    'dock_loadout': 'Dock_Loadout',
    'Dock/Loadout': 'Dock_Loadout',
    'loadout': 'Dock_Loadout',
    'Loadout': 'Dock_Loadout',
    'LOADOUT': 'Dock_Loadout',
}


# ============================================
# DATA CONNECTOR CLASS
# ============================================

class CRISPConnector:
    """
    Ingests CRISP data from multiple formats and normalizes it
    for the SeverityEngine. Handles messy real-world data:
    - Column name variations
    - Date format parsing
    - Zone name normalization
    - Missing value handling
    - Data validation and quality checks
    """
    
    # Internal schema that the SeverityEngine expects
    REQUIRED_COLUMNS = ['timestamp', 'zone', 'utilization_pct']
    OPTIONAL_COLUMNS = ['wip_units', 'throughput_rate_uph', 'labor_headcount', 'downtime_minutes', 'cpt_window']
    
    CPT_HOURS = [5, 11, 13, 16]  # Standard CMH7 CPT windows
    
    def __init__(self, column_map: Optional[Dict] = None, zone_aliases: Optional[Dict] = None):
        """
        Initialize connector with optional custom mappings.
        
        Args:
            column_map: Override default column name candidates
            zone_aliases: Override default zone name normalization
        """
        self.column_map = column_map or DEFAULT_COLUMN_MAP
        self.zone_aliases = zone_aliases or ZONE_ALIASES
        self.load_history: List[Dict] = []
        self._last_raw = None
        self._last_clean = None
    
    # ------------------------------------------
    # LOADING METHODS
    # ------------------------------------------
    
    def load(self, path: str, **kwargs) -> pd.DataFrame:
        """
        Auto-detect file format and load.
        Supports: .csv, .xlsx, .xls, .tsv, .json
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        ext = path.suffix.lower()
        loaders = {
            '.csv': self.load_csv,
            '.tsv': lambda p, **kw: self.load_csv(p, sep='\t', **kw),
            '.xlsx': self.load_excel,
            '.xls': self.load_excel,
            '.json': self.load_json,
        }
        
        if ext not in loaders:
            raise ValueError(f"Unsupported format: {ext}. Use .csv, .xlsx, .xls, .tsv, or .json")
        
        logger.info(f"Loading {ext} file: {path.name}")
        data = loaders[ext](str(path), **kwargs)
        
        self._log_load(str(path), ext, len(data))
        return data
    
    def load_csv(self, path: str, sep: str = ',', **kwargs) -> pd.DataFrame:
        """Load from CSV/TSV file with flexible parsing."""
        try:
            # Try standard read first
            df = pd.read_csv(path, sep=sep, **kwargs)
        except Exception as e:
            # Try with different encodings
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    df = pd.read_csv(path, sep=sep, encoding=encoding, **kwargs)
                    logger.info(f"Loaded with {encoding} encoding")
                    break
                except:
                    continue
            else:
                raise ValueError(f"Could not parse CSV: {e}")
        
        self._last_raw = df.copy()
        logger.info(f"Loaded CSV: {len(df)} rows x {len(df.columns)} columns")
        return df
    
    def load_excel(self, path: str, sheet_name: Optional[Union[str, int]] = 0, **kwargs) -> pd.DataFrame:
        """Load from Excel file."""
        df = pd.read_excel(path, sheet_name=sheet_name, **kwargs)
        self._last_raw = df.copy()
        logger.info(f"Loaded Excel: {len(df)} rows x {len(df.columns)} columns (sheet: {sheet_name})")
        return df
    
    def load_json(self, path: str, **kwargs) -> pd.DataFrame:
        """Load from JSON (array of records or nested)."""
        with open(path, 'r') as f:
            raw = json.load(f)
        
        if isinstance(raw, list):
            df = pd.DataFrame(raw)
        elif isinstance(raw, dict):
            # Try common nested structures
            for key in ['data', 'records', 'results', 'rows']:
                if key in raw and isinstance(raw[key], list):
                    df = pd.DataFrame(raw[key])
                    break
            else:
                df = pd.DataFrame([raw])
        else:
            raise ValueError("JSON structure not recognized")
        
        self._last_raw = df.copy()
        logger.info(f"Loaded JSON: {len(df)} rows x {len(df.columns)} columns")
        return df
    
    def load_clipboard(self) -> pd.DataFrame:
        """Load from clipboard (paste from CRISP UI or Excel)."""
        try:
            df = pd.read_clipboard()
            self._last_raw = df.copy()
            logger.info(f"Loaded from clipboard: {len(df)} rows x {len(df.columns)} columns")
            return df
        except Exception as e:
            raise ValueError(f"Could not read clipboard: {e}. Copy data first.")
    
    # ------------------------------------------
    # NORMALIZATION
    # ------------------------------------------
    
    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize raw data to engine-ready format.
        Handles column mapping, zone normalization, type coercion,
        timestamp parsing, and CPT window detection.
        
        Returns a clean DataFrame ready for SeverityEngine.process_batch()
        """
        logger.info("Starting normalization...")
        result = pd.DataFrame()
        
        # Step 1: Map columns
        result['timestamp'] = self._find_and_parse_timestamp(df)
        result['zone'] = self._find_and_normalize_zone(df)
        result['utilization_pct'] = self._find_numeric_column(df, 'utilization_candidates')
        
        # Optional columns (fill with defaults if not found)
        result['wip_units'] = self._find_numeric_column(df, 'wip_candidates', default=50)
        result['throughput_rate_uph'] = self._find_numeric_column(df, 'throughput_candidates', default=150)
        result['labor_headcount'] = self._find_numeric_column(df, 'labor_candidates', default=12)
        result['downtime_minutes'] = self._find_numeric_column(df, 'downtime_candidates', default=0)
        
        # Step 2: Detect CPT windows
        result['cpt_window'] = result['timestamp'].dt.hour.isin(self.CPT_HOURS)
        
        # Step 3: Clean up
        result = result.dropna(subset=['timestamp', 'zone', 'utilization_pct'])
        result['utilization_pct'] = result['utilization_pct'].clip(0, 150)  # Sanity bounds
        
        # Step 4: Sort
        result = result.sort_values(['timestamp', 'zone']).reset_index(drop=True)
        
        self._last_clean = result.copy()
        
        # Quality report
        self._quality_report(df, result)
        
        return result
    
    def _find_and_parse_timestamp(self, df: pd.DataFrame) -> pd.Series:
        """Find timestamp column and parse to datetime."""
        col = self._find_column(df, 'timestamp_candidates')
        if col is None:
            # Try to find any datetime-like column
            for c in df.columns:
                try:
                    parsed = pd.to_datetime(df[c], errors='coerce')
                    if parsed.notna().sum() > len(df) * 0.5:
                        logger.info(f"Auto-detected timestamp column: '{c}'")
                        return parsed
                except:
                    continue
            raise ValueError("No timestamp column found. Expected: " + 
                           str(self.column_map['timestamp_candidates'][:5]))
        
        return pd.to_datetime(df[col], errors='coerce')
    
    def _find_and_normalize_zone(self, df: pd.DataFrame) -> pd.Series:
        """Find zone column and normalize names."""
        col = self._find_column(df, 'zone_candidates')
        if col is None:
            raise ValueError("No zone/process column found. Expected: " +
                           str(self.column_map['zone_candidates'][:5]))
        
        # Normalize zone names
        return df[col].map(lambda x: self.zone_aliases.get(str(x).strip(), str(x).strip()))
    
    def _find_numeric_column(self, df: pd.DataFrame, candidate_key: str, default=None) -> pd.Series:
        """Find a numeric column by candidate names."""
        col = self._find_column(df, candidate_key)
        if col is None:
            if default is not None:
                logger.warning(f"Column not found for '{candidate_key}', using default={default}")
                return pd.Series([default] * len(df), dtype=float)
            raise ValueError(f"Required column not found: {candidate_key}")
        
        # Handle percentage strings (e.g., "104.9%")
        series = df[col].copy()
        if series.dtype == object:
            series = series.astype(str).str.replace('%', '').str.strip()
        
        return pd.to_numeric(series, errors='coerce')
    
    def _find_column(self, df: pd.DataFrame, candidate_key: str) -> Optional[str]:
        """Find first matching column from candidates list."""
        candidates = self.column_map[candidate_key]
        for candidate in candidates:
            if candidate in df.columns:
                logger.info(f"Mapped '{candidate_key}' -> column '{candidate}'")
                return candidate
        return None
    
    def _quality_report(self, raw_df: pd.DataFrame, clean_df: pd.DataFrame):
        """Log data quality metrics."""
        rows_in = len(raw_df)
        rows_out = len(clean_df)
        dropped = rows_in - rows_out
        
        logger.info(f"Normalization complete:")
        logger.info(f"  Input:  {rows_in} rows")
        logger.info(f"  Output: {rows_out} rows ({dropped} dropped)")
        logger.info(f"  Zones:  {clean_df['zone'].nunique()} unique")
        logger.info(f"  Time range: {clean_df['timestamp'].min()} to {clean_df['timestamp'].max()}")
        
        # Check for data gaps
        zones = clean_df['zone'].unique()
        timestamps = clean_df['timestamp'].unique()
        expected = len(zones) * len(timestamps)
        actual = len(clean_df)
        completeness = actual / expected * 100 if expected > 0 else 0
        logger.info(f"  Completeness: {completeness:.1f}% ({actual}/{expected} zone-time combos)")
        
        if dropped > rows_in * 0.1:
            logger.warning(f"  WARNING: {dropped/rows_in*100:.1f}% of rows dropped during normalization!")
    
    def _log_load(self, path: str, format: str, rows: int):
        """Track load history for debugging."""
        self.load_history.append({
            'timestamp': datetime.now().isoformat(),
            'path': path,
            'format': format,
            'rows': rows
        })
    
    # ------------------------------------------
    # UTILITIES
    # ------------------------------------------
    
    def preview(self, df: pd.DataFrame, n: int = 5) -> str:
        """Pretty-print a preview of the data."""
        return df.head(n).to_string(index=False)
    
    def detect_columns(self, df: pd.DataFrame) -> Dict:
        """
        Analyze a DataFrame and report which columns were detected.
        Useful for debugging when data doesn't load correctly.
        """
        report = {}
        for key in self.column_map:
            col = self._find_column(df, key)
            report[key] = col if col else 'NOT FOUND'
        return report
    
    def get_schema(self) -> Dict:
        """Return the expected output schema."""
        return {
            'required': self.REQUIRED_COLUMNS,
            'optional': self.OPTIONAL_COLUMNS,
            'description': {
                'timestamp': 'datetime - reading timestamp',
                'zone': 'str - normalized zone name (PC_Singles, PC_Multis, SLAM, etc.)',
                'utilization_pct': 'float - capacity utilization percentage (0-150)',
                'wip_units': 'int - units currently in process/waiting',
                'throughput_rate_uph': 'int - units processed per hour',
                'labor_headcount': 'int - associates assigned to zone',
                'downtime_minutes': 'int - equipment downtime in this window',
                'cpt_window': 'bool - True if this is a CPT deadline window'
            }
        }
    
    def create_sample_csv(self, output_path: str = 'sample_crisp_export.csv', rows: int = 50):
        """
        Generate a sample CSV in the format the connector expects.
        Use this to understand the expected input format.
        """
        zones = ['PC_Singles', 'PC_Multis', 'SLAM', 'Sorter_Chutes', 'Dock_Loadout']
        base_time = datetime(2026, 6, 4, 5, 0)
        
        records = []
        for i in range(rows // len(zones)):
            t = base_time + timedelta(minutes=30 * i)
            for zone in zones:
                records.append({
                    'Timestamp': t.strftime('%Y-%m-%d %H:%M:%S'),
                    'Process Path': zone,
                    'Utilization %': f"{np.random.uniform(60, 110):.1f}%",
                    'WIP Count': np.random.randint(20, 100),
                    'Throughput': np.random.randint(100, 200),
                    'Headcount': np.random.randint(8, 16),
                    'Downtime (min)': np.random.choice([0, 0, 0, 5, 10, 15])
                })
        
        df = pd.DataFrame(records)
        df.to_csv(output_path, index=False)
        logger.info(f"Sample CSV saved: {output_path} ({len(df)} rows)")
        return df


# ============================================
# REDO CONNECTOR (future expansion)
# ============================================

class REDOConnector:
    """
    Placeholder for REDO data ingestion.
    REDO provides additional operational signals that can
    supplement CRISP utilization data.
    
    TODO: Implement once REDO export format is confirmed.
    """
    
    def __init__(self):
        self.supported = False
        logger.info("REDOConnector initialized (not yet implemented)")
    
    def load(self, path: str) -> pd.DataFrame:
        raise NotImplementedError(
            "REDO connector not yet implemented. "
            "Need to confirm export format and access method."
        )


# ============================================
# PIPELINE: Full load-normalize-engine flow
# ============================================

def run_pipeline(file_path: str, engine=None):
    """
    One-liner to go from raw file to scored results.
    
    Usage:
        from data_connector import run_pipeline
        results, engine = run_pipeline('crisp_export.csv')
    """
    from crisp_translator import SeverityEngine
    
    connector = CRISPConnector()
    raw = connector.load(file_path)
    clean = connector.normalize(raw)
    
    if engine is None:
        engine = SeverityEngine()
    
    results = engine.process_batch(clean)
    
    logger.info(f"Pipeline complete: {len(results)} readings scored")
    logger.info(f"  Incidents: {len(engine.incidents)}")
    logger.info(f"  Escalations: {len(engine.escalations)}")
    
    return results, engine


if __name__ == '__main__':
    # Demo: create sample data and run through connector
    connector = CRISPConnector()
    
    # Generate sample CSV
    sample = connector.create_sample_csv('sample_crisp_export.csv')
    print("\nSample CSV preview:")
    print(connector.preview(sample))
    
    # Load and normalize it
    loaded = connector.load_csv('sample_crisp_export.csv')
    clean = connector.normalize(loaded)
    
    print("\nNormalized output preview:")
    print(connector.preview(clean))
    
    print("\nSchema:")
    for k, v in connector.get_schema()['description'].items():
        print(f"  {k}: {v}")
