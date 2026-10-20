# coding=utf-8
"""音素级移植：把"整个基础音节都不存在"的拼音也补出来。

思路（这是"拆 + 组合"的另一半）：
  一个音节 = 声母 + 韵母。
  包里没有 "néng"，但有 "nǎ"（声母 n）和 "fēng"（韵母 eng）。
  把 nǎ 的声母段和 fēng 的韵母段拼起来，再把基频轮廓换成二声/三声/四声，
  就得到 "néng"。

拼接点怎么定：
  * 韵母取 donor 的【浊音起点之后】的部分 —— 起始辅音切掉，剩下干净的元音
  * 声母取 donor 的【起始段】，长度按该声母类型在包里的中位时长
  * 接缝做 10ms 交叉淡化

声调：拼接后再用声码器整体替换基频轮廓（和声调重组用的是同一套机制），
所以音色的保真度主要取决于"韵母 donor 选得好不好"。
"""
import os
import unicodedata
import numpy as np

# 声母表（长的排前面）
_INITIALS = ('zh', 'ch', 'sh', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l',
             'g', 'k', 'h', 'j', 'q', 'x', 'r', 'z', 'c', 's')
# 零声母（y/w 开头的）特殊处理
_VOWEL_INITIALS = {}


def split_pinyin(py):
    """'neng' -> ('n', 'eng')；'yu' -> ('', 'v')；'zhuang' -> ('zh', 'uang')

    韵母用 ü 记作 v，和语音包里的文件命名保持一致。
    """
    if not py:
        return '', ''
    if py.startswith('y'):
        rest = py[1:]
        if rest.startswith('u'):          # yu yue yuan yun
            return '', 'v' + rest[1:]
        if rest == 'i':
            return '', 'i'
        return '', 'i' + rest
    if py.startswith('w'):
        rest = py[1:]
        if rest == 'u':
            return '', 'u'
        return '', 'u' + rest
    for ini in _INITIALS:
        if py.startswith(ini):
            return ini, py[len(ini):]
    return '', py


def strip_tone(py):
    """去掉声调符号，只留音节本体"""
    d = unicodedata.normalize('NFD', py)
    out = []
    for c in d:
        if unicodedata.combining(c) == 0:
            out.append(c)
        elif c == '̈':          # 变音符 -> ü
            if out and out[-1] == 'u':
                out[-1] = 'v'
            else:
                out.append('v')
    s = ''.join(out).replace('ü', 'v')
    return s


def voiced_onset(f0):
    """浊音起点（帧索引）：F0 连续为正的第一帧"""
    if len(f0) == 0:
        return None
    v = f0 > 0
    for i in range(len(v)):
        if v[i] and (i + 3 >= len(v) or v[i:i + 3].all()):
            return i
    return None


def _frame_rms(x, sr, frame_ms=5.0):
    n = max(int(sr * frame_ms / 1000.0), 1)
    m = len(x) // n
    if m < 2:
        return np.zeros(1), n
    return np.sqrt((x[:m * n].reshape(m, n) ** 2).mean(axis=1)), n


