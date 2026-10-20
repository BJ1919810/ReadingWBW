# coding=utf-8
"""声调重组引擎（离线用）。

把音节拆成 (F0 声调轮廓) x (频谱段内容)，再重新组合：
  段内容保持不变（波形取自原音），只把 F0 轮廓换成目标声调。

本模块只依赖 pyworld 的 F0 提取（harvest），
不碰频域重建 —— 详见 voice_synth/__init__.py 的说明。
"""
import os
import unicodedata
import numpy as np
import pyworld as pw

from voice_reader.audio_io import load_audio
from .metrics import hf_ratio as _hf_ratio, ltas_dist, mcd


def vocoder_analyze(x, sr):
    """声码器分析（延迟导入，避免运行时加载 pyworld）"""
    from .vocoder import analyze as va
    return va(x, sr)

F0_FLOOR, F0_CEIL = 60.0, 400.0
FRAME_MS = 5.0
NPT = 64
MARK2TONE = {'̄': '1', '́': '2', '̌': '3', '̀': '4'}


# ---------------------------------------------------------------- 拼音拆合

def decompose(s):
    """'lì' -> ('li', '4')  基础音节 / 声调序号

    注意：'ü' 规范化后是 u + U+0308（变音符号），要把变音符号还原成 'ü'，
    否则 lǜ 会被拆成 'lu'。
    """
    d = unicodedata.normalize('NFD', s)
    base = []
    tone = None
    for c in d:
        if not unicodedata.combining(c):
            base.append(c)
        elif c == '̈':          # 变音符号：把前面的 u 替换成 ü
            if base and base[-1] == 'u':
                base[-1] = 'ü'
            else:
                base.append('ü')
        else:
            tone = c
    return ''.join(base), (MARK2TONE.get(tone, '?') if tone else '0')


def _tone_index(base):
    """声调符该标在哪个元音上（汉语拼音标调规则）"""
    for i, c in enumerate(base):
        if c == 'a':
            return i
    for i, c in enumerate(base):
        if c in 'oe':
            return i
    if 'iu' in base:
        return base.index('iu') + 1
    if 'ui' in base:
        return base.index('ui') + 1
    for i in range(len(base) - 1, -1, -1):
        if base[i] in 'iuü':
            return i
    return None


def compose(base, tone):
    """('li', '4') -> 'lì'；tone='0'（轻声）返回 base 本身

    声调符必须标在正确的元音上：a > o > e > iu 的 u > ui 的 i > 最后一个元音。
    直接拼在字符串末尾只对"以元音结尾"的音节碰巧正确，
    guān->guàń、chuān->chuān̄ 都是错的。
    """
    marks = {'1': '̄', '2': '́', '3': '̌', '4': '̀'}
    m = marks.get(tone)
    if not m:
        return base
    idx = _tone_index(base)
    if idx is None:
        return base
    ch = base[idx]
    if ch == 'ü':
        out = base[:idx] + 'ü' + m + base[idx + 1:]
    else:
        out = base[:idx] + ch + m + base[idx + 1:]
    return unicodedata.normalize('NFC', out)


# ---------------------------------------------------------------- F0 分析

def analyze_f0(x, sr):
    """提取 F0 轨迹（5ms 网格）。

    用 harvest 而不是 dio：实测这批语音素材上 dio 有 20%+ 的片段
    提不出浊音帧（dio=0/45 之类），而 harvest 全部正常。
    harvest 也失败时退回 dio 的宽范围参数。
    """
    f0, t = pw.harvest(x, sr, f0_floor=F0_FLOOR, f0_ceil=F0_CEIL,
                        frame_period=FRAME_MS)
    if int((f0 > 0).sum()) < 4:
        f0, t = pw.dio(x, sr, f0_floor=40, f0_ceil=900, frame_period=FRAME_MS)
    return f0


def voiced_rel(f0):
    """浊音段相对中位数的半音轨迹，以及中心基频"""
    v = f0[f0 > 0]
    if len(v) < 4:
        return None, None
    med = float(np.median(v))
    return 12 * np.log2(v / med), med


def resample_to(rel, n=NPT):
    """把任意长度的轨迹重采样到固定点数，便于求平均"""
    idx = np.linspace(0, len(rel) - 1, n)
    return np.interp(idx, np.arange(len(rel)), rel)


# ---------------------------------------------------------------- 模板

