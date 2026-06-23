import os
import json

import pandas as pd
import numpy as np

from core.config import STANDARD_SIGNALS
from core.signal_processing import decode_v2_signal, adc_to_physical, parse_timestamp, has_data


def load_csv(file_or_path):
    return pd.read_csv(file_or_path, sep=";")


def load_meta_json(folder_path):
    meta_path = os.path.join(folder_path, "meta.json")
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def detect_columns(df):
    ts_col = "timestamp" if "timestamp" in df.columns else df.columns[0]
    x = np.array([parse_timestamp(v) for v in df[ts_col]], dtype=float)

    rms_cols = [c for c in df.columns if "rms" in c.lower() or "RMS" in c]
    if not rms_cols:
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if ts_col in num_cols:
            num_cols.remove(ts_col)
        rms_cols = num_cols[:6]
    rms_cols = [c for c in rms_cols if has_data(df[c])]

    signal_cols = [c for c in df.columns if "signal" in c.lower() or "base64" in c.lower() or "osc" in c.lower()]
    signal_cols = [c for c in signal_cols if "length" not in c.lower()]

    for s in STANDARD_SIGNALS:
        if s not in signal_cols and s in df.columns:
            signal_cols.append(s)
    signal_cols = [s for s in STANDARD_SIGNALS if s in signal_cols or s in df.columns]
    if not signal_cols:
        signal_cols = STANDARD_SIGNALS[:6]

    return ts_col, x, rms_cols, signal_cols


def get_physical_signals(cursor_idx, signal_cols, df):
    result = {}
    if "U_mult" in df.columns and "U_dev" in df.columns:
        row = df.iloc[cursor_idx]
        u_mult = float(row.get("U_mult", 47)) if pd.notna(row.get("U_mult")) else 47
        u_dev = float(row.get("U_dev", 47)) if pd.notna(row.get("U_dev")) else 47
    else:
        u_mult, u_dev = 47, 47
    if "I_mult" in df.columns and "I_dev" in df.columns:
        row = df.iloc[cursor_idx]
        i_mult = float(row.get("I_mult", 25000)) if pd.notna(row.get("I_mult")) else 25000
        i_dev = float(row.get("I_dev", 66)) if pd.notna(row.get("I_dev")) else 66
    else:
        i_mult, i_dev = 25000, 66

    for sig_col in signal_cols:
        sig_str = df.iloc[cursor_idx][sig_col]
        signal = decode_v2_signal(str(sig_str))
        if len(signal) > 0:
            is_voltage = "U_" in sig_col or "voltage" in sig_col.lower()
            mult = u_mult if is_voltage else i_mult
            div = u_dev if is_voltage else i_dev
            signal = adc_to_physical(signal, mult, div)
            result[sig_col] = {
                "signal": signal,
                "is_voltage": is_voltage,
                "unit": "В" if is_voltage else "А",
            }
        else:
            result[sig_col] = None
    return result


def format_local_time(ts_str):
    if not ts_str or ts_str == "\u2014":
        return "\u2014"
    try:
        dt = pd.Timestamp(ts_str)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(ts_str)
