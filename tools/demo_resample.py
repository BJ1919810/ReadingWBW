# coding=utf-8
"""A/B：线性插值 vs 带限 sinc 重采样的听感对比。

两者音高/时长都相同，差别只在高频"空气感"：
线性插值把 11~22kHz 削掉 3~6dB -> 声音变薄 -> 听感"尖细"。
"""
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from voice_reader import paths                                  # noqa: E402
from voice_reader.audio_io import load_audio, to_pcm16, to_mono  # noqa: E402
from voice_reader.assets import AssetIndex                    # noqa: E402
from voice_reader.pinyin_map import (PhraseIndex, load_wtv_map,  # noqa: E402
                                     load_overrides, convert_to_pinyin,
                                     detect_encoding)

OUT = os.path.join(paths.ROOT, 'demo', 'out')
os.makedirs(OUT, exist_ok=True)
SR = 48000


def linear_resample(data, sr_in, sr_out):
    if sr_in == sr_out or len(data) == 0:
        return data
    n_out = int(len(data) * sr_out / sr_in)
    if n_out <= 0:
        return data
    return np.interp(np.linspace(0, len(data) - 1, n_out),
                     np.arange(len(data)), data).astype('float32')


def render(text, resampler, out_path):
    index = AssetIndex('hanser')
    wtv = load_wtv_map()
    ov = load_overrides()
    ph = PhraseIndex(index.phrases.keys())
    py = convert_to_pinyin(text, wtv, None, ov)
    chunks = []
    for kind, key, alt in ph.iter_tokens(text, py, wtv):
        if kind == 'pause':
            chunks.append(np.zeros(int(SR * key)))
            continue
        path = index.phrase(key) if kind == 'phrase' else index.syllable(key)
        if path is None and kind == 'char' and alt:
            path = index.syllable(alt)
        if path is None:
            chunks.append(np.zeros(int(SR * 0.09)))
            continue
        data, sr = load_audio(path)
        data = to_mono(data)
        if sr != SR:
            data = resampler(data, sr, SR)
        chunks.append(np.asarray(data, dtype=np.float64))
    g = np.concatenate(chunks)
    peak = float(np.max(np.abs(g))) or 1.0
    sf.write(out_path, np.clip(g / peak * 0.89, -1, 1).astype(np.float32), SR)
    return g


def main():
    # 挑一段用到 44.1k 片段较多的真实文本
    index = AssetIndex('hanser')
    wtv = load_wtv_map()
    ov = load_overrides()
    ph = PhraseIndex(index.phrases.keys())
    import soundfile as sf
    rates = {}
    pdir = paths.pack_dir('hanser')
    for f in os.listdir(pdir):
        if f.endswith('.ogg'):
            rates[f[:-4]] = sf.info(os.path.join(pdir, f)).samplerate
    best = (0, None)
    for name in ['原神之可莉小矮砸.txt', '笑樱.txt']:
        p = os.path.join(paths.ROOT, name)
        if not os.path.exists(p):
            continue
        text, _ = detect_encoding(p)
        for para in text.split('\n'):
            para = para.strip()
            if not (45 <= len(para) <= 100):
                continue
            py = convert_to_pinyin(para, wtv, None, ov)
            c = 0
            for kind, key, alt in ph.iter_tokens(para, py, wtv):
                if kind == 'char' and rates.get(key) == 44100:
                    c += 1
            if c > best[0]:
                best = (c, para[:80])
            if best[0] >= 8:
                break
    n, text = best
    print('选用段落（%d 个 44.1k 片段）：' % n)
    print('  %s' % text)
    a = render(text, linear_resample, os.path.join(OUT, 'rs_A_linear.wav'))
    b = render(text, _sinc_wrap, os.path.join(OUT, 'rs_B_sinc.wav'))
    print('  A 线性插值 -> rs_A_linear.wav')
    print('  B 带限sinc -> rs_B_sinc.wav')
    # 量化差异
    m = min(len(a), len(b))
    d = np.abs(a[:m] - b[:m])
    print('  两者最大差 %.4f  RMS 差 %.5f' % (d.max(), np.sqrt((d ** 2).mean())))


def _sinc_wrap(data, sr_in, sr_out):
    from voice_reader.audio_io import resample
    return resample(data, sr_in, sr_out)[0]


if __name__ == '__main__':
    main()
