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


def resample(data, sr_in, sr_out):
    """线性重采样。素材都是 48k，通常是空操作。"""
    if sr_in == sr_out or len(data) == 0:
        return data, sr_in
    n_out = int(len(data) * sr_out / sr_in)
    if n_out <= 0:
        return data, sr_in
    out = np.interp(np.linspace(0, len(data) - 1, n_out),
                    np.arange(len(data)), data).astype('float32')
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