def build_templates(pack_dir, cache_path=None):
    """统计每个声调的 (电平, 形状) 模板。

    模板形状是该声调全部录音的 F0 相对轨迹的平均值，
    形状符合普通话规范：1 平、2 升、3 降升、4 降。

    cache_path: 磁盘缓存路径（键含语音包文件清单的哈希，素材变了自动失效）。
    模板构建要跑 802 次 F0 提取，约 14 秒，缓存后重建就只剩几秒。
    """
    files = sorted({f[:-4] for f in os.listdir(pack_dir) if f.endswith('.ogg')})
    key = None
    if cache_path:
        import hashlib
        import pickle
        key = hashlib.sha1('|'.join(files).encode('utf-8')).hexdigest()[:16]
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    blob = pickle.load(f)
                if blob.get('key') == key:
                    return blob['templates'], blob['levels']
            except Exception:
                pass

    buckets = {t: [] for t in '1234'}
    for h in files:
        b, t = decompose(h)
        if t not in buckets:
            continue
        try:
            x, sr = load_audio(os.path.join(pack_dir, h + '.ogg'))
            f0 = analyze_f0(x, sr)
        except Exception:
            continue
        rel, med = voiced_rel(f0)
        if rel is None:
            continue
        buckets[t].append((med, resample_to(rel)))
    if not all(buckets.values()):
        return None, None
    all_med = np.array([m for t in buckets for m, _ in buckets[t]])
    glob = float(np.median(all_med))
    templates, levels = {}, {}
    for t, items in buckets.items():
        templates[t] = np.array([s for _, s in items]).mean(axis=0)
        levels[t] = float(np.median([m for m, _ in items])) / glob

    if cache_path and key:
        try:
            d = os.path.dirname(cache_path)
            if d:
                os.makedirs(d, exist_ok=True)
            import pickle
            tmp = cache_path + '.tmp'
            with open(tmp, 'wb') as f:
                pickle.dump({'key': key, 'templates': templates,
                             'levels': levels}, f,
                            protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, cache_path)
        except Exception:
            pass
    return templates, levels


# ---------------------------------------------------------------- 合成

def synth_tone(x, sr, src_tone, target_tone, templates, levels, backend='vocoder'):
    """把一段音频的声调重塑为 target_tone（段内容保持不变）。

    backend:
      'vocoder' 默认。声码器重建，频谱包络（共振峰=音色）原样保留，
                不会有相位抵消造成的"电音"；基频逐帧可精确控制，
                声调准确率明显更高（实测 77.8% vs PSOLA 的 50%）。
      'psola'   时域基频同步叠加。声码器不可用时的兜底。

    性能：只做【一次】全量分析（harvest+cheaptrick+d4c），
          之前是三次（analyze_f0 + vocoder_analyze + resynth 内部那次）。
    """
    from .vocoder import analyze as v_analyze, resynth as v_resynth

    analysis = None
    f0 = None
    if backend == 'vocoder':
        try:
            analysis = v_analyze(x, sr)
            f0 = analysis[0]
        except Exception:
            analysis = None
            f0 = None
    if f0 is None:
        f0 = analyze_f0(x, sr)

    rel_c, med_c = voiced_rel(f0)
    if rel_c is None:
        raise ValueError('no voiced frames')

    # 目标 F0 曲线：模板形状 + 目标声调的电平（与源同网格，无需插值）
    shape = templates[target_tone]
    shape_g = np.interp(np.linspace(0, len(shape) - 1, len(f0)),
                        np.arange(len(shape)), shape)
    center = med_c / max(levels.get(src_tone, 1.0), 1e-6) * levels[target_tone]
    f0_tgt = center * np.power(2.0, shape_g / 12.0)
    f0_tgt[f0 <= 0] = 0.0

    y = None
    if analysis is not None:
        try:
            y = v_resynth(x, sr, f0_tgt, analysis=analysis)
        except Exception:
            y = None
    if y is None:
        from .psola import psola_resynth
        y = psola_resynth(x, sr, np.arange(len(f0)) * (FRAME_MS / 1000.0),
                          f0, f0_tgt)
    return _finalize(y, sr, src=x)


# 轻声（neutral tone）：缩短 + 衰减 + 压平基频
NEUTRAL_KEEP = 0.55      # 保留的浊音段比例
NEUTRAL_GAIN = 0.42      # 约 -7.5 dB


