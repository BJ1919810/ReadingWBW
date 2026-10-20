# coding=utf-8
"""资源路径解析。

全部基于本文件位置推导，不依赖 os.getcwd()，
这样无论从哪个目录启动、还是打包成 exe，资源都能找到。
"""
import os
import sys

# voice_reader/ 的父目录 = 项目根
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PACKAGE_DIR)

# 打包成单文件 exe 时，资源会被解包到 sys._MEIPASS
def _base_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return ROOT


def _user_dir():
    """可写目录。冻结后 BASE_DIR 是临时解包目录（退出即清空），
    缓存不能写在那里，要写到 exe 所在目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return ROOT


BASE_DIR = _base_dir()      # 随包分发的只读资源
USER_DIR = _user_dir()      # 可写目录（缓存等）

VOICE_PACKS_DIR = os.path.join(BASE_DIR, 'VoicesPackages')
CACHE_DIR = os.path.join(USER_DIR, '.cache')
WTV_DATA = os.path.join(BASE_DIR, 'WTV.data')
PRONUNCIATIONS = os.path.join(BASE_DIR, 'pronunciations.json')

# 语音包内部结构（构建工具与运行时必须一致，集中在这里定义）
GENERATED_DIR = '_generated'      # 离线补齐的音节放这里
ASSET_MANIFEST = 'assets.json'    # 补齐清单 + 统计
PHRASES_DIR = 'phrases'            # 词组录音子目录
SILENCE_NAME = '空'                # 静默兜底录音

# 兼容旧版把数据放在 cwd 的情况
if not os.path.exists(WTV_DATA):
    _legacy = os.path.join(os.getcwd(), 'WTV.data')
    if os.path.exists(_legacy):
        WTV_DATA = _legacy


def pack_dir(pack_name):
    """某个语音包的目录"""
    return os.path.join(VOICE_PACKS_DIR, pack_name)


def available_packs():
    """列出可用的语音包（必须有顶层音频文件才算可用）"""
    if not os.path.isdir(VOICE_PACKS_DIR):
        return []
    out = []
    for name in sorted(os.listdir(VOICE_PACKS_DIR)):
        d = pack_dir(name)
        if not os.path.isdir(d):
            continue
        try:
            has_audio = any(f.endswith('.ogg') for f in os.listdir(d))
        except OSError:
            continue
        if has_audio:
            out.append(name)
    return out


def ensure_cache_dir():
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        return CACHE_DIR
    except OSError:
        return None
