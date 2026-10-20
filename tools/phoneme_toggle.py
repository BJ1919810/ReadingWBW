# coding=utf-8
"""音素层的开/关对比：确认回滚是真回滚（关掉就完全回到原状）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from voice_reader import paths                                  # noqa: E402
from voice_reader.assets import AssetIndex                     # noqa: E402
from voice_reader.pinyin_map import (PhraseIndex, load_wtv_map, load_overrides,
                                     convert_to_pinyin, detect_encoding)  # noqa: E402

NOVELS = ['原神之可莉小矮砸.txt', '笑樱.txt', '在崩铁里作死是不是搞错了什么？.txt']


def coverage(use_phoneme):
    idx = AssetIndex('hanser', use_phoneme=use_phoneme)
    wtv = load_wtv_map()
    ov = load_overrides()
    ph = PhraseIndex(idx.phrases.keys())
    out = []
    for name in NOVELS:
        p = os.path.join(paths.ROOT, name)
        if not os.path.exists(p):
            continue
        text, _ = detect_encoding(p)
        py = convert_to_pinyin(text, wtv, None, ov)
        hit = tot = 0
        for kind, key, alt in ph.iter_tokens(text, py, wtv):
            if kind != 'char':
                continue
            tot += 1
            if idx.has(key) or (alt and idx.has(alt)):
                hit += 1
        out.append((name[:8], hit, tot, 100.0 * hit / max(tot, 1)))
    return idx.coverage(), out


print('=== 关闭音素层（默认，当前行为）===')
cov_off, res_off = coverage(False)
print('  资源:', cov_off)
for n, h, t, pct in res_off:
    print('    %-10s %d/%d = %.1f%%' % (n, h, t, pct))

print()
print('=== 开启音素层（环境变量 READINGWBW_USE_PHONEME=1）===')
os.environ[paths.USE_PHONEME_ENV] = '1'
cov_on, res_on = coverage(None)
print('  资源:', cov_on)
for n, h, t, pct in res_on:
    print('    %-10s %d/%d = %.1f%%' % (n, h, t, pct))

print()
print('=== 提升 ===')
for (n, h0, t, p0), (_, h1, _, p1) in zip(res_off, res_on):
    print('    %-10s %.1f%% -> %.1f%%  (+%.1f%%)' % (n, p0, p1, p1 - p0))

print()
print('=== 回滚验证：把开关关掉，行为应与"关闭"完全一致 ===')
os.environ[paths.USE_PHONEME_ENV] = ''
cov_back, res_back = coverage(None)
same = (cov_back == cov_off and [r[1] for r in res_back] == [r[1] for r in res_off])
print('  资源:', cov_back)
print('  与关闭状态完全一致:', same)