def vowel_onset(x, sr):
    """元音起点（秒）：能量对数域的最大上升沿。

    不能用 F0 找起点 —— harvest 对闭塞段也报 F0，
    很多音节的 F0 从第 0 帧就是正的，起点会被算成 0，声母段就空了。
    """
    rms, n = _frame_rms(x, sr)
    if len(rms) < 3:
        return 0.0
    db = 20 * np.log10(np.maximum(rms, 1e-5))
    half = max(3, len(db) // 2)
    i = int(np.argmax(np.diff(db)[:half]))
    return (i + 1) * n / sr


def vowel_stable(x, sr):
    """元音稳定段起点（秒）：越过起音后的第一个高能量点。

    切韵母要从这里切，避开塞音的爆破噪声（爆破会被重复听两次）。
    """
    rms, n = _frame_rms(x, sr)
    if len(rms) < 3:
        return 0.0
    db = 20 * np.log10(np.maximum(rms, 1e-5))
    thr = np.percentile(db, 90) - 6.0
    for i in range(len(db)):
        if db[i] >= thr:
            return i * n / sr
    return 0.0


class DonorIndex:
    """语音包里可用的 donor：按韵母归类（取元音）+ 按声母归类（取辅音）"""

    def __init__(self, pack_dir):
        self.pack_dir = pack_dir
        self.by_final = {}      # final -> [(name, initial, onset_sec, dur_sec)]
        self.by_initial = {}    # initial -> [(name, onset_sec)]
        self.initial_dur = {}   # initial -> 该声母段的中位时长(秒)
        self._scan()

    def _scan(self):
        from .tone_synth import load_audio
        buckets = {i: [] for i in _INITIALS}
        for f in sorted(os.listdir(self.pack_dir)):
            if not f.endswith('.ogg'):
                continue
            name = f[:-4]
            py = strip_tone(name)
            if not py or py in ('de', 'le', 'me', 'ne', 'pu', 'a', 'e', 'o'):
                continue
            ini, fin = split_pinyin(py)
            if not fin:
                continue
            try:
                x, sr = load_audio(os.path.join(self.pack_dir, name + '.ogg'))
            except Exception:
                continue
            onset = vowel_onset(x, sr)        # 元音起点：切声母用
            stable = vowel_stable(x, sr)      # 元音稳定段：切韵母用
            dur = len(x) / sr
            if stable <= onset:
                stable = onset
            self.by_final.setdefault(fin, []).append((name, ini, onset, stable, dur))
            if ini:
                self.by_initial.setdefault(ini, []).append((name, onset, dur))
                buckets[ini].append(onset)
        # 每种声母段的中位时长
        for ini, vals in buckets.items():
            if vals:
                self.initial_dur[ini] = float(np.median(vals))

    def final_donors(self, final):
        return self.by_final.get(final, [])

    def initial_donors(self, initial):
        return self.by_initial.get(initial, [])

    def initial_duration(self, initial):
        return self.initial_dur.get(initial, 0.06)


def _seg(x, sr, a, b):
    a = max(0, min(int(a * sr), len(x) - 1))
    b = max(a + 1, min(int(b * sr), len(x)))
    return x[a:b]


def _crossfade(a, b, sr, ms=6.0):
    """把 a、b 拼起来，接缝处交叉淡化。

    淡化长度必须自适应：声母段常常只有 10~20ms，
    固定 10ms 的淡化会把塞音的爆破音整个吃掉，结果里就没有这个声母了。
    """
    shorter = min(len(a), len(b))
    n = max(int(ms / 1000.0 * sr), 2)
    n = min(n, int(shorter * 0.3))     # 不超过较短段的 30%
    if n < 2:
        return np.concatenate([a, b])
    w = np.linspace(0, 1, n)
    mid = a[-n:] * (1 - w) + b[:n] * w
    return np.concatenate([a[:-n], mid, b[n:]])


_SEG_CACHE = {}


def _segments(pack_dir, name):
    """取出某个音节的 (声母段, 韵母段)，带缓存。"""
    if name in _SEG_CACHE:
        return _SEG_CACHE[name]
    from .tone_synth import load_audio
    try:
        x, sr = load_audio(os.path.join(pack_dir, name + '.ogg'))
    except Exception:
        _SEG_CACHE[name] = None
        return None
    onset = vowel_onset(x, sr)
    stable = vowel_stable(x, sr)
    dur = len(x) / sr
    if stable <= onset:
        stable = onset
    ini_seg = _seg(x, sr, 0.0, onset)
    fin_seg = _seg(x, sr, stable, dur)
    _SEG_CACHE[name] = (ini_seg, fin_seg, sr, dur)
    return _SEG_CACHE[name]


def splice(pack_dir, initial, final, index, prefer_initial=None):
    """拼接出 声母+韵母 的音节。返回 (音频, 采样率, 声母donor, 韵母donor) 或 None。"""
    fin_donors = index.final_donors(final)
    ini_donors = index.initial_donors(initial)
    if not fin_donors or not ini_donors:
        return None

    # 韵母 donor：优先选声母与目标不同类的（避免鼻音重复叠加）
    def fin_rank(d):
        name, ini_d, onset, stable, dur = d
        if prefer_initial and ini_d == prefer_initial:
            return 2
        if ini_d in ('m', 'n'):
            return 1
        return 0
    fin_sorted = sorted(fin_donors, key=fin_rank)

    # 声母 donor：初始段长度接近该声母类型中位时长的优先
    target_dur = index.initial_duration(initial)
    ini_sorted = sorted(ini_donors, key=lambda d: abs(d[1] - target_dur))

    # 声母段候选（8~120ms）
    ini_cands = []
    for name_i, onset_i, dur_i in ini_sorted:
        segs = _segments(pack_dir, name_i)
        if not segs:
            continue
        ini_seg = segs[0]
        d = len(ini_seg) / segs[2]
        if 0.008 <= d <= 0.12:
            ini_cands.append((name_i, ini_seg, segs[2], abs(d - target_dur)))
    ini_cands.sort(key=lambda t: t[3])
    ini_cands = ini_cands[:6]
    if not ini_cands:
        return None

    # 韵母段候选（≥50ms）
    fin_cands = []
    for name_f, ini_f, onset_f, stable_f, dur_f in fin_sorted:
        segs = _segments(pack_dir, name_f)
        if not segs:
            continue
        fin_seg = segs[1]
        if len(fin_seg) / segs[2] >= 0.05:
            fin_cands.append((name_f, fin_seg, segs[2]))
    fin_cands = fin_cands[:8]
    if not fin_cands:
        return None

    for name_i, ini_seg, sr, _ in ini_cands:
        for name_f, fin_seg, sr2 in fin_cands:
            if sr != sr2:
                continue
            return _crossfade(ini_seg, fin_seg, sr), sr, name_i, name_f
    return None
