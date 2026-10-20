# coding=utf-8
"""文本 -> 发音单元。

两件事：
  1. 把文本转成逐字拼音（pypinyin 上下文转写，能正确处理多音字；
     WTV.data 作为查不到时的兜底），结果落盘缓存。
  2. 把文本切成"发音单元"：优先匹配语音包里的词组录音，
     匹配不到再退回单字。整个过程是惰性生成，不会把整本书塞进内存。
"""
import os
import json
import pickle
import logging

from . import paths

log = logging.getLogger(__name__)

# WTV.data 解析一次就够，全进程复用
_WTV_CACHE = None

# 朗读时的标点停顿（秒）
PUNCT_PAUSE = {
    '，': 0.16, ',': 0.16, '、': 0.12, '；': 0.20, ';': 0.20,
    '：': 0.18, ':': 0.18, '。': 0.28, '.': 0.28, '！': 0.28, '!': 0.28,
    '？': 0.30, '?': 0.30, '…': 0.30, '—': 0.20, '~': 0.12, '～': 0.12,
    '\n': 0.24, '“': 0.02, '”': 0.02, '"': 0.02, '（': 0.10, '）': 0.10,
    '(': 0.10, ')': 0.10, '《': 0.10, '》': 0.10, '【': 0.10, '】': 0.10,
}
PAUSE_CHARS = set(PUNCT_PAUSE)


def load_wtv_map():
    """WTV.data: 形如 '吖ā,阿ā,啊ā' 的字->拼音表，作为 pypinyin 的兜底。

    解析一次后缓存 —— 这个表有两万多条，每次调用都重新解析太浪费。
    """
    global _WTV_CACHE
    if _WTV_CACHE is not None:
        return _WTV_CACHE
    m = {}
    if not os.path.exists(paths.WTV_DATA):
        log.warning('未找到 WTV.data，多音字兜底不可用：%s', paths.WTV_DATA)
        _WTV_CACHE = m
        return m
    try:
        with open(paths.WTV_DATA, 'rb') as f:
            raw = pickle.load(f)
        for item in raw.split(','):
            if len(item) > 1:
                m[item[0]] = item[1:]
    except Exception as exc:
        log.warning('WTV.data 解析失败：%s', exc)
    _WTV_CACHE = m
    return m


def detect_encoding(path):
    """按顺序尝试常见编码，失败则用 latin-1 兜底（不会抛异常）"""
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'gb18030', 'big5'):
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read(), enc
        except UnicodeDecodeError:
            continue
        except OSError:
            raise
    with open(path, 'r', encoding='latin-1', errors='replace') as f:
        return f.read(), 'latin-1'


def load_overrides():
    """自定义读音表：{"椎名樱": "zhuī míng yīng"}，用于人名/生僻字。

    文件放在项目根的 pronunciations.json，随时可改。
    """
    path = paths.PRONUNCIATIONS
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        out = {}
        for k, v in data.items():
            if k.startswith('_'):
                continue          # 允许在文件里写注释
            if isinstance(v, str):
                out[k] = v.split()
            elif isinstance(v, list):
                out[k] = list(v)
        return out
    except Exception as exc:
        log.warning('pronunciations.json 解析失败（忽略）：%s', exc)
        return {}


def apply_overrides(text, pinyin_list, overrides):
    """把自定义读音覆盖到拼音序列上（按长词优先）"""
    if not overrides:
        return pinyin_list
    keys = sorted(overrides, key=len, reverse=True)
    out = list(pinyin_list)
    i = 0
    n = len(text)
    while i < n:
        hit = None
        for k in keys:
            if k and text.startswith(k, i):
                hit = k
                break
        if hit:
            seq = overrides[hit]
            for j, py in enumerate(seq):
                if i + j < n:
                    out[i + j] = py
            i += len(hit)
        else:
            i += 1
    return out


