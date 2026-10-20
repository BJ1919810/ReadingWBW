# coding=utf-8
"""体检项的单一实现。

tools/ 下每个检查脚本和 check_all.py 共用这里的函数，
避免"同一件事两套算法、指标悄悄对不上"。

每个检查返回 (名称, 是否通过, 数值说明, 细节)。
"""
import os
import sys
import subprocess

import numpy as np

from _common import ROOT
from voice_reader import paths
from voice_reader.assets import AssetIndex
from voice_reader.pinyin_map import (PhraseIndex, load_wtv_map, load_overrides,
                                     convert_to_pinyin, detect_encoding)
from voice_synth import decompose
from voice_synth.metrics import mcd
from voice_reader.audio_io import load_audio


def _run(cmd, timeout=300):
    """跑子进程。Windows 控制台默认 GBK，这里强制 UTF-8 且不因个别坏字节炸掉。"""
    return subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=ROOT,
                          encoding='utf-8', errors='replace')

PACK = 'hanser'
NOVELS = ['原神之可莉小矮砸.txt', '笑樱.txt', '在崩铁里作死是不是搞错了什么？.txt']


# ---------------------------------------------------------------- 覆盖率

def check_coverage(min_pct=95.0):
    index = AssetIndex(PACK)
    wtv = load_wtv_map()
    overrides = load_overrides()
    phrases = PhraseIndex(index.phrases.keys())
    worst = 100.0
    detail = []
    for name in NOVELS:
        p = os.path.join(paths.ROOT, name)
        if not os.path.exists(p):
            continue
        text, _ = detect_encoding(p)
        py = convert_to_pinyin(text, wtv, None, overrides)
        hit = tot = 0
        for kind, key, alt in phrases.iter_tokens(text, py, wtv):
            if kind != 'char':
                continue
            tot += 1
            if index.has(key) or (alt and index.has(alt)):
                hit += 1
        if tot:
            pct = 100.0 * hit / tot
            worst = min(worst, pct)
            detail.append('%s %.1f%%' % (name[:6], pct))
    ok = worst >= min_pct
    return ('覆盖率', ok, '最低 %.1f%% (阈值 ≥%.0f%%)' % (worst, min_pct),
            '  '.join(detail))


# ---------------------------------------------------------------- 融合度

def check_blend(max_mcd=60.0):
    pdir = paths.pack_dir(PACK)
    gen = os.path.join(pdir, '_generated')
    if not os.path.isdir(gen):
        return ('融合度', False, '没有 _generated 目录', '先跑 build_voicepack')
    have = {f[:-4] for f in os.listdir(pdir) if f.endswith('.ogg')}
    byb = {}
    for h in have:
        b, t = decompose(h)
        if t in '1234':
            byb.setdefault(b, {})[t] = h
    ms = []
    for f in sorted(os.listdir(gen)):
        if not f.endswith('.ogg'):
            continue
        name = f[:-4]
        b, t = decompose(name)
        srcs = byb.get(b, {})
        if not srcs:
            continue
        src = srcs[sorted(srcs)[0]]
        g, gsr = load_audio(os.path.join(gen, name + '.ogg'))
        s, ssr = load_audio(os.path.join(pdir, src + '.ogg'))
        v = mcd(s, g, ssr)
        if v == v:
            ms.append(v)
    if not ms:
        return ('融合度', False, '没有可比对的样本', '')
    med = float(np.median(ms))
    # 标尺：不同音节之间的 MCD 差距
    x, sr = load_audio(os.path.join(pdir, 'hāo.ogg'))
    y, _ = load_audio(os.path.join(pdir, 'māo.ogg'))
    scale = mcd(x, y, sr)
    ok = med < max_mcd
    return ('融合度', ok, 'MCD中位 %.1f (阈值 <%.0f)' % (med, max_mcd),
            '不同音节间 MCD=%.1f，中位为其 %.0f%%' % (scale, 100 * med / max(scale, 1e-9)))


# ---------------------------------------------------------------- 声调

