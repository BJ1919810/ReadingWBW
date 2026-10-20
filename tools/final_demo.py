# coding=utf-8
"""最终试听：挑补齐音节最多的真实段落 + 纯合成音节串。"""
import os
import numpy as np
import soundfile as sf

from _common import ROOT  # noqa: F401  (导入即把项目根加入 sys.path)
from voice_reader import paths
from voice_reader.assets import AssetIndex
from voice_reader.pinyin_map import (PhraseIndex, load_wtv_map, load_overrides,
                                      convert_to_pinyin, detect_encoding)

OUT = os.path.join(paths.ROOT, 'demo', 'out')
os.makedirs(OUT, exist_ok=True)
SR = 48000

index = AssetIndex('hanser')
phrases = PhraseIndex(index.phrases.keys())
wtv = load_wtv_map()
overrides = load_overrides()
GEN = set(index.generated)


def build(text, use_generated, out_path):
    py = convert_to_pinyin(text, wtv, None, overrides)
    chunks, miss, gen_used = [], [], []
    for kind, key, alt in phrases.iter_tokens(text, py, wtv):
        if kind == 'pause':
            chunks.append(np.zeros(int(SR * key)))
            continue
        if kind == 'phrase':
            path = index.phrase(key)
        else:
            if use_generated:
                path = index.syllable(key)
                if path is None and alt:
                    path = index.syllable(alt)
                if path is None:
                    miss.append(key)
                elif key in GEN:
                    gen_used.append(key)
            else:
                # A 版只用原包录音，补齐的一律当没有
                path = index.syllables.get(key)
                if path is None:
                    miss.append(key)
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
    return miss, gen_used, len(g) / SR


def pick_paragraph():
    """从小说里挑补齐音节最多的段落"""
    best = (0, None)
    for name in ['原神之可莉小矮砸.txt', '笑樱.txt', '这不可能是我妹妹.txt']:
        p = os.path.join(paths.ROOT, name)
        if not os.path.exists(p):
            continue
        text, _ = detect_encoding(p)
        for para in text.split('\n'):
            para = para.strip()
            if not (40 <= len(para) <= 110):
                continue
            py = convert_to_pinyin(para, wtv, None, overrides)
            c = 0
            for kind, key, alt in phrases.iter_tokens(para, py, wtv):
                if kind == 'char' and key in GEN:
                    c += 1
            if c > best[0]:
                best = (c, para[:80])
            if best[0] >= 12:
                return best
    return best


def main():
    print('资源:', index.coverage())
    n, para = pick_paragraph()
    print('补齐音节最多的段落 (%d 个补齐音节):' % n)
    print('  ', para)
    m1, g1, d1 = build(para, False, os.path.join(OUT, 'ab_A_original.wav'))
    m2, g2, d2 = build(para, True, os.path.join(OUT, 'ab_B_enhanced.wav'))
    print('  A 原包   : %5.1fs  静默 %2d 字  %s' % (d1, len(m1), ''.join(m1)))
    print('  B 补齐后 : %5.1fs  静默 %2d 字  %s   (用了 %d 个补齐音节)'
          % (d2, len(m2), ''.join(m2), len(g2)))

    # 纯合成音节串：只放补齐出来的音节
    print()
    print('=== 纯合成音节串（全部是离线补齐的）===')
    pick = ['yǐ', 'wú', 'háo', 'guǎn', 'chuān', 'shén', 'zǐ', 'rán', 'lín', 'néng']
    avail = [p for p in pick if p in GEN]
    seq = []
    for p in avail:
        data, _ = sf.read(index.generated[p], dtype='float32')
        if data.ndim > 1:
            data = data.mean(axis=1)
        seq.append(data.astype(np.float64))
    if seq:
        g = np.concatenate([np.zeros(int(SR * 0.18))] +
                           [s for pair in zip(seq, [np.zeros(int(SR * 0.25))] * len(seq))
                            for s in pair])
        peak = float(np.max(np.abs(g))) or 1.0
        sf.write(os.path.join(OUT, 'synth_only.wav'),
                 np.clip(g / peak * 0.89, -1, 1).astype(np.float32), SR)
        print('  %s  -> synth_only.wav' % ' | '.join(avail))
    missing = [p for p in pick if p not in GEN]
    if missing:
        print('  (未生成: %s)' % ' '.join(missing))

    print()
    for f in sorted(os.listdir(OUT)):
        if f.endswith('.wav'):
            print('   %-28s %6.0f KB' % (f, os.path.getsize(os.path.join(OUT, f)) / 1024))


if __name__ == '__main__':
    main()
