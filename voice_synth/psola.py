# coding=utf-8
"""TD-PSOLA：时域基频同步叠加的基频变换。

做法：
  浊音段切成"基频同步"的波形小段（以基频标记为中心），
  按目标 F0 轮廓重新摆放这些小段并叠加相加。
  波形本身是原音的原始采样，只改了时间位置，不做频域重建。

时间轴怎么建（这是最关键、也最容易做错的一步）：
  用【检测到的源周期】直接推进，而不是用 F0 积分重建一套标记。
  原因：F0 估计和真实周期之间有慢漂移，用积分生成的目标标记会和源标记
  逐渐错位，段投到错误的位置 -> 叠加互相抵消 -> 听感就是"电音"。
  实测：F0 积分版即使做同 F0 重建也有 6.5dB 音色漂移（应该接近 0）。

  正确做法：
    源标记 m_i 的真实周期 T_i（峰值间距，精确）
    目标周期 T*_i = T_i × f0_src(t_i) / f0_tgt(t_i)
    输出标记 s_0 = t_0, s_{i+1} = s_i + T*_i
    源段（2 个源周期）重采样到 2 个目标周期后，Hanning 窗投放到 s_i
  这样：
    - 同 F0 时 T*_i = T_i，两个操作都是空操作 -> 完美重建
    - 变调时段的内部周期与投放步长一致 -> 无相位抵消
    - 窗长 = 2×步长 -> 50% 重叠，Hanning 窗求和恒为 1 -> 无幅度调制
"""
import numpy as np

FRAME_S = 0.005
RATIO_LIMIT = (0.65, 1.55)      # 周期缩放比上下限，防止共振峰漂太狠


def smooth_f0(f0, width=3):
    """平滑 F0 轨迹：中值滤波 + 移动平均（只作用于浊音段）"""
    f = np.array(f0, dtype=float, copy=True)
    voiced = f > 0
    if voiced.sum() < width + 2:
        return f
    v = f[voiced]
    pad = width // 2
    vp = np.pad(v, pad, mode='edge')
    v = np.median(np.lib.stride_tricks.sliding_window_view(vp, width), axis=1)
    vp = np.pad(v, pad, mode='edge')
    v = np.mean(np.lib.stride_tricks.sliding_window_view(vp, width), axis=1)
    f[voiced] = v
    return f


def _pitch_marks(x, sr, times, f0, t_start, t_end):
    """浊音区的基频标记（glottal closure 近似：绝对值局部极大）。

    按 F0 预测下一个标记的位置，再在该位置附近找峰：
    这样每个周期必定产出一个标记。
    """
    n = len(x)
    marks = []
    t = t_start
    guard = 0
    while t < t_end and guard < 8000:
        guard += 1
        f = float(np.interp(t, times, f0, left=0, right=0))
        if f <= 0:
            break
        period = sr / f
        if period < 2 or period > sr / 40:
            break
        center = int(t * sr)
        lo = max(1, center - int(0.3 * period))
        hi = min(n, center + int(0.3 * period))
        if hi - lo < 3:
            t += period / sr
            continue
        p = lo + int(np.argmax(np.abs(x[lo:hi])))
        if marks and p - marks[-1] < period * 0.6:
            t = (p + period * 0.7) / sr
            continue
        marks.append(p)
        t = (p + period * 0.7) / sr
    return marks


def _voiced_span(times, f0):
    """浊音区的时间范围 [t_start, t_end]"""
    voiced = np.where(f0 > 0)[0]
    if len(voiced) < 3:
        return None, None
    return times[voiced[0]], times[voiced[-1]] + FRAME_S


def psola_resynth(x, sr, times, f0_src, f0_tgt):
    """按 f0_tgt 重塑 x 的基频轮廓。times/f0 为同一长度的 5ms 网格。"""
    x = np.asarray(x, dtype=np.float64)
    n_in = len(x)
    duration = n_in / sr
    if len(times) < 2 or len(f0_src) != len(times) or len(f0_tgt) != len(times):
        return x.copy()

    t_start, t_end = _voiced_span(times, f0_src)
    if t_start is None:
        return x.copy()

    src_marks = _pitch_marks(x, sr, times, f0_src, t_start, t_end)
    K = len(src_marks)
    if K < 3:
        return x.copy()

    f0_tgt_s = smooth_f0(f0_tgt)

    # 源标记的【实际相邻间距】（不是平均间距——用平均会让时间轴和源标记错开）
    D = np.diff(np.array(src_marks, dtype=np.float64))
    if len(D) < 2:
        return x.copy()

    # 目标间距 = 实际间距 × (源F0/目标F0)，取中点处的 F0 比值
    mid_t = (np.array(src_marks[:-1], dtype=np.float64) +
             np.array(src_marks[1:], dtype=np.float64)) / 2.0 / sr
    fs = np.interp(mid_t, times, f0_src, left=0, right=0)
    ft = np.interp(mid_t, times, f0_tgt_s, left=0, right=0)
    ratio = np.ones(len(D))
    ok = (fs > 0) & (ft > 0)
    ratio[ok] = fs[ok] / ft[ok]
    ratio = np.clip(ratio, RATIO_LIMIT[0], RATIO_LIMIT[1])
    tgt_gap = D * ratio                     # 目标投放间距（样本）

    # 输出时间轴：直接用源标记位置推进
    src_t = np.array(src_marks, dtype=np.float64) / sr
    out_t = np.empty(K)
    out_t[0] = src_t[0]
    for i in range(1, K):
        out_t[i] = out_t[i - 1] + tgt_gap[i - 1] / sr

    out_len = int(duration * sr)
    y = np.zeros(out_len + sr, dtype=np.float64)
    wsum = np.zeros_like(y)

    for i in range(K):
        # 源段跨前后两个标记：[m_{i-1}, m_{i+1}]，内容是原音的原始采样
        lo = src_marks[i - 1] if i > 0 else src_marks[i] - int(D[0] / 2)
        hi = src_marks[i + 1] if i < K - 1 else src_marks[i] + int(D[-1] / 2)
        lo = int(max(0, lo))
        hi = int(min(n_in, hi))
        if hi - lo < 4:
            continue
        seg = x[lo:hi]

        # 重采样到 2 个目标间距：段的内部周期 = 投放步长 = 目标周期
        half_t = max(int(round(tgt_gap[min(i, len(tgt_gap) - 1)])), 2)
        want = 2 * half_t
        if len(seg) != want:
            seg = np.interp(np.linspace(0, len(seg) - 1, want),
                            np.arange(len(seg)), seg)
        win = np.hanning(want)

        center = int(out_t[i] * sr)
        o_lo = center - want // 2
        o_hi = o_lo + want
        s_lo = max(0, o_lo)
        s_hi = min(len(y), o_hi)
        if s_hi <= s_lo:
            continue
        y[s_lo:s_hi] += seg[s_lo - o_lo:s_hi - o_lo] * win[s_lo - o_lo:s_hi - o_lo]
        wsum[s_lo:s_hi] += win[s_lo - o_lo:s_hi - o_lo]

    covered = wsum > 1e-3
    out = np.zeros(out_len)
    out[covered[:out_len]] = (y[:out_len][covered[:out_len]] /
                              wsum[:out_len][covered[:out_len]])
    # 清音/无声区保留原始波形（清辅音不受基频影响）
    voiced = np.interp(np.arange(out_len) / sr, times, f0_src, left=0, right=0) > 0
    out[~voiced] = x[:out_len][~voiced]
    return out
