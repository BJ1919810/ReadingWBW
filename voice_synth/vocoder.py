# coding=utf-8
"""声码器后端：用 WORLD 保留频谱包络、只改基频。

相比 PSOLA：
  * 频谱包络（共振峰 = 音色）原样保留，不会有相位抵消造成的"电音"
  * 基频逐帧可精确控制，声调准确率明显更高（实测 67% vs 50%）
  * 代价：必须绕开这版 pyworld 的 d4c 缺陷

这版 pyworld 的 d4c 缺陷：约 15% 的频点是 NaN。
处理办法：
  - 清音帧 ap = 1.0（纯噪声）
  - 浊音帧 ap 里 NaN 的频点在【频率轴】上线性插值补齐
    （ap 沿频率是平滑的，插值出来的值足够准）
"""
import numpy as np
import pyworld as pw

FRAME_MS = 5.0
F0_FLOOR, F0_CEIL = 60.0, 400.0


def fix_nan_rows(mat):
    """按行（频率轴）线性插值修复 NaN；整行皆 NaN 用全局中位数兜底"""
    mat = np.array(mat, dtype=float, copy=True)
    if not np.isnan(mat).any():
        return mat
    fallback = np.nanmedian(mat) if not np.isnan(mat).all() else 0.5
    out = mat.copy()
    for i in range(out.shape[0]):
        row = out[i]
        bad = np.isnan(row)
        if not bad.any():
            continue
        if bad.all():
            out[i] = fallback
            continue
        good = ~bad
        out[i, bad] = np.interp(np.where(bad)[0], np.where(good)[0], row[good])
    return out


def analyze(x, sr):
    """F0 + 频谱包络 + 非周期性"""
    f0, t = pw.harvest(x, sr, f0_floor=F0_FLOOR, f0_ceil=F0_CEIL,
                       frame_period=FRAME_MS)
    if int((f0 > 0).sum()) < 4:
        f0, t = pw.dio(x, sr, f0_floor=40, f0_ceil=900, frame_period=FRAME_MS)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)
    ap = fix_nan_rows(np.nan_to_num(ap, nan=np.nan))
    ap = np.clip(ap, 0.0, 1.0)
    ap[f0 <= 0] = 1.0          # 清音 = 纯噪声
    return f0, sp, ap


def resynth(x, sr, f0_target, analysis=None):
    """按 f0_target 重建（f0_target 与 analyze 返回的 f0 同网格）。

    analysis 可以传入之前算好的 (f0, sp, ap) 复用 ——
    同一个源录音要合成多个声调时，不必反复分析。
    """
    if analysis is None:
        analysis = analyze(x, sr)
    f0, sp, ap = analysis
    new_f0 = f0.copy()
    n = min(len(new_f0), len(f0_target))
    vi = np.where(f0[:n] > 0)[0]
    if len(vi):
        new_f0[vi] = f0_target[vi]
    y = pw.synthesize(new_f0, sp, ap, sr, frame_period=FRAME_MS)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    if len(y) != len(x):
        y = np.interp(np.linspace(0, len(y) - 1, len(x)), np.arange(len(y)), y)
    return y
