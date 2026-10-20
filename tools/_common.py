# coding=utf-8
"""tools/ 共用的小工具。

各脚本原本各自抄了一遍 sys.path 拼接、读音频、拼片段的代码，
这里收成一处。
"""
import os
import sys

import numpy as np
import soundfile as sf

# 项目根（tools/ 的上一级）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SAMPLE_RATE = 48000


def load_mono(path, target_sr=SAMPLE_RATE):
    """读音频 -> (float64 单声道, 采样率)"""
    data, sr = sf.read(path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if target_sr and sr != target_sr:
        n_out = int(len(data) * target_sr / sr)
        if n_out > 0:
            data = np.interp(np.linspace(0, len(data) - 1, n_out),
                             np.arange(len(data)), data)
            sr = target_sr
    return data.astype(np.float64), sr


def concat(clips, gap=0.0, lead=0.0, sr=SAMPLE_RATE):
    """把若干片段拼成一段，中间插入 gap 秒静音"""
    parts = [np.zeros(int(lead * sr))]
    for i, c in enumerate(clips):
        if i:
            parts.append(np.zeros(int(gap * sr)))
        parts.append(c)
    return np.concatenate(parts) if parts else np.zeros(sr)


def write_wav(path, data, sr=SAMPLE_RATE, target=0.89):
    """写 wav，做峰值归一防削波"""
    peak = float(np.max(np.abs(data))) if len(data) else 0.0
    if peak > 0:
        data = data / peak * target
    sf.write(path, np.clip(data, -1, 1).astype(np.float32), sr)
    return path
