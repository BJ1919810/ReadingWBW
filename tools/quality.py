# coding=utf-8
"""音质体检：对比 PSOLA 与声码器两条基频变换路线。

指标（定义与实现都在 voice_synth.metrics，两处共用同一口径）：
  长时平均谱差  音色有没有保住（对时移不敏感，是主要判据）
  帧LSD         逐帧谱距离（对时间错位敏感，参考用）
  分段SNR       波形相似度（PSOLA 不保波形，这一项天然偏低）
  噪声底/断续   有没有沙沙噪 / 咔哒声

标尺（务必先看这个，否则数字没有意义）：
  x vs x            =  0.00 dB
  x vs x*0.5        =  5.94 dB（应约 6.02）
  hāo vs māo        =  8.21 dB   <- 同语音包不同音节的自然差距
  hāo vs yī         = 19.45 dB
所以"补齐音节 vs 源录音"只要落在 5-10 dB，就是同一个声音。
"""
import os
import sys

import numpy as np
import pyworld as pw

from _common import ROOT, load_mono  # noqa: F401
sys.path.insert(0, ROOT)
from voice_synth.psola import psola_resynth                    # noqa: E402
from voice_synth.tone_synth import analyze_f0                  # noqa: E402
from voice_synth.metrics import (ltas_dist, seg_snr, hf_ratio,   # noqa: E402
                                 discontinuities)

FRAME_MS = 5.0


def _grid(x, sr):
    n = int(len(x) / sr / (FRAME_MS / 1000.0)) + 1
    return np.arange(n) * (FRAME_MS / 1000.0)


def psola_identity(x, sr):
    """PSOLA 用原 F0 重建：质量上限"""
    f0 = analyze_f0(x, sr)
    return psola_resynth(x, sr, _grid(x, sr), f0, f0)


def psola_shift(x, sr):
    """PSOLA 整体升 2 个半音：检验变换本身的失真"""
    f0 = analyze_f0(x, sr)
    return psola_resynth(x, sr, _grid(x, sr), f0, f0 * 1.12)


def vocoder_roundtrip(x, sr):
    """声码器往返（对照用，不用于生产）"""
    f0, t = pw.harvest(x, sr, f0_floor=60, f0_ceil=400, frame_period=FRAME_MS)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)
    ap = np.nan_to_num(ap, nan=0.0)
    y = pw.synthesize(f0, sp, ap, sr, frame_period=FRAME_MS)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    if len(y) != len(x):
        y = np.interp(np.linspace(0, len(y) - 1, len(x)), np.arange(len(y)), y)
    return y


def evaluate(name, fn, files, pack_dir):
    lt, sn, nf, dc = [], [], [], []
    for n in files:
        p = os.path.join(pack_dir, n + '.ogg')
        if not os.path.exists(p):
            continue
        x, sr = load_mono(p)
        try:
            y = fn(x, sr)[:len(x)]
        except Exception as exc:
            print('   %-18s 失败: %s' % (name, exc))
            return
        lt.append(ltas_dist(x, y, sr))
        sn.append(seg_snr(x, y, sr))
        nf.append(hf_ratio(y, sr))
        dc.append(discontinuities(y, sr))
    print('   %-18s 长时谱差=%5.2fdB  SNR=%6.1fdB  噪声底=%.4f  断续=%.1f'
          % (name, np.mean(lt), np.mean(sn), np.mean(nf), np.mean(dc)))


if __name__ == '__main__':
    from voice_reader import paths
    pack_dir = paths.pack_dir('hanser')
    files = ['hāo', 'yī', 'nǐ', 'zhī', 'māo', 'jiāng', 'shì', 'lǜ']
    print('样本: %s' % ' '.join(files))
    print()
    evaluate('PSOLA 同F0重建', psola_identity, files, pack_dir)
    evaluate('PSOLA 升2半音', psola_shift, files, pack_dir)
    evaluate('声码器往返(对照)', vocoder_roundtrip, files, pack_dir)
