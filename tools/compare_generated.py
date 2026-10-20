# coding=utf-8
"""生成音节 vs 其源录音的逐项对比，找出最差的一批。"""
import os
import numpy as np

from _common import ROOT  # noqa: F401  (导入即把项目根加入 sys.path)
from voice_synth import decompose
from voice_reader.audio_io import load_audio
from voice_synth.tone_synth import analyze_f0
from voice_reader import paths
from voice_synth.metrics import hf_ratio

pdir = paths.pack_dir('hanser')
gen = os.path.join(pdir, '_generated')
have = {f[:-4] for f in os.listdir(pdir) if f.endswith('.ogg')}
byb = {}
for h in have:
    b, t = decompose(h)
    if t in '1234':
        byb.setdefault(b, {})[t] = h

rows = []
for f in sorted(os.listdir(gen)):
    if not f.endswith('.ogg'):
        continue
    name = f[:-4]
    b, t = decompose(name)
    srcs = byb.get(b, {})
    if not srcs:
        rows.append((999, name, 'no-source', 0, 0, 0, 0))
        continue
    src = srcs[sorted(srcs)[0]]
    x, sr = load_audio(os.path.join(gen, name + '.ogg'))
    xs, _ = load_audio(os.path.join(pdir, src + '.ogg'))
    f0 = analyze_f0(x, sr)
    v = f0[f0 > 0]
    nf = hf_ratio(x, sr)
    nfs = hf_ratio(xs, sr)
    rows.append((nf - nfs, name, src, nf, nfs, len(x) / sr, len(v)))

rows.sort(reverse=True)
print('最差的 12 个（噪声底增量最大）：')
for d, name, src, nf, nfs, dur, nv in rows[:12]:
    print('  %-8s <- %-8s 噪声底 %.4f (源 %.4f, +%.4f)  时长 %.0fms  浊音帧 %d'
          % (name, src, nf, nfs, d, dur * 1000, nv))
print()
deltas = [r[0] for r in rows if r[2] != 'no-source']
print('噪声底增量: 均值 %+.4f  中位 %+.4f  最小 %+.4f  最大 %+.4f'
      % (np.mean(deltas), np.median(deltas), min(deltas), max(deltas)))
print('浊音帧为 0 的生成音节: %d 个' % sum(1 for r in rows if r[6] == 0))
print('  ->', [r[1] for r in rows if r[6] == 0][:20])
print('时长 < 100ms 的: %d 个' % sum(1 for r in rows if r[5] < 0.1))
