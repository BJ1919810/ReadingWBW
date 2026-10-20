# coding=utf-8
"""端到端验证：文本 -> 发音单元 -> 资源解析 -> 覆盖率 / 性能。"""
import os
import time
import collections

from _common import ROOT  # noqa: F401  (导入即把项目根加入 sys.path)
from voice_reader import paths
from voice_reader.assets import AssetIndex
from voice_reader.pinyin_map import (PhraseIndex, load_wtv_map, load_overrides,
                                      convert_to_pinyin, detect_encoding)

index = AssetIndex('hanser')
print('资源索引:', index.coverage())

phrases = PhraseIndex(index.phrases.keys())
print('词组数 %d，最长词组 %d 字' % (len(index.phrases), phrases.max_len))

wtv = load_wtv_map()
overrides = load_overrides()
print('自定义读音 %d 条: %s' % (len(overrides), ' '.join(overrides)))

for name in ['在崩铁里作死是不是搞错了什么？.txt', '笑樱.txt',
             '原神之可莉小矮砸.txt']:
    p = os.path.join(paths.ROOT, name)
    if not os.path.exists(p):
        continue
    text, enc = detect_encoding(p)
    t0 = time.time()
    py = convert_to_pinyin(text, wtv, None, overrides)
    t_py = time.time() - t0

    t0 = time.time()
    kinds = collections.Counter()
    hit = miss = recovered = 0
    missing = collections.Counter()
    n = 0
    for kind, key, alt in phrases.iter_tokens(text, py, wtv):
        kinds[kind] += 1
        n += 1
        if kind == 'char':
            if index.has(key):
                hit += 1
            elif alt and index.has(alt):
                recovered += 1
                missing[alt] += 1
            else:
                miss += 1
                missing[key] += 1
    t_seg = time.time() - t0

    print()
    print('%s  (%s, %d 字)' % (name, enc, len(text)))
    print('  转拼音 %.2fs | 切分+解析 %.3fs | 共 %d 个发音单元' % (t_py, t_seg, n))
    print('  单元构成: %s' % dict(kinds))
    if kinds['char']:
        tot = hit + recovered + miss
        print('  单字可播: %d 直接 + %d 备选 = %d/%d = %.1f%%  (完全缺失 %d 种)'
              % (hit, recovered, hit + recovered, tot,
                 100.0 * (hit + recovered) / tot, len(missing)))
        if missing:
            print('  仍缺失 top: %s' %
                  ' '.join('%s(%d)' % kv for kv in missing.most_common(12)))
