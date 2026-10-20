# coding=utf-8
"""覆盖率拆解：带调 vs 轻声。"""
import os, pickle
from collections import defaultdict, Counter

from _common import ROOT  # noqa: F401  (导入即把项目根加入 sys.path)
from voice_synth import decompose
from voice_reader import paths

pdir = paths.pack_dir('hanser')
have = {f[:-4] for f in os.listdir(pdir) if f.endswith('.ogg')}
with open(paths.WTV_DATA, 'rb') as f:
    py = pickle.load(f)
need = {p[1:] for p in py.split(',') if p and len(p) > 1}
w = Counter()
for p in py.split(','):
    if p and len(p) > 1:
        w[p[1:]] += 1
tot = sum(w.values())

toned = [m for m in need if decompose(m)[1] in '1234']
neutral = [m for m in need if decompose(m)[1] == '0']

byb = defaultdict(set)
for h in have:
    b, t = decompose(h)
    if t in '1234':
        byb[b].add(h)


def rescuable(m):
    b, t = decompose(m)
    if t == '0':
        return bool(byb.get(b))
    return any(decompose(s)[0] == b for s in byb.get(b, ()))


missing = need - have
rt = [m for m in toned if m in missing and rescuable(m)]
rn = [m for m in neutral if m in missing and rescuable(m)]
covered = sum(w[m] for m in need & have)

print('need=%d  带调=%d  无声调(轻声)=%d' % (len(need), len(toned), len(neutral)))
print('已有覆盖:      %7d 字符 (%.1f%%)' % (covered, 100 * covered / tot))
print('带调可补:      %7d 字符 (%.1f%%)   %d 个拼音' %
      (sum(w[m] for m in rt), 100 * sum(w[m] for m in rt) / tot, len(rt)))
print('轻声可补:      %7d 字符 (%.1f%%)   %d 个拼音' %
      (sum(w[m] for m in rn), 100 * sum(w[m] for m in rn) / tot, len(rn)))
print('补齐后总覆盖:  %7d 字符 (%.1f%%)' %
      (covered + sum(w[m] for m in rt) + sum(w[m] for m in rn),
       100 * (covered + sum(w[m] for m in rt) + sum(w[m] for m in rn)) / tot))
print()
print('轻声里最高频的:', ' '.join('%s(%d)' % (m, w[m])
                                for m in sorted(neutral, key=lambda x: -w[x])[:15]))
