# coding=utf-8
"""融合度评估：补齐音节是否还是"同一个声音"。

用 MCD（mel 倒谱失真）——只比声道包络（音色），对变调引起的谐波位移不敏感，
也不会被电平差干扰。

标尺：
  x vs x        = 0
  x vs x*0.5    = 0（对电平不敏感）
  同一音节换声调 = 变调的固有代价（物理上无法为零）
  不同音节      = 音色的自然差距
"""
import os
import sys

import numpy as np

from _common import ROOT, load_mono
sys.path.insert(0, ROOT)
from voice_synth.metrics import mcd, ltas_dist, hf_ratio     # noqa: E402
from voice_synth import decompose                           # noqa: E402
from voice_reader import paths                              # noqa: E402

PACK = paths.pack_dir('hanser')
GEN = os.path.join(PACK, '_generated')


def main():
    files = {n[:-4]: os.path.join(PACK, n) for n in os.listdir(PACK)
             if n.endswith('.ogg') and os.path.isfile(os.path.join(PACK, n))}
    x, sr = load_mono(files['hāo'])
    y, _ = load_mono(files['māo'])
    print('=== 标尺 ===')
    print('  x vs x          : %6.2f dB  (应 0)' % mcd(x, x, sr))
    print('  x vs x*0.5      : %6.2f dB  (应≈0)' % mcd(x, x * 0.5, sr))
    print('  hāo vs māo      : %6.2f dB  <- 不同音节的音色差距' % mcd(x, y, sr))

    have = set(files)
    byb = {}
    for h in have:
        b, t = decompose(h)
        if t in '1234':
            byb.setdefault(b, {})[t] = h

    print()
    print('=== 补齐音节 vs 源录音 ===')
    mcds, lt, nf = [], [], []
    for f in sorted(os.listdir(GEN)):
        if not f.endswith('.ogg'):
            continue
        name = f[:-4]
        b, t = decompose(name)
        srcs = byb.get(b, {})
        if not srcs:
            continue
        src = srcs[sorted(srcs)[0]]
        g, gsr = load_mono(os.path.join(GEN, name + '.ogg'))
        s, ssr = load_mono(files[src])
        m = mcd(s, g, ssr)
        if m == m:
            mcds.append(m)
        lt.append(ltas_dist(s, g, ssr))
        nf.append(hf_ratio(g, gsr))
    if not mcds:
        print('  没有可评的样本')
        return
    mcds = np.array(mcds)
    print('  样本 %d 个' % len(mcds))
    print('  MCD      均值 %5.2f  中位 %5.2f  90分位 %5.2f  最大 %5.2f'
          % (mcds.mean(), np.median(mcds), np.percentile(mcds, 90), mcds.max()))
    print('  长时谱差 均值 %5.2f  (参考：不同音节间约 6~19dB)' % np.mean(lt))
    print('  噪声底   均值 %.4f  (原包音节约 0.037)' % np.mean(nf))
    print()
    print('  判据：MCD 中位数应远小于"不同音节"的差距(%s dB)'
          % ('%.1f' % mcd(x, y, sr)))


if __name__ == '__main__':
    main()
