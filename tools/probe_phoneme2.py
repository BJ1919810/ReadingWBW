# coding=utf-8
"""音素级移植：用"同为真实音节、韵母相同声母不同"的那一对做标尺。

    真实对：MCD("chéng", "méng")   —— 两个都是真人音节，只差声母
    我们的：MCD("bèng", "chéng")   —— 差一个声母（/b/ vs /ch/）

如果两者的 MCD 接近，说明我们的拼接达到了"真人换一个声母"的水平。
"""
import os
import sys
import pickle

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from voice_reader import paths                                  # noqa: E402
from voice_synth.phoneme import splice, split_pinyin, strip_tone  # noqa: E402
from voice_synth.tone_synth import build_templates, analyze_f0, voiced_rel, load_audio  # noqa: E402
from voice_synth.vocoder import resynth                        # noqa: E402
from voice_synth.metrics import mcd                            # noqa: E402

PACK = paths.pack_dir('hanser')
idx = pickle.load(open(os.path.join(paths.ensure_cache_dir(),
                                    'donor_index.pkl'), 'rb'))
templates, levels = build_templates(PACK)


def apply_tone(y, sr, tone):
    f0 = analyze_f0(y, sr)
    rel, med = voiced_rel(f0)
    if rel is None:
        return None
    shape = templates[tone]
    sg = np.interp(np.linspace(0, len(shape) - 1, len(f0)),
                   np.arange(len(shape)), shape)
    center = med / max(levels.get(tone, 1.0), 1e-6) * levels[tone]
    f0_t = center * np.power(2.0, sg / 12.0)
    f0_t[f0 <= 0] = 0
    return resynth(y, sr, f0_t)


def real_pair_for(final):
    """找两个真实音节：韵母相同、声母不同。返回 (名1, 名2)"""
    cands = idx.final_donors(final)
    if len(cands) < 2:
        return None
    a = cands[0]
    for b in cands[1:]:
        if b[1] != a[1]:
            return a[0], b[0]
    return None


print('%-8s %-6s %-7s | %9s %9s | %s'
      % ('目标', '声母donor', '韵母donor', '我们MCD', '真实对MCD', '判定'))
print('-' * 72)
for m in ['be', 'bèng', 'bìn', 'néng', 'rán', 'tuán', 'gěi', 'shén', 'dé', 'lóng']:
    py = strip_tone(m)
    ini, fin = split_pinyin(py)
    r = splice(PACK, ini, fin, idx)
    if r is None:
        print('%-8s  无 donor' % m)
        continue
    y, sr, di, df = r
    tone = '2'
    y2 = apply_tone(y, sr, tone)
    if y2 is None:
        print('%-8s  换调失败' % m)
        continue
    xf, _ = load_audio(os.path.join(PACK, df + '.ogg'))
    ref = apply_tone(xf, sr, tone)
    if ref is None:
        ref = xf
    our = mcd(ref, y2, sr)
    pair = real_pair_for(fin)
    if pair:
        x1, _ = load_audio(os.path.join(PACK, pair[0] + '.ogg'))
        x2, _ = load_audio(os.path.join(PACK, pair[1] + '.ogg'))
        real = mcd(x1, x2, sr)
        judge = 'OK' if our <= real * 1.3 else '偏差'
        print('%-8s %-6s %-7s | %9.1f %9.1f | %s (真实对 %s/%s)'
              % (m, di, df, our, real, judge, pair[0], pair[1]))
    else:
        print('%-8s %-6s %-7s | %9.1f %9s | 无同韵母真实对'
              % (m, di, df, our, '-'))
print()
print('判定：我们的 MCD <= 真实对的 1.3 倍即算达到真人水平')
