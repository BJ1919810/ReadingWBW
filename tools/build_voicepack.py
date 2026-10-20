# coding=utf-8
"""离线构建工具：为语音包补齐缺失的声调。

用法：
    python tools/build_voicepack.py hanser
    python tools/build_voicepack.py hanser --dry-run

产出（不改动原包任何文件）：
    VoicesPackages/hanser/_generated/<拼音>.ogg   补齐的音节
    VoicesPackages/hanser/assets.json            补齐清单 + 覆盖率统计
"""
import os
import sys
import json
import time
import pickle
import argparse
import logging

from _common import ROOT  # noqa: F401  (导入即把项目根加入 sys.path)

from voice_reader import paths
from voice_synth import (decompose, compose, build_templates,
                       synth_tone, synth_neutral, validate_syllable)
from voice_reader.audio_io import load_audio

log = logging.getLogger('build_voicepack')
import re
PY_RE = re.compile(r'^[a-zü]+$')


def needed_pinyin():
    """朗读时真正需要的声音集合。

    注意：运行时用的是 pypinyin（多音字按上下文选读音），
    而 WTV.data 只是一张单字表，两者读音并不一致 ——
    例如 WTV 里 馆->guān，pypinyin 读 guǎn。
    所以需求集 = WTV.data 的读音 ∪ 项目文本里各字的所有读音（heteronym）。
    """
    need = set()
    if os.path.exists(paths.WTV_DATA):
        with open(paths.WTV_DATA, 'rb') as f:
            raw = pickle.load(f)
        need |= {p[1:] for p in raw.split(',') if p and len(p) > 1}

    chars = set()
    # 全量汉字（来自 WTV.data 的字表），而不只是现有 txt 里出现过的
    if os.path.exists(paths.WTV_DATA):
        with open(paths.WTV_DATA, 'rb') as f:
            raw = pickle.load(f)
        chars |= {p[0] for p in raw.split(',') if p}
    for name in os.listdir(paths.ROOT):
        if not name.lower().endswith('.txt'):
            continue
        try:
            with open(os.path.join(paths.ROOT, name), 'r',
                      encoding='utf-8-sig', errors='ignore') as f:
                text = f.read()
        except OSError:
            continue
        chars |= {c for c in text if '一' <= c <= '鿿'}

    if chars:
        try:
            from pypinyin import pinyin, Style
            ordered = sorted(chars)
            res = pinyin(ordered, style=Style.TONE, heteronym=True,
                         errors=lambda x: x)
            for item in res:
                for py in (item if isinstance(item, list) else [item]):
                    if py and py not in need:
                        need.add(py)
        except Exception as exc:
            log.warning('pypinyin 读音收集失败：%s', exc)
    return need


def build_base_index(pdir):
    """基础音节 -> {声调序号: 录音文件名}，只收合法拼音"""
    idx = {}
    for f in os.listdir(pdir):
        if not f.endswith('.ogg'):
            continue
        name = f[:-4]
        b, t = decompose(name)
        if t in '1234' and PY_RE.match(b):
            idx.setdefault(b, {}).setdefault(t, name)
    return idx


def _synth_one(args):
    """合成单个音节。返回 (pinyin, ok, reason)。

    模块级函数：Windows 上 multiprocessing 需要可 pickle 的顶层函数。
    """
    pdir, pinyin, src, src_tone, tone, kind, templates, levels, out_path = args
    try:
        x, sr = load_audio(os.path.join(pdir, src + '.ogg'))
        if kind == 'neutral':
            y = synth_neutral(x, sr)
        else:
            y = synth_tone(x, sr, src_tone, tone, templates, levels)
    except Exception as exc:
        return pinyin, False, '%s:%s' % (src, exc)
    good, why = validate_syllable(y, sr, x)
    if not good:
        return pinyin, False, '%s:%s' % (src, why)
    if out_path:
        import soundfile as sf
        sf.write(out_path, y.astype('float32'), sr)
        # 写盘后回读校验：保证交付的每个文件都真的可用
        back, bsr = load_audio(out_path)
        ok2, why2 = validate_syllable(back, bsr, x)
        if not ok2:
            os.remove(out_path)
            return pinyin, False, '%s:回读校验失败(%s)' % (src, why2)
    return pinyin, True, ''


def _synth_base(task):
    """一个基础音节的全部目标。任务级并行：每个 base 一个任务。"""
    pdir, base, items, tones, templates, levels, gen_dir, dry = task
    out = []
    for pinyin, tone, kind in items:
        reasons = []
        done = False
        for src_tone in sorted(tones):
            src = tones[src_tone]
            out_path = None if dry else os.path.join(gen_dir, pinyin + '.ogg')
            pin, ok, why = _synth_one((pdir, pinyin, src, src_tone, tone, kind,
                                       templates, levels, out_path))
            if ok:
                out.append((pinyin, True, ''))
                done = True
                break
            reasons.append(why)
        if not done:
            out.append((pinyin, False, '; '.join(reasons[:2])))
    return out


