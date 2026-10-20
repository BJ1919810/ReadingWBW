# coding=utf-8
"""单音节四声对照：[原]=原包录音  [补]=离线补齐"""
import os
import numpy as np
import soundfile as sf

from _common import ROOT  # noqa: F401  (导入即把项目根加入 sys.path)
from voice_reader import paths
from voice_reader.assets import AssetIndex
from voice_synth import decompose

OUT = os.path.join(paths.ROOT, 'demo', 'out')
SR = 48000
index = AssetIndex('hanser')

byb = {}
for h in list(index.syllables) + list(index.generated):
    b, t = decompose(h)
    if t in '1234':
        byb.setdefault(b, {})[t] = h

for base in ['yi', 'wu', 'hao', 'zhong', 'shi', 'niu']:
    tones = byb.get(base, {})
    if not tones:
        continue
    seq, labels = [], []
    for t in '1234':
        hit = tones.get(t)
        if hit:
            p = index.syllables.get(hit) or index.generated.get(hit)
            data, _ = sf.read(p, dtype='float32')
            if data.ndim > 1:
                data = data.mean(axis=1)
            seq.append(data.astype(np.float64))
            labels.append('%s[%s]' % (hit, '补' if hit in index.generated else '原'))
        else:
            labels.append('—')
    if not seq:
        continue
    g = np.concatenate([np.zeros(int(SR * 0.15))] +
                       [s for pair in zip(seq, [np.zeros(int(SR * 0.25))] * len(seq))
                        for s in pair])
    peak = float(np.max(np.abs(g))) or 1.0
    sf.write(os.path.join(OUT, 'tones_%s.wav' % base),
             np.clip(g / peak * 0.89, -1, 1).astype(np.float32), SR)
    print('  %-6s %s' % (base, ' | '.join(labels)))
