import re
import base64
import struct

import numpy as np
import pandas as pd

from core.config import ADC_RAW_MAX, ADC_FULL_SCALE_V


def decode_v2_signal(base64_str, signal_bytes=3):
    if not base64_str or not isinstance(base64_str, str):
        return np.array([])
    try:
        raw_bytes = base64.b64decode(base64_str.strip())
    except Exception:
        return np.array([])
    points = []
    for i in range(0, len(raw_bytes), signal_bytes):
        chunk = raw_bytes[i:i + signal_bytes]
        if len(chunk) < signal_bytes:
            break
        be_bytes = bytes(reversed(chunk))
        sign_byte = b'\xff' if (be_bytes[0] & 0x80) else b'\x00'
        val = struct.unpack('>i', sign_byte + be_bytes)[0]
        points.append(val >> 2)
    return np.array(points, dtype=np.int32)


def adc_to_physical(adc_shifted, mult, div):
    if div == 0:
        return adc_shifted
    scale = (mult / div) / (ADC_RAW_MAX / ADC_FULL_SCALE_V)
    return adc_shifted * scale


def parse_channel_range(text, max_channels):
    text = text.strip().replace(" ", "").replace("[", "").replace("]", "")
    if not text:
        return list(range(max_channels))
    mask = [False] * max_channels
    parts = re.split(r"[,;/]", text)
    for part in parts:
        sub = re.split(r"[:-]", part)
        if all(x.isdigit() for x in sub):
            nums = list(map(int, sub))
            nums.sort()
            if len(nums) == 1:
                if 0 <= nums[0] - 1 < max_channels:
                    mask[nums[0] - 1] = True
            elif len(nums) >= 2:
                for i in range(nums[0], min(nums[1] + 1, max_channels + 1)):
                    if 0 <= i - 1 < max_channels:
                        mask[i - 1] = True
    return [i for i, v in enumerate(mask) if v]


def parse_timestamp(val):
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return pd.Timestamp(val).timestamp() * 1000
    except Exception:
        return 0.0


def downsample(x, y, max_points):
    if len(x) <= max_points:
        return x, y
    step = max(1, len(x) // max_points)
    return x[::step], y[::step]


def has_data(col):
    vals = col.dropna()
    if len(vals) == 0:
        return False
    if vals.dtype == object:
        non_empty = vals[vals.astype(str).str.strip().astype(bool)]
        return len(non_empty) > 0
    return vals.abs().sum() > 0
