# coding=utf-8
"""构建音素级移植层。

    python tools/build_phoneme.py hanser
    python tools/build_phoneme.py hanser --dry-run

产出（与现有层完全隔离，删掉即回滚）：
    VoicesPackages/hanser/_generated_phoneme/*.ogg
    VoicesPackages/hanser/assets_phoneme.json

质量门槛：合成结果与"韵母 donor"的 MCD，必须不超过
"两个真实音节（韵母相同、声母不同）"的 1.3 倍 —— 即达到真人换一个声母的水平。
"""
import os
import sys
import json
import time
import pickle
import argparse
import logging

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_reader import paths                                  # noqa: E402
from voice_synth.phoneme import (DonorIndex, splice, split_pinyin,  # noqa: E402
                                 strip_tone)
from voice_synth.tone_synth import (build_templates, analyze_f0,  # noqa: E402
                                     voiced_rel, load_audio)
from voice_synth.vocoder import resynth                        # noqa: E402
from voice_synth.metrics import mcd                             # noqa: E402

log = logging.getLogger('build_phoneme')
QUALITY_FACTOR = 1.3      # 相对"真实同韵母不同声母"那一对的允许倍数


def get_donor_index(pack_dir):
    cache = os.path.join(paths.ensure_cache_dir() or '.', 'donor_index.pkl')
    if os.path.exists(cache):
        try:
            with open(cache, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    t0 = time.time()
    idx = DonorIndex(pack_dir)
    log.info('donor 索引构建 %.1fs', time.time() - t0)
    d = paths.ensure_cache_dir()
    if d:
        try:
            with open(cache, 'wb') as f:
                pickle.dump(idx, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            pass
    return idx


def apply_tone(y, sr, tone, templates, levels):
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


def real_pair_mcd(pack_dir, idx, final, sr):
    """同一韵母、不同声母的两个真实音节之间的 MCD —— 作为"真人水平"的标尺"""
    cands = idx.final_donors(final)
    if len(cands) < 2:
        return None
    a = cands[0]
    for b in cands[1:]:
        if b[1] != a[1]:
            try:
                x1, _ = load_audio(os.path.join(pack_dir, a[0] + '.ogg'))
                x2, _ = load_audio(os.path.join(pack_dir, b[0] + '.ogg'))
            except Exception:
                return None
            return mcd(x1, x2, sr)
    return None


def synth_one(task):
    """合成一个音素级音节。返回 (pinyin, ok, reason)"""
    pack_dir, pinyin, final, tone, templates, levels, idx, out_path = task
    py = strip_tone(pinyin)
    ini, fin = split_pinyin(py)
    r = splice(pack_dir, ini, fin, idx)
    if r is None:
        return pinyin, False, '无 donor (%s+%s)' % (ini or '零', fin)
    y, sr, di, df = r
    y2 = apply_tone(y, sr, tone, templates, levels)
    if y2 is None:
        return pinyin, False, '换调后无浊音帧'
    # 质量门槛
    try:
        xf, _ = load_audio(os.path.join(pack_dir, df + '.ogg'))
    except Exception:
        return pinyin, False, '韵母 donor 读不出'
    ref = apply_tone(xf, sr, tone, templates, levels)
    if ref is None:
        ref = xf
    our = mcd(ref, y2, sr)
    base = real_pair_mcd(pack_dir, idx, fin, sr)
    if base and our > base * QUALITY_FACTOR:
        return pinyin, False, '音色偏差 MCD %.0f > 真人 %.0f' % (our, base)
    if out_path:
        import soundfile as sf
        sf.write(out_path, y2.astype('float32'), sr)
    return pinyin, True, ''


def main():
    ap = argparse.ArgumentParser(description='构建音素级移植层')
    ap.add_argument('pack', nargs='?', default='hanser')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format='%(message)s')

    pack_dir = paths.pack_dir(args.pack)
    if not os.path.isdir(pack_dir):
        print('语音包不存在：%s' % pack_dir)
        return 1

    idx = get_donor_index(pack_dir)
    templates, levels = build_templates(pack_dir)
    if templates is None:
        print('声调模板构建失败')
        return 1

    have = {f[:-4] for f in os.listdir(pack_dir) if f.endswith('.ogg')}
    gen_file = os.path.join(pack_dir, paths.ASSET_MANIFEST)
    gen = set()
    if os.path.exists(gen_file):
        try:
            with open(gen_file, encoding='utf-8') as f:
                gen = set(json.load(f).get('generated', {}))
        except Exception:
            pass
    with open(paths.WTV_DATA, 'rb') as f:
        raw = pickle.load(f)
    need = {p[1:] for p in raw.split(',') if p and len(p) > 1}
    missing = sorted(need - have - gen)
    print('  现有覆盖之外还缺 %d 个拼音' % len(missing))

    out_dir = os.path.join(pack_dir, paths.PHONEME_DIR)
    if not args.dry_run:
        os.makedirs(out_dir, exist_ok=True)

    tasks = []
    for pinyin in missing:
        from voice_synth.tone_synth import decompose
        tone = decompose(pinyin)[1]
        if tone not in '1234':
            tone = '1'          # 轻声用一声代替，后面再派生
        final = split_pinyin(strip_tone(pinyin))[1]
        out = None if args.dry_run else os.path.join(out_dir, pinyin + '.ogg')
        tasks.append((pack_dir, pinyin, final, tone, templates, levels, idx, out))

    generated, failed = {}, []
    t0 = time.time()
    for i, task in enumerate(tasks, 1):
        pinyin, ok, why = synth_one(task)
        if ok:
            generated[pinyin] = '%s/%s.ogg' % (paths.PHONEME_DIR, pinyin)
        else:
            failed.append((pinyin, why))
        if not args.quiet and i % 25 == 0:
            print('    ... %d/%d' % (i, len(tasks)))
    dt = time.time() - t0
    print('  音素级补齐 %d 个，放弃 %d 个，用时 %.0fs'
          % (len(generated), len(failed), dt))
    if failed:
        print('  放弃明细（前 12）:')
        for p, w in failed[:12]:
            print('    %-8s %s' % (p, w))

    if not args.dry_run:
        manifest = {
            'pack': args.pack,
            'version': 1,
            'built_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'generated': generated,
            'stats': {
                '音素补齐': len(generated),
                '放弃': len(failed),
                '质量门槛': 'MCD <= 真人同韵母对 x%.1f' % QUALITY_FACTOR,
            },
        }
        with open(os.path.join(pack_dir, paths.PHONEME_MANIFEST),
                  'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        print('  已写入 %s' % paths.PHONEME_MANIFEST)
    return 0


if __name__ == '__main__':
    sys.exit(main())
