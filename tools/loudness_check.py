# coding=utf-8
"""响度一致性：补齐音节与原包音节混排时，音量是否跳变。"""
import os
import sys

import numpy as np

from _common import ROOT, load_mono
sys.path.insert(0, ROOT)
from voice_reader import paths

PACK = paths.pack_dir('hanser')
GEN = os.path.join(PACK, '_generated')


def stats(name, arrs):
    pk = np.array([a[0] for a in arrs])
    rms = np.array([a[1] for a in arrs])
    print('  %-12s n=%-4d 峰值 中位 %.3f (p10 %.3f p90 %.3f)   RMS 中位 %.4f'
          % (name, len(arrs), np.median(pk), np.percentile(pk, 10),
             np.percentile(pk, 90), np.median(rms)))


def main():
    orig = []
    for f in os.listdir(PACK):
        if not f.endswith('.ogg'):
            continue
        x, sr = load_mono(os.path.join(PACK, f))
        orig.append((float(np.max(np.abs(x))), float(np.sqrt((x ** 2).mean()))))
    gen = []
    for f in os.listdir(GEN):
        if not f.endswith('.ogg'):
            continue
        x, sr = load_mono(os.path.join(GEN, f))
        gen.append((float(np.max(np.abs(x))), float(np.sqrt((x ** 2).mean()))))
    print('=== 响度分布 ===')
    stats('原包音节', orig)
    stats('补齐音节', gen)
    o = np.array([a[1] for a in orig])
    g = np.array([a[1] for a in gen])
    print()
    print('  RMS 比值(补齐/原包中位): %.2f  -> %s'
          % (np.median(g) / np.median(o),
             '偏响，混排时会跳' if abs(np.median(g) / np.median(o) - 1) > 0.15 else '基本一致'))


if __name__ == '__main__':
    main()