def synth_neutral(x, sr):
    """由一个完整声调的录音派生轻声。

    轻声的三个特征：比本调短、音量低、基频平缓。
    基频压平同样走 PSOLA，波形不经过频域重建。
    """
    from .psola import psola_resynth

    f0 = analyze_f0(x, sr)
    vi = np.where(f0 > 0)[0]
    if len(vi) < 4:
        raise ValueError('no voiced frames')
    times = np.arange(len(f0)) * (FRAME_MS / 1000.0)
    v_start = int(vi[0] * FRAME_MS / 1000.0 * sr)
    v_end = int((vi[-1] + 1) * FRAME_MS / 1000.0 * sr)
    cut = int(v_start + (v_end - v_start) * NEUTRAL_KEEP)

    # 压平：目标 F0 = 源中位数（略降）
    v = f0[f0 > 0]
    center = float(np.median(v))
    f0_flat = f0.copy()
    vi2 = np.where(f0 > 0)[0]
    if len(vi2) >= 2:
        flat = np.linspace(0, -0.6, len(vi2))
        f0_flat[vi2] = center * np.power(2.0, flat / 12.0)

    y = psola_resynth(x, sr, times, f0, f0_flat)
    y = y[:cut]
    fo = min(int(0.012 * sr), max(len(y) // 4, 1))
    if fo > 1:
        y[-fo:] *= np.linspace(1, 0, fo)
    # 轻声比本调轻：按源录音的 RMS 乘 NEUTRAL_GAIN，而不是先衰减再峰值归一
    # （先衰减再归一会把衰减抵消掉，轻声就和本调一样响）
    rms_src = float(np.sqrt(np.mean(x ** 2)))
    rms_y = float(np.sqrt(np.mean(y ** 2))) if len(y) else 0.0
    if rms_y > 1e-9 and rms_src > 1e-9:
        y = y * (rms_src * NEUTRAL_GAIN / rms_y)
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 0.95:
        y = y * (0.95 / peak)
    return y


def _finalize(y, sr, src=None):
    """淡入淡出防爆音 + 响度对齐。

    响度必须与【源录音】对齐：之前统一峰值归一到 0.89，
    而原包音节峰值散布在 0.37~0.91、RMS 中位 0.177。
    补齐音节因此比邻居响 1.27 倍，混排时音量跳变 —— 听感发毛。
    """
    fi = min(int(0.005 * sr), len(y) // 2)
    fo = min(int(0.010 * sr), len(y) // 2)
    if fi > 1:
        y[:fi] *= np.linspace(0, 1, fi)
    if fo > 1:
        y[-fo:] *= np.linspace(1, 0, fo)

    if src is not None and len(src) == len(y):
        rms_src = float(np.sqrt(np.mean(src ** 2)))
        rms_y = float(np.sqrt(np.mean(y ** 2)))
        if rms_y > 1e-9 and rms_src > 1e-9:
            y = y * (rms_src / rms_y)

    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 0.95:
        y = y * (0.95 / peak)
    return y


# ---------------------------------------------------------------- 校验

def validate_syllable(y, sr, src=None, max_timbre_drift=10.0, max_mcd=70.0):
    """校验生成结果是否可用。返回 (ok, reason)

    判据是"音色有没有被毁"，不是"F0 能不能被提取出来"：
    目标声调的轮廓有时会让 harvest 提不出基频（短促音节上尤其明显），
    但那种情况下音色其实保住了（实测只漂 1.6dB），
    用 F0 可检测性去卡会把好结果误杀。

    两个音色指标一起看：
      长时谱形状距离 < 10dB   （语音带内，对电平不变）
      MCD < 70dB              （只比声道包络，对变调的谐波位移不敏感）
    阈值依据：同语音包不同音节之间的 MCD 差距是 85.8dB，
    补齐音节实测中位 40.6、90分位 55.3，所以 70 是个合理的分界。

    源录音本身提不出基频（发噪/气声太重）的，不能拿来合成，
    与其输出垃圾音频，不如不生成。
    """
    if y is None or len(y) < int(0.05 * sr):
        return False, '太短'
    if not np.all(np.isfinite(y)):
        return False, '含 NaN/Inf'
    if src is not None:
        nf_new = _hf_ratio(y, sr)
        nf_src = _hf_ratio(src, sr)
        if nf_new > max(nf_src * 3.0, nf_src + 0.25):
            return False, '噪声底异常升高(%.3f->%.3f)' % (nf_src, nf_new)
        drift = ltas_dist(src, y, sr)
        if drift == drift and drift > max_timbre_drift:
            return False, '音色漂移 %.1fdB' % drift
        m = mcd(src, y, sr)
        if m == m and m > max_mcd:
            return False, '音色失真 MCD %.1fdB' % m
    return True, ''