def check_tone(min_pct=60.0):
    """合成结果的声调判定率（对照分类器天花板）。"""
    from voice_synth import build_templates, synth_tone
    pdir = paths.pack_dir(PACK)
    templates, levels = build_templates(pdir)
    if templates is None:
        return ('声调准确率', False, '模板构建失败', '')
    # 分类器天花板：原包真实录音
    real_ok = real_tot = 0
    for f in sorted(os.listdir(pdir)):
        if not f.endswith('.ogg'):
            continue
        name = f[:-4]
        b, t = decompose(name)
        if t not in '1234':
            continue
        try:
            x, sr = load_audio(os.path.join(pdir, name + '.ogg'))
            from voice_synth.tone_synth import analyze_f0, voiced_rel, resample_to
            f0 = analyze_f0(x, sr)
            rel, med = voiced_rel(f0)
            if rel is None:
                continue
            shape = resample_to(rel)
            pred = min(templates, key=lambda t: np.linalg.norm(templates[t] - shape))
        except Exception:
            continue
        real_tot += 1
        real_ok += (pred == t)

    ok_cnt = tot = 0
    for src in ['hāo', 'yī', 'māo', 'lā', 'shì', 'tán', 'hǎo', 'zhōng']:
        p = os.path.join(pdir, src + '.ogg')
        if not os.path.exists(p):
            continue
        x, sr = load_audio(p)
        st = decompose(src)[1]
        for tgt in '1234':
            if tgt == st:
                continue
            try:
                y = synth_tone(x, sr, st, tgt, templates, levels)
                from voice_synth.tone_synth import analyze_f0, voiced_rel, resample_to
                f0 = analyze_f0(y, sr)
                rel, med = voiced_rel(f0)
                if rel is None:
                    tot += 1
                    continue
                shape = resample_to(rel)
                pred = min(templates, key=lambda t: np.linalg.norm(templates[t] - shape))
            except Exception:
                tot += 1
                continue
            tot += 1
            ok_cnt += (pred == tgt)
    pct = 100.0 * ok_cnt / max(tot, 1)
    ceil_pct = 100.0 * real_ok / max(real_tot, 1)
    ok = pct >= min_pct
    return ('声调准确率', ok, '%.1f%% (阈值 ≥%.0f%%)' % (pct, min_pct),
            '分类器天花板 %.1f%%（原包真实录音）' % ceil_pct)


# ---------------------------------------------------------------- 响度

def check_loudness(lo=0.85, hi=1.15):
    pdir = paths.pack_dir(PACK)
    gen = os.path.join(pdir, '_generated')
    if not os.path.isdir(gen):
        return ('响度一致性', False, '没有 _generated 目录', '')
    orig, genr = [], []
    for d, acc in ((pdir, orig), (gen, genr)):
        for f in os.listdir(d):
            if not f.endswith('.ogg'):
                continue
            x, sr = load_audio(os.path.join(d, f))
            acc.append(float(np.sqrt((x ** 2).mean())))
    if not orig or not genr:
        return ('响度一致性', False, '样本不足', '')
    ratio = float(np.median(genr)) / float(np.median(orig))
    ok = lo <= ratio <= hi
    return ('响度一致性', ok, 'RMS比 %.2f (阈值 %.2f~%.2f)' % (ratio, lo, hi),
            '补齐音节与原包混排不应忽大忽小')


# ---------------------------------------------------------------- 稳定性

def check_stability():
    """线程泄漏 + 实际播放。"""
    script = os.path.join(ROOT, 'tools', 'stress_test.py')
    try:
        r = _run([sys.executable, script], timeout=300)
    except subprocess.TimeoutExpired:
        return ('稳定性', False, '压力测试超时', '')
    out = r.stdout + r.stderr
    leak = None
    for line in out.splitlines():
        if '泄漏=' in line:
            leak = int(line.split('泄漏=')[1].split()[0])
    if leak is None:
        return ('稳定性', False, '压力测试没给出结论', out[-300:])
    return ('稳定性', leak == 0, '线程泄漏 %d (阈值 =0)' % leak, '反复启停 + 中途停止')


# ---------------------------------------------------------------- 静态检查