def convert_to_pinyin(text, wtv=None, cache_path=None, overrides=None):
    """逐字拼音列表。

    优先级：自定义读音表 > pypinyin 上下文转写 > WTV.data 兜底。
    结果落盘缓存（键含文本内容，文件变了自动失效）。
    """
    if wtv is None:
        wtv = load_wtv_map()
    if overrides is None:
        overrides = load_overrides()
    cache_sig = None
    if cache_path:
        try:
            cache_sig = _cache_signature(overrides)
        except Exception:
            cache_sig = None

    if cache_path and cache_sig is not None and os.path.exists(cache_path):
        try:
            with open(cache_path, 'rb') as f:
                blob = pickle.load(f)
            if (isinstance(blob, dict) and blob.get('text') == text
                    and blob.get('sig') == cache_sig):
                return blob['pinyin']
        except Exception:
            pass

    result = None
    try:
        from pypinyin import pinyin, Style
        # errors 回调返回 list(x) 才能保证结果与原文严格 1:1 对齐
        # （默认会把连续的非中文字符合并成一项，导致下标错位）
        res = pinyin(text, style=Style.TONE, strict=True, errors=lambda x: list(x))
        result = []
        for item in res:
            if isinstance(item, (list, tuple)):
                item = item[0] if item else ''
            result.append(item)
    except Exception as exc:
        log.warning('pypinyin 转写失败，回退到 WTV.data：%s', exc)
        result = None

    if result is None:
        result = [wtv.get(ch, '') for ch in text]
    else:
        if len(result) != len(text):
            result = (result + [''] * len(text))[:len(text)]
        for i, ch in enumerate(text):
            if not result[i] or result[i] == ch:
                result[i] = wtv.get(ch, result[i])

    result = apply_overrides(text, result, overrides)

    if cache_path and cache_sig is not None:
        d = paths.ensure_cache_dir()
        if d:
            tmp = cache_path + '.tmp'
            try:
                with open(tmp, 'wb') as f:
                    pickle.dump({'text': text, 'pinyin': result, 'sig': cache_sig},
                                f, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(tmp, cache_path)
            except Exception as exc:
                log.debug('拼音缓存写入失败：%s', exc)
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    return result


def _cache_signature(overrides):
    import hashlib
    blob = json.dumps(overrides, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode('utf-8')).hexdigest()


class PhraseIndex:
    """语音包词组索引：按首字分组，惰性产出发音单元。"""

    def __init__(self, phrases):
        self.phrases = phrases
        self.by_first = {}
        for p in phrases:
            if not p:
                continue
            self.by_first.setdefault(p[0], set()).add(len(p))
        for k in self.by_first:
            self.by_first[k] = sorted(self.by_first[k], reverse=True)
        self.max_len = max((len(p) for p in phrases), default=0)

    def iter_tokens(self, text, pinyin_list, wtv=None):
        """产出 (kind, key, alt)：
             kind='phrase', key=词组文本, alt=''
             kind='char',   key=主读音,    alt=备选读音（WTV.data 的读法）
             kind='pause',  key=停顿秒数,  alt=''

        alt 的用途：pypinyin 的读音在语音包里没有录音时，可以退到
        WTV.data 的读法。两者谁对谁错取决于上下文（人名、生僻字），
        哪个有录音就用哪个，比二选一稳。
        """
        n = len(text)
        i = 0
        while i < n:
            ch = text[i]
            if ch in PAUSE_CHARS:
                yield ('pause', PUNCT_PAUSE[ch], '')
                i += 1
                continue
            if ch.isspace():
                i += 1
                continue

            matched = None
            for length in self.by_first.get(ch, ()):
                if i + length > n:
                    continue
                cand = text[i:i + length]
                if cand in self.phrases:
                    matched = cand
                    break
            if matched:
                yield ('phrase', matched, '')
                i += len(matched)
                continue

            py = pinyin_list[i] if i < len(pinyin_list) else ''
            # py == ch 说明 pypinyin 不认识这个字，不是发音，跳过
            if py and py != ch:
                alt = ''
                if wtv:
                    a = wtv.get(ch, '')
                    if a and a != py:
                        alt = a
                yield ('char', py, alt)
            i += 1
