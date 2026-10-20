# coding=utf-8
"""生成 A/B 试听：同一批补齐音节，PSOLA 版 vs 声码器版。

用户反馈"hao 二声有电音" —— 这里直接把两种后端的同一音节并排放出来，
让人耳直接判别哪个干净。
"""
import os
import sys

from _common import ROOT, concat, write_wav
sys.path.insert(0, ROOT)
from voice_synth import build_templates, synth_tone, decompose   # noqa: E402
from voice_reader.audio_io import load_audio                    # noqa: E402
from voice_reader import paths                                  # noqa: E402

PACK = paths.pack_dir('hanser')
OUT = os.path.join(ROOT, 'demo', 'out')
os.makedirs(OUT, exist_ok=True)
SR = 48000
T, L = build_templates(PACK)

CASES = [('hāo', '2'), ('hāo', '3'), ('hāo', '4'),
         ('lā', '2'), ('yī', '3'), ('shì', '1'), ('tán', '4')]


def main():
    print('=== 同一音节：PSOLA 版 vs 声码器版 ===')
    psola_clips, voc_clips, ref_clips = [], [], []
    labels = []
    for src, tgt in CASES:
        p = os.path.join(PACK, src + '.ogg')
        if not os.path.exists(p):
            continue
        x, sr = load_audio(p)
        st = decompose(src)[1]
        yp = synth_tone(x, sr, st, tgt, T, L, backend='psola')
        yv = synth_tone(x, sr, st, tgt, T, L, backend='vocoder')
        psola_clips.append(yp)
        voc_clips.append(yv)
        ref_clips.append(x)
        labels.append('%s->t%s' % (src, tgt))
        print('  %-12s 已生成' % labels[-1])

    if not psola_clips:
        print('没有可对比的样本')
        return
    for tag, clips in [('backend_psola', psola_clips),
                       ('backend_vocoder', voc_clips),
                       ('source_ref', ref_clips)]:
        g = concat(clips, gap=0.28, lead=0.12, sr=SR)
        write_wav(os.path.join(OUT, 'ab_%s.wav' % tag), g, SR)
        print('  写出 ab_%s.wav  (%.1fs)' % (tag, len(g) / SR))
    print()
    print('  顺序: ' + ' | '.join(labels))
    print('  三段是同一组音节：PSOLA 版 / 声码器版 / 原始源音节')


if __name__ == '__main__':
    main()
