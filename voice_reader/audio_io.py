# coding=utf-8
"""音频读写（运行时与离线工具共用）。

之前 load_audio / 读 ogg 这类逻辑在 tone_synth、player、SearchTool、
tools 脚本里各写了一遍，行为还不一致（有的转单声道有的没转，
有的重采样有的没重采样）。这里收成一处。
"""
import numpy as np
import soundfile as sf

SAMPLE_RATE = 48000        # 语音包素材统一采样率


def to_mono(data):
    """多声道 -> 单声道"""
    if getattr(data, 'ndim', 1) > 1:
        return data.mean(axis=1)
    return data


SINC_HALF = 16          # sinc 核半长（输入采样点）


def _sinc_resample(data, sr_in, sr_out, half=SINC_HALF):
    """带限 sinc 插值重采样（纯 numpy，运行时不需要 scipy）。

    为什么不用线性插值：线性插值等效于一个三角形低通，
    升采样时会把 11~22kHz 削掉 3~6dB —— 语音的"空气感"没了，
    听起来就"薄"、"尖细"。实测 44.1k 片段的高频能量占比
    被砍掉 36%~41%，而 sinc 版本能原样保住。

    核的截止频率 = min(sr_in, sr_out)/2（连续时间意义），
    降采样时自动带限，避免混叠。
    """
    from math import gcd
    if sr_in == sr_out or len(data) == 0:
        return data
    g = gcd(int(sr_in), int(sr_out))
    up, down = int(sr_out) // g, int(sr_in) // g
    n_out = int(round(len(data) * up / down))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    # 输出采样点对应的输入连续时间位置
    t = np.arange(n_out) * (down / up)
    base = np.floor(t).astype(np.int64)
    frac = t - base
    k = np.arange(-half + 1, half + 1, dtype=np.int64)
    n_taps = k.shape[0]
    idx = base[:, None] + k[None, :]
    valid = (idx >= 0) & (idx < len(data))
    idxc = np.clip(idx, 0, len(data) - 1)
    # 截止频率（输入 Nyquist 的比例）
    c = min(sr_out / sr_in, 1.0)
    win = np.hanning(n_taps)
    ker = np.sinc(c * (frac[:, None] - k[None, :])) * win[None, :]
    out = np.sum(data[idxc] * ker, axis=1)
    out[~valid.all(axis=1)] = 0.0
    # 保持电平：核的和约等于 1/c，按比例补偿
    out = out * (c if c < 1.0 else 1.0)
    return out.astype(np.float32)


def resample(data, sr_in, sr_out):
    """重采样到目标采样率（带限 sinc 插值）。

    素材里 44.1k 和 48k 混着（顶层 120 个 44.1k / 679 个 48k，
    词组 76 / 144）。播放器统一到 48k，44.1k 的片段必须重采样 ——
    用线性插值会把高频空气感削掉三四成，听起来"尖细"。
    """
    if sr_in == sr_out or len(data) == 0:
        return data, sr_in
    out = _sinc_resample(np.asarray(data, dtype=np.float64), sr_in, sr_out)
    # 窗的增益会有几个百分点的偏差，对齐回原电平，
    # 免得重采样过的片段在混排时忽大忽小
    r_in = float(np.sqrt(np.mean(np.asarray(data, dtype=np.float64) ** 2)))
    r_out = float(np.sqrt(np.mean(out.astype(np.float64) ** 2)))
    if r_out > 1e-9 and r_in > 1e-9:
        out = (out * (r_in / r_out)).astype(np.float32)
    return out, sr_out


def load_audio(path, target_sr=None):
    """读音频 -> (float64 单声道数组, 采样率)"""
    data, sr = sf.read(path)
    data = to_mono(data)
    if target_sr:
        data, sr = resample(data, sr, target_sr)
    return data.astype(np.float64), sr


def to_pcm16(data):
    """浮点样本 -> 16-bit 有符号小端 PCM 字节。

    必须转！pygame.mixer.Sound(buffer=...) 收的是【mixer 格式】的原始 PCM 字节，
    本项目 mixer 是 16-bit 有符号单声道。
    直接把 float32 的 tobytes() 塞进去，会被当成 int16 解释 ——
    采样点错位、幅度失真，听起来就是"全损音质"的噪声。
    """
    a = np.clip(np.asarray(data, dtype=np.float32), -1.0, 1.0)
    return (a * 32767.0).astype('<i2').tobytes()


def load_sound_bytes(path, target_sr=SAMPLE_RATE):
    """读音频 -> (16-bit PCM 字节, 采样率)，直接交给 pygame 播放"""
    data, sr = sf.read(path, dtype='float32')
    data = to_mono(data)
    data, sr = resample(data, sr, target_sr)
    return to_pcm16(data), sr


def verify_pcm_roundtrip(path, target_sr=SAMPLE_RATE):
    """自检：把送进 mixer 的字节解回来，和源文件逐样本比。

    返回 (最大误差, 是否通过)。这是防"把 float32 字节当 int16 送进 mixer"
    那类位深错位的护栏 —— 错位时程序不报任何错，只是声音变成噪声。
    """
    raw, sr = load_sound_bytes(path, target_sr)
    back = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32767.0
    src, _ = load_audio(path, target_sr=sr)
    src = np.clip(src, -1.0, 1.0)
    m = min(len(back), len(src))
    if m < 100:
        return 0.0, True
    err = float(np.max(np.abs(back[:m] - src[:m])))
    return err, err <= 1e-3


def save_audio(path, data, sr):
    """写音频（float32）"""
    sf.write(path, np.asarray(data, dtype='float32'), sr)


def peak_normalize(data, target=0.89):
    """峰值归一，防止削波"""
    peak = float(np.max(np.abs(data))) if len(data) else 0.0
    if peak <= 0:
        return data
    return data / peak * target