def main():
    ap = argparse.ArgumentParser(description='为语音包补齐缺失声调')
    ap.add_argument('pack', nargs='?', help='语音包名（默认全部）')
    ap.add_argument('--dry-run', action='store_true', help='只报告不写文件')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--jobs', '-j', type=int, default=0,
                    help='并行进程数（0=自动，按 CPU 核数）')
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format='%(message)s')

    packs = [args.pack] if args.pack else paths.available_packs()
    if not packs:
        print('没有找到可用语音包')
        return 1

    need = needed_pinyin()
    overall_ok = True

    for pack in packs:
        pdir = paths.pack_dir(pack)
        if not os.path.isdir(pdir):
            print('跳过 %s：目录不存在' % pack)
            continue
        print('=' * 68)
        print('语音包：%s' % pack)

        have = {f[:-4] for f in os.listdir(pdir) if f.endswith('.ogg')}
        by_base = build_base_index(pdir)

        print('  原有音节 %d 个 / 可用基础音节 %d 个' % (len(have), len(by_base)))

        tpl_cache = os.path.join(paths.ensure_cache_dir() or '.',
                                 'templates_%s.pkl' % pack)
        templates, levels = build_templates(pdir, cache_path=tpl_cache)
        if templates is None:
            print('  声调模板构建失败（可能四个声调的样本不全），跳过')
            overall_ok = False
            continue
        print('  声调电平: ' + '  '.join('tone%s=%.3f' % (t, levels[t]) for t in '1234'))

        # 目标：某个基础音节缺某个声调
        targets = []
        for b, tones in by_base.items():
            for t in '1234':
                if t not in tones:
                    targets.append((b, t, 'tone'))
        # 轻声：基础音节存在但没有轻声录音，且朗读需要
        for b, tones in by_base.items():
            if '0' not in tones and (not need or b in need):
                targets.append((b, '0', 'neutral'))
        wanted = [(b, t, kind) for b, t, kind in targets
                  if not need or compose(b, t) in need or kind == 'neutral']

        print('  待补 %d 个（其中带调 %d / 轻声 %d）'
              % (len(wanted), sum(1 for _, _, k in wanted if k == 'tone'),
                 sum(1 for _, _, k in wanted if k == 'neutral')))

        gen_dir = os.path.join(pdir, '_generated')
        if not args.dry_run:
            os.makedirs(gen_dir, exist_ok=True)

        # 按基础音节分组：同一 base 的多个目标放一个任务，源录音少分析几次
        grouped = {}
        for b, t, kind in wanted:
            grouped.setdefault(b, []).append((compose(b, t), t, kind))
        tasks = [(pdir, b, items, by_base[b], templates, levels, gen_dir,
                  args.dry_run) for b, items in grouped.items()]

        generated = {}
        failed = []
        t0 = time.time()
        jobs = args.jobs or max(1, (os.cpu_count() or 2) - 1)
        done = 0
        if jobs > 1 and len(tasks) > 1:
            import multiprocessing as mp
            ctx = mp.get_context('spawn')
            with ctx.Pool(processes=min(jobs, len(tasks))) as pool:
                for res in pool.imap_unordered(_synth_base, tasks):
                    for pinyin, ok, why in res:
                        if ok:
                            generated[pinyin] = '_generated/%s.ogg' % pinyin
                        else:
                            failed.append((pinyin, why))
                    done += 1
                    if not args.quiet and done % 20 == 0:
                        print('    ... %d/%d 个 base' % (done, len(tasks)))
        else:
            for task in tasks:
                for pinyin, ok, why in _synth_base(task):
                    if ok:
                        generated[pinyin] = '_generated/%s.ogg' % pinyin
                    else:
                        failed.append((pinyin, why))
        dt = time.time() - t0
        print('  生成 %d 个音节，耗时 %.1fs（%d 进程并行）'
              % (len(generated), dt, jobs))
        if failed:
            print('  放弃 %d 个（源录音不可用，不产出坏音频）：' % len(failed))
            for pinyin, why in failed[:12]:
                print('    %-8s %s' % (pinyin, why))

        # 覆盖率统计
        new_have = have | set(generated)
        if need:
            covered = len(need & new_have)
            print('  拼音种类覆盖: %d/%d = %.1f%%  (原 %.1f%%)'
                  % (covered, len(need), 100 * covered / len(need),
                     100 * len(need & have) / len(need)))

        manifest = {
            'pack': pack,
            'version': 1,
            'built_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'generated': generated,
            'stats': {
                '原包音节': len(have),
                '补齐音节': len(generated),
                '基础音节': len(by_base),
                '词组': len([f for f in os.listdir(os.path.join(pdir, 'phrases'))
                             if f.endswith('.ogg')])
                if os.path.isdir(os.path.join(pdir, 'phrases')) else 0,
                '声调电平': {k: round(v, 4) for k, v in levels.items()},
            },
        }
        if not args.dry_run:
            with open(os.path.join(pdir, 'assets.json'), 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=1)
            print('  已写入 assets.json')
        else:
            print('  (dry-run，未写文件)')
    return 0 if overall_ok else 1


if __name__ == '__main__':
    sys.exit(main())
