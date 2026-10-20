# coding=utf-8
"""清点"真正还差什么"：把剩余缺口按成因分类。"""
import os
import sys
import json
import pickle
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from voice_synth import decompose                       # noqa: E402
from voice_reader import paths                        # noqa: E402

pdir = paths.pack_dir('hanser')
have = {f[:-4] for f in os.listdir(pdir) if f.endswith('.ogg')}
gen = set(json.load(open(os.path.join(pdir, 'assets.json'),
                          encoding='utf-8'))['generated'])

with open(paths.WTV_DATA, 'rb') as f:
    raw = pickle.load(f)
need = {p[1:] for p in raw.split(',') if p and len(p) > 1}
weight = Counter()
for p in raw.split(','):
    if p and len(p) > 1:
        weight[p[1:]] += 1

# 每个 base 在包里有几声
base_tones = {}
for h in have:
    b, t = decompose(h)
    if t in '1234':
        base_tones.setdefault(b, set()).add(t)

missing = sorted(need - have - gen)
cat = {'整base缺失': [], 'base在但该声调未生成': [], '其他': []}
for m in missing:
    b, t = decompose(m)
    if b not in base_tones:
        cat['整base缺失'].append(m)
    elif t in base_tones[b]:
        cat['其他'].append(m)
    else:
        cat['base在但该声调未生成'].append(m)

tot = sum(weight.values())
print('需求拼音种类 %d   已覆盖 %d (%.1f%%)   未覆盖 %d'
      % (len(need), len(need) - len(missing),
         100.0 * (len(need) - len(missing)) / len(need), len(missing)))
print()
for k, v in cat.items():
    w = sum(weight[m] for m in v)
    print('  %-22s %4d 个拼音   字符权重 %5d (%.2f%%)' % (k, len(v), w, 100.0 * w / tot))
    if v:
        print('      ' + ' '.join(v[:28]))
print()
print('合计未覆盖字符权重: %d (%.2f%%)' %
      (sum(weight[m] for m in missing), 100.0 * sum(weight[m] for m in missing) / tot))
print()
print('=== 这 5 个 base 有轻声录音但没有四声 ===')
for b in ['de', 'le', 'me', 'ne', 'pu']:
    print('  %-4s 包内文件: %s' % (b, [h for h in sorted(have) if decompose(h)[0] == b]))