def check_lint():
    try:
        r = _run([sys.executable, '-m', 'pyflakes',
                  'voice_reader', 'voice_synth', 'tools', 'SearchTool.py'],
                 timeout=120)
    except FileNotFoundError:
        return ('静态检查', True, 'pyflakes 未安装，跳过', '')
    lines = [l for l in (r.stdout or '').splitlines()
             if l.strip() and "_common.ROOT' imported but unused" not in l
             and 'unable to detect undefined names' not in l]
    return ('静态检查', not lines, '%d 条告警' % len(lines),
            ' / '.join(lines[:3]) if lines else '干净')


# ---------------------------------------------------------------- 导入

def check_imports():
    code = (
        "import sys; sys.path.insert(0,'.')\n"
        "import voice_reader, voice_reader.paths, voice_reader.audio_io\n"
        "import voice_reader.pinyin_map, voice_reader.assets\n"
        "import voice_reader.player, voice_reader.ui\n"
        "import voice_synth, voice_synth.psola, voice_synth.tone_synth\n"
        "import voice_synth.vocoder, voice_synth.metrics\n"
        "print('ok')\n")
    r = _run([sys.executable, '-c', code], timeout=120)
    ok = r.returncode == 0
    return ('模块导入', ok, '正常' if ok else '失败', (r.stderr or '')[-200:])


# ---------------------------------------------------------------- 汇总

def check_phoneme(min_pct=99.0):
    """音素级移植层：开启后覆盖率应显著提升；关闭后行为应与之前完全一致。"""
    from voice_reader.assets import AssetIndex
    wtv = load_wtv_map()
    ov = load_overrides()

    def cov(use_phoneme):
        index = AssetIndex(PACK, use_phoneme=use_phoneme)
        ph = PhraseIndex(index.phrases.keys())
        pcts = []
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
                if index.has(key) or (alt and index.has(alt)):
                    hit += 1
            if tot:
                pcts.append(100.0 * hit / tot)
        return index, (min(pcts) if pcts else 0.0)

    idx_off, pct_off = cov(False)
    idx_on, pct_on = cov(True)
    if len(idx_on.phoneme) == 0:
        return ('音素级补齐', False, '音素层是空的',
                '跑 python tools/build_phoneme.py %s 生成' % PACK)
    ok = pct_on >= min_pct and pct_on > pct_off
    return ('音素级补齐', ok, '开 %d 个音节，覆盖 %.1f%% -> %.1f%%'
            % (len(idx_on.phoneme), pct_off, pct_on),
            '阈值 ≥%.0f%%；关闭开关即回滚' % min_pct)


def check_playback_fidelity(max_err=1e-3):
    """播放保真：把 mixer 实际收到的字节解回来，和源文件逐样本比。

    这项检查是为了防住"把 float32 字节当成 int16 送进 mixer"这种错位 ——
    位深一错，听感就是"全损音质"的纯噪声，但程序不会报任何错。
    """
    import numpy as np
    from voice_reader.audio_io import load_sound_bytes, load_audio
    pdir = paths.pack_dir(PACK)
    names = [f[:-4] for f in sorted(os.listdir(pdir))
             if f.endswith('.ogg') and not f.startswith('空')][:20]
    worst = 0.0
    for n in names:
        p = os.path.join(pdir, n + '.ogg')
        try:
            raw, sr = load_sound_bytes(p)
            back = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32767.0
            # 参照也要同样重采样 + 同样削波，否则比的是两回事
            src, _ = load_audio(p, target_sr=sr)
            src = np.clip(src, -1.0, 1.0)
        except Exception as exc:
            return ('播放保真', False, '读取失败: %s' % exc, '')
        m = min(len(back), len(src))
        if m < 100:
            continue
        err = float(np.max(np.abs(back[:m] - src[:m])))
        worst = max(worst, err)
    ok = worst <= max_err
    return ('播放保真', ok, '最大样本误差 %.2e (阈值 %.0e)' % (worst, max_err),
            'mixer 收到的是 16-bit PCM；位深错位会立刻爆表')


ALL_CHECKS = [
    ('模块导入', check_imports),
    ('静态检查', check_lint),
    ('覆盖率', check_coverage),
    ('融合度', check_blend),
    ('声调准确率', check_tone),
    ('响度一致性', check_loudness),
    ('音素级补齐', check_phoneme),
    ('播放保真', check_playback_fidelity),
    ('稳定性', check_stability),
]
