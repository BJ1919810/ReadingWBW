# coding=utf-8
"""语音包索引。

一个语音包目录长这样：
    VoicesPackages/hanser/
        ā.ogg  bā.ogg  ...      单字（音节）录音
        空.ogg                  静默兜底
        phrases/
            为什么.ogg  hello.ogg ...   词组录音
        _generated/              离线生成的补齐音节（tools/build_voicepack.py 产出）
        assets.json              补齐清单 + 统计信息
"""
import os
import json
import logging

from . import paths

log = logging.getLogger(__name__)

SILENCE = paths.SILENCE_NAME
GENERATED_DIR = paths.GENERATED_DIR
ASSET_MANIFEST = paths.ASSET_MANIFEST
PHRASES_DIR = paths.PHRASES_DIR


class AssetIndex:
    """某个语音包的可播放资源索引。"""

    def __init__(self, pack_name):
        self.pack = pack_name
        self.root = paths.pack_dir(pack_name)
        self.syllables = {}     # 音节 -> 文件路径
        self.generated = {}     # 音节 -> 文件路径（离线补齐）
        self.phrases = {}       # 词组 -> 文件路径
        self.stats = {}
        self._load()

    # ---------- 加载 ----------
    def _load(self):
        if not os.path.isdir(self.root):
            raise FileNotFoundError('语音包目录不存在：%s' % self.root)
        self._scan_syllables()
        self._scan_phrases()
        self._load_manifest()

    def _scan_syllables(self):
        try:
            entries = os.listdir(self.root)
        except OSError as exc:
            log.warning('扫描语音包失败：%s', exc)
            return
        for name in entries:
            if not name.endswith('.ogg'):
                continue
            if os.path.isdir(os.path.join(self.root, name)):
                continue
            self.syllables[name[:-4]] = os.path.join(self.root, name)

    def _scan_phrases(self):
        pdir = os.path.join(self.root, PHRASES_DIR)
        if not os.path.isdir(pdir):
            return
        try:
            entries = os.listdir(pdir)
        except OSError as exc:
            log.warning('扫描词组目录失败：%s', exc)
            return
        for name in entries:
            if name.endswith('.ogg'):
                self.phrases[name[:-4]] = os.path.join(pdir, name)

    def _load_manifest(self):
        mpath = os.path.join(self.root, ASSET_MANIFEST)
        if not os.path.exists(mpath):
            self._scan_generated()
            return
        try:
            with open(mpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as exc:
            log.warning('assets.json 解析失败（忽略，改用目录扫描）：%s', exc)
            self._scan_generated()
            return
        self.stats = data.get('stats', {})
        for pinyin, rel in (data.get('generated') or {}).items():
            full = os.path.join(self.root, rel.replace('/', os.sep))
            if os.path.exists(full):
                self.generated[pinyin] = full
        # 清单里没有但目录里有的，也算数（防止清单过期导致补齐音节失联）
        self._scan_generated()

    def _scan_generated(self):
        """直接扫 _generated/ 目录。

        这样即使 assets.json 丢了或坏了，补齐的音节也不会失联。
        """
        gdir = os.path.join(self.root, GENERATED_DIR)
        if not os.path.isdir(gdir):
            return
        try:
            entries = os.listdir(gdir)
        except OSError as exc:
            log.warning('扫描补齐目录失败：%s', exc)
            return
        for name in entries:
            if name.endswith('.ogg'):
                self.generated.setdefault(name[:-4],
                                         os.path.join(gdir, name))

    # ---------- 查询 ----------
    def syllable(self, pinyin):
        """音节录音路径；优先原包，其次离线补齐，都没有返回 None"""
        if pinyin in self.syllables:
            return self.syllables[pinyin]
        return self.generated.get(pinyin)

    def phrase(self, text):
        return self.phrases.get(text)

    def has(self, pinyin):
        return pinyin in self.syllables or pinyin in self.generated

    def coverage(self):
        return {
            '音节(原包)': len(self.syllables),
            '音节(补齐)': len(self.generated),
            '词组': len(self.phrases),
        }
