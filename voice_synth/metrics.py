# coding=utf-8
"""音频质量度量（构建校验与离线工具共用）。

之前这些函数在 tools/quality.py 里，而构建时的校验又需要同一套口径，
所以抽到这里，避免两处各写一份、指标悄悄对不上。
"""
import numpy as np
from scipy.fft import dct
from scipy.signal import stft      # 提到模块级：函数内 import 每次都要查 sys.modules


def mel_power(x, sr, n_fft=1024, n_mel=40, fmax=8000.0):
    """线性 mel 功率谱（每帧 n_mel 个带）。

    用 scipy.signal.stft 一次算完所有帧，不要用 Python 循环逐帧 FFT
    （校验时每个音节要算两遍，慢十几倍）。
    """
    freqs = np.linspace(0, sr / 2, n_fft // 2 + 1)
    mel = 2595 * np.log10(1 + freqs / 700)
    mel_max = 2595 * np.log10(1 + fmax / 700)
    pts = np.linspace(mel[0], mel_max, n_mel)
    idx = np.searchsorted(mel, pts)
    f, t, Z = stft(x, fs=sr, window='hann', nperseg=n_fft, noverlap=n_fft - 256,
                   nfft=n_fft, boundary=None, padded=False)
    P = (np.abs(Z) ** 2).T                      # (frames, bins)
    if P.shape[0] == 0:
        return np.full((1, n_mel), 1e-12)
    out = np.zeros((P.shape[0], n_mel))
    for i in range(n_mel):
        a = min(idx[i], len(freqs) - 2)
        b = max(min(idx[i + 1] if i + 1 < n_mel else len(freqs) - 1,
                    len(freqs) - 1), a + 1)
        out[:, i] = P[:, a:b].mean(axis=1) + 1e-12
    return out


def mel_spec(x, sr, n_fft=1024, n_mel=40, floor_db=-100.0, fmax=8000.0):
    """mel 频谱（每帧 n_mel 个带），单位为相对峰值的 dB。

    三个必要的处理：
    1) 先按峰值归一 —— 否则比较的是绝对电平，响度差会被当成音色差
       （这正是之前误判"音色漂移 13dB"的原因）。
    2) 只取 0~8kHz 的【语音频带】。再高的频段对音色听感的贡献可以忽略，
       而素材在这些频段常常是数值零，两侧一对比就放大成几十 dB 的假差异
       （实测源 -127dB vs 输出 -38dB，实际两者 14k 以上能量几乎相同）。
    3) 给每个带设绝对下限，避免贴底时 log 放大噪声。
    """
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak > 0:
        x = x / peak
    P = mel_power(x, sr, n_fft, n_mel, fmax)
    out = 10 * np.log10(P)
    return np.maximum(out, floor_db)


def mel_cepstrum(x, sr, n_fft=1024, n_mel=40, n_cep=20, lifter=22):
    """倒谱系数（只保留声道包络）。

    线性 mel 功率 -> log -> 正交 DCT-II -> 截取前 n_cep 个系数（去掉 c0 能量项）
    -> 倒谱提升去掉高频倒谱：谐波梳的位置被滤掉，留下的是声道（共振峰）包络，
    也就是"音色"。因此它对"变调引起的谐波位移"不敏感。
    """
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak > 0:
        x = x / peak
    P = mel_power(x, sr, n_fft, n_mel)
    logS = np.log(P)
    C = dct(logS, type=2, axis=1, norm='ortho')
    c = C[:, :n_cep].copy()
    idx = np.arange(n_cep)
    c[:, 1:] *= np.exp(-0.5 * (idx[1:] / float(lifter)) ** 2)
    return c


def mcd(a, b, sr):
    """mel 倒谱失真 dB：只比音色（声道包络），对变调引起的谐波位移不敏感"""
    ca, cb = mel_cepstrum(a, sr), mel_cepstrum(b, sr)
    n = min(len(ca), len(cb))
    if n == 0:
        return float('nan')
    d = ca[:n, 1:] - cb[:n, 1:]
    return float((10.0 / np.log(10)) * np.sqrt(2.0 * (d ** 2).sum(axis=1).mean()))


def ltas(x, sr, n_fft=1024, n_mel=40):
    """长时平均谱：所有帧 mel 谱的平均。

    比逐帧 LSD 更能反映"音色有没有保住"——逐帧比较会被 PSOLA 的
    微小时间错位严重拖累，而听感上时间错位并不明显。
    """
    return mel_spec(x, sr, n_fft, n_mel).mean(axis=0)


def ltas_dist(a, b, sr, level_invariant=True):
    """长时平均谱距离 dB。

    默认【对电平不变】：先减去各自的平均电平，只比较频谱形状。
    音色是"长什么样子"，不是"多响"——源音频和合成音频的峰值因数不同，
    直接比较绝对电平会把单纯的响度差误判成音色漂移
    （实测误判高达 13dB，而实际频谱形状只差 1-2dB）。
    """
    A, B = ltas(a, sr), ltas(b, sr)
    n = min(len(A), len(B))
    if n == 0:
        return float('nan')
    A, B = A[:n], B[:n]
    if level_invariant:
        A = A - A.mean()
        B = B - B.mean()
    return float(np.sqrt(((A - B) ** 2).mean()))


def seg_snr(a, b, sr, win=0.02):
    """分段信噪比 dB（重建 vs 原音）"""
    n = int(win * sr)
    m = min(len(a), len(b)) // n * n
    if m == 0:
        return float('nan')
    aa, bb = a[:m].reshape(-1, n), b[:m].reshape(-1, n)
    num = np.sum(aa ** 2, axis=1)
    den = np.sum((aa - bb) ** 2, axis=1)
    return float(np.mean(10 * np.log10(np.maximum(num, 1e-12) /
                                      np.maximum(den, 1e-12))))


def hf_ratio(x, sr):
    """高频(6-12k)能量占比，用来发现"沙沙噪"型坏音频"""
    X = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    band = X[(freqs > 6000) & (freqs < 12000)]
    return float((np.sum(band ** 2) / max(np.sum(X ** 2), 1e-12)) ** 0.5)


def discontinuities(x, sr, win=0.010):
    """咔哒声计数：相邻 10ms 窗 RMS 跳变超过 6dB 的次数"""
    n = max(int(win * sr), 1)
    m = len(x) // n * n
    if m < 2 * n:
        return 0
    r = np.sqrt((x[:m].reshape(-1, n) ** 2).mean(axis=1))
    db = 20 * np.log10(np.maximum(r, 1e-6))
    return int((np.abs(np.diff(db)) > 6).sum())
