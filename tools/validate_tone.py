# coding=utf-8
"""声调判定验证：合成结果的声调是否真的变成了目标声调。

关键对照：先把【原包真实录音】拿去分类，得到分类器自身的天花板。
孤立短音节 + F0 单一线索，本就有天花板；合成值接近天花板，
说明方法没有额外损失。
"""
import os
import sys

import numpy as np

from _common import ROOT  # noqa: F401
sys.path.insert(0, ROOT)
from voice_synth import (decompose, build_templates, synth_tone)   # noqa: E402
from voice_synth.tone_synth import (analyze_f0, voiced_rel,         # noqa: E402
                                     resample_to)
from voice_reader.audio_io import load_audio                        # noqa: E402
from voice_reader import paths                                      # noqa: E402


def classify(shape, templates):
    """用模板做最近质心，判断这个音节听上去是第几声"""
    best, bd = None, 1e9
    for t, tmpl in templates.items():
        d = float(np.linalg.norm(tmpl - shape))
        if d < bd:
            best, bd = t, d
    return best, bd


def shape_of(x, sr):
    f0 = analyze_f0(x, sr)
    rel, med = voiced_rel(f0)
    if rel is None:
        return None, None
    return resample_to(rel), med


def main():
    pdir = paths.pack_dir('hanser')
    templates, levels = build_templates(pdir)
    print('声调电平:', {k: round(v, 3) for k, v in levels.items()})

    # ---- 分类器天花板：原包真实录音（声调已知）----
    real_ok = real_tot = 0
    for f in sorted(os.listdir(pdir)):
        if not f.endswith('.ogg'):
            continue
        name = f[:-4]
        b, t = decompose(name)
        if t not in '1234':
            continue
        try:
            x, sr = load_audio(os.path.join(pdir, name + '.ogg'))
            shape, _ = shape_of(x, sr)
        except Exception:
            continue
        if shape is None:
            continue
        pred, _ = classify(shape, templates)
        real_tot += 1
        real_ok += (pred == t)
    print()
    print('=== 分类器天花板：原包真实录音 ===')
    print('  %d/%d = %.1f%%   <- 孤立短音节 + F0 单一线索的固有上限'
          % (real_ok, real_tot, 100.0 * real_ok / max(real_tot, 1)))

    print()
    print('=== 合成结果 ===')
    ok = tot = 0
    for src in ['lā', 'lǎ', 'māo', 'zhī', 'huī', 'jiāng', 'nǚ', 'shì', 'hǎo', 'tán']:
        p = os.path.join(pdir, src + '.ogg')
        if not os.path.exists(p):
            continue
        x, sr = load_audio(p)
        sb, st = decompose(src)
        for tgt in '1234':
            if tgt == st:
                continue
            y = synth_tone(x, sr, st, tgt, templates, levels)
            shape, med = shape_of(y, sr)
            if shape is None:
                continue
            pred, _ = classify(shape, templates)
            tot += 1
            hit = (pred == tgt)
            ok += hit
            print('  %s(%s) -> %s : 判定=%s %s'
                  % (src, st, tgt, pred, 'OK' if hit else 'MISS'))
    print()
    print('  合成声调判定正确率: %d/%d = %.1f%%' % (ok, tot, 100.0 * ok / max(tot, 1)))
    print('  对照上面的天花板 —— 接近即说明方法没有额外损失')


if __name__ == '__main__':
    main()
