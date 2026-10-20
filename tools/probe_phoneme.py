# coding=utf-8
"""音素级移植的可行性验证：能拼出多少、音色像不像。"""
import os
import sys
import time
import pickle

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from voice_reader import paths                                  # noqa: E402
from voice_synth.phoneme import DonorIndex, splice, split_pinyin, strip_tone  # noqa: E402
from voice_synth.tone_synth import (build_templates, analyze_f0,  # noqa: E402
                                     voiced_rel, load_audio)
from voice_synth.vocoder import resynth                        # noqa: E402
from voice_synth.metrics import mcd, ltas_dist                  # noqa: E402

PACK = paths.pack_dir('hanser')
OUT = os.path.join(paths.ROOT, 'demo', 'out')
os.makedirs(OUT, exist_ok=True)


def get_index():
    cache = os.path.join(paths.ensure_cache_dir() or '.', 'donor_index.pkl')
    if os.path.exists(cache):
        try:
            with open(cache, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    t0 = time.time()
    idx = DonorIndex(PACK)
    print('donor 索引构建 %.1fs：%d 个韵母类别，%d 个声母类别'
          % (time.time() - t0, len(idx.by_final), len(idx.by_initial)))
    d = paths.ensure_cache_dir()
    if d:
        try:
            with open(cache, 'wb') as f:
                pickle.dump(idx, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            pass
    return idx


def apply_tone(y, sr, tone, templates, levels):
    """把一段音频的基频轮廓换成指定声调"""
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


def main():
    idx = get_index()
    templates, levels = build_templates(PACK)

    # 目标：整个 base 在包里不存在的那些
    import json
    from voice_synth import decompose
    have = {f[:-4] for f in os.listdir(PACK) if f.endswith('.ogg')}
    with open(paths.WTV_DATA, 'rb') as f:
        raw = pickle.load(f)
    need = {p[1:] for p in raw.split(',') if p and len(p) > 1}
    gen = set(json.load(open(os.path.join(PACK, 'assets.json'),
                            encoding='utf-8'))['generated'])
    missing = sorted(need - have - gen)

    print()
    print('待补 %d 个拼音，先试 8 个' % len(missing))
    print('（MCD 参照：把韵母 donor 也做同样的声调替换后比，差异只剩声母）')
    for m in missing[:8]:
        py = strip_tone(m)
        ini, fin = split_pinyin(py)
        r = splice(PACK, ini, fin, idx)
        if r is None:
            print('  %-8s (%s+%s)  无可用 donor' % (m, ini or '零', fin))
            continue
        y, sr, di, df = r
        tone = decompose(m)[1]
        y2 = apply_tone(y, sr, tone if tone in '1234' else '2',
                        templates, levels)
        if y2 is None:
            print('  %-8s 拼接后无浊音帧' % m)
            continue
        # 同口径参照：韵母 donor 也换成同样的声调
        xf, _ = load_audio(os.path.join(PACK, df + '.ogg'))
        ref = apply_tone(xf, sr, tone if tone in '1234' else '2', templates, levels)
        if ref is None:
            ref = xf
        d_mcd = mcd(ref, y2, sr)
        d_ltas = ltas_dist(ref, y2, sr)
        import soundfile as sf
        sf.write(os.path.join(OUT, 'ph_%s.wav' % m), y2.astype('float32'), sr)
        sf.write(os.path.join(OUT, 'phref_%s.wav' % m), ref.astype('float32'), sr)
        print('  %-8s (%s+%s) 声母<-%-6s 韵母<-%-6s  MCD %5.1f  长时谱差 %5.1f'
              % (m, ini or '零', fin, di, df, d_mcd, d_ltas))

    print()
    print('=== 覆盖率潜力 ===')
    ok = 0
    for m in missing:
        py = strip_tone(m)
        ini, fin = split_pinyin(py)
        if not fin or not idx.final_donors(fin):
            continue
        if ini and not idx.initial_donors(ini):
            continue
        ok += 1
    print('  %d/%d 个缺失拼音有可用 donor（%.0f%%）' % (ok, len(missing), 100.0 * ok / max(len(missing), 1)))


if __name__ == '__main__':
    main()
