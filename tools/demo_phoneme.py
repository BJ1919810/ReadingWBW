# coding=utf-8
"""音素层的 A/B 试听：同一段文本，关/开音素级补齐各渲染一次。"""
import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from voice_reader import paths                                  # noqa: E402
from voice_reader.assets import AssetIndex                     # noqa: E402
from voice_reader.pinyin_map import (PhraseIndex, load_wtv_map, load_overrides,
                                     convert_to_pinyin, detect_encoding)  # noqa: E402

OUT = os.path.join(paths.ROOT, 'demo', 'out')
SR = 48000
os.makedirs(OUT, exist_ok=True)


def render(text, use_phoneme, out_path):
    index = AssetIndex('hanser', use_phoneme=use_phoneme)
    wtv = load_wtv_map()
    ov = load_overrides()
    ph = PhraseIndex(index.phrases.keys())
    py = convert_to_pinyin(text, wtv, None, ov)
    chunks, miss, used = [], [], []
    for kind, key, alt in ph.iter_tokens(text, py, wtv):
        if kind == 'pause':
            chunks.append(np.zeros(int(SR * key)))
            continue
        if kind == 'phrase':
            path = index.phrase(key)
        else:
            path = index.syllable(key)
            if path is None and alt:
                path = index.syllable(alt)
            if path is None:
                miss.append(key)
            elif key in index.phoneme:
                used.append(key)
        if path is None:
            chunks.append(np.zeros(int(SR * 0.09)))
            continue
        data, _ = sf.read(path, dtype='float32')
        if data.ndim > 1:
            data = data.mean(axis=1)
        chunks.append(data.astype(np.float64))
    g = np.concatenate(chunks) if chunks else np.zeros(SR)
    peak = float(np.max(np.abs(g))) or 1.0
    sf.write(out_path, np.clip(g / peak * 0.89, -1, 1).astype(np.float32), SR)
    return miss, used


def pick_text():
    """挑一段音素层补齐用得最多的真实文本"""
    best = (0, None)
    for name in ['原神之可莉小矮砸.txt', '笑樱.txt']:
        p = os.path.join(paths.ROOT, name)
        if not os.path.exists(p):
            continue
        text, _ = detect_encoding(p)
        index = AssetIndex('hanser', use_phoneme=True)
        wtv = load_wtv_map()
        ov = load_overrides()
        ph = PhraseIndex(index.phrases.keys())
        for para in text.split('\n'):
            para = para.strip()
            if not (45 <= len(para) <= 110):
                continue
            py = convert_to_pinyin(para, wtv, None, ov)
            c = 0
            for kind, key, alt in ph.iter_tokens(para, py, wtv):
                if kind == 'char' and key in index.phoneme:
                    c += 1
            if c > best[0]:
                best = (c, para[:80])
            if best[0] >= 10:
                return best
    return best


def main():
    n, text = pick_text()
    print('选用段落（%d 个音素层补齐）：' % n)
    print('  %s' % text)
    m1, u1 = render(text, False, os.path.join(OUT, 'ph_A_off.wav'))
    m2, u2 = render(text, True, os.path.join(OUT, 'ph_B_on.wav'))
    print('  关音素层: 静默 %d 字 %s' % (len(m1), ''.join(m1)))
    print('  开音素层: 静默 %d 字 %s  (用上 %d 个音素补齐音节)'
          % (len(m2), ''.join(m2), len(u2)))
    print('  写出 ph_A_off.wav / ph_B_on.wav')


if __name__ == '__main__':
    main()
