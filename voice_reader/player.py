# coding=utf-8
"""播放引擎。

关键点：
  * 预取线程负责解码音频，主线程只管播 —— 解码不拖慢朗读
  * 主线程等音频自然播完，不做忙等
  * 缺录音的音节走"空.ogg"，并在日志里记下来，不中断朗读
  * 停止时生产者线程必须能退出（否则每启停一次泄漏一个线程）
"""
import os
import time
import queue
import threading
import logging

from . import paths
from .assets import AssetIndex
from .audio_io import load_sound_bytes
from .pinyin_map import (PhraseIndex, load_wtv_map, convert_to_pinyin,
                         load_overrides)

log = logging.getLogger(__name__)

SAMPLE_RATE = 48000
CHUNK = 512
PREFETCH = 24          # 预取队列长度
PUT_TIMEOUT = 0.5      # 生产者入队超时（秒），用于感知停止


class PlaybackStopped(Exception):
    pass


class Player:
    """把文本读出来。"""

    def __init__(self, pack_name, on_progress=None, on_log=None):
        self.index = AssetIndex(pack_name)
        self.phrases = PhraseIndex(self.index.phrases.keys())
        self.on_progress = on_progress
        self.on_log = on_log
        self._stop = threading.Event()
        self._thread = None
        self._pygame = None
        self.missing = set()
        self.recovered = set()
        self.error = None      # 朗读过程中的异常，供界面显示

    # ---------- 生命周期 ----------
    def start(self, text, text_path=None):
        if self._thread and self._thread.is_alive():
            raise RuntimeError('已经在朗读了')
        self._stop.clear()
        self.missing = set()
        self.recovered = set()
        self.error = None
        self._thread = threading.Thread(target=self._run, args=(text, text_path),
                                        daemon=True, name='reader')
        self._thread.start()
        return self._thread

    def stop(self):
        self._stop.set()
        if self._pygame:
            try:
                self._pygame.mixer.stop()
            except Exception:
                pass

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    # ---------- 主流程 ----------
    def _run(self, text, text_path):
        try:
            self._pygame = _init_pygame()
        except Exception as exc:
            self.error = exc
            self._log('音频设备初始化失败：%s' % exc)
            return

        wtv = load_wtv_map()
        overrides = load_overrides()
        cache_path = None
        if text_path:
            cache_path = os.path.join(
                paths.ensure_cache_dir() or '.',
                'pinyin_%s.pkl' % _hash_name(text_path))
        pinyin_list = convert_to_pinyin(text, wtv, cache_path, overrides)
        tokens = self.phrases.iter_tokens(text, pinyin_list, wtv)

        total = max(len(text), 1)
        done = 0
        q = queue.Queue(maxsize=PREFETCH)
        stop = self._stop

        def producer():
            """预取线程：解析资源并解码音频。

            停止时必须能退出：入队用超时，感知到停止就返回；
            否则队列满时会永久阻塞在 put() 上，泄漏线程。
            """
            try:
                for kind, key, alt in tokens:
                    if stop.is_set():
                        break
                    if kind == 'pause':
                        if not _put(q, ('pause', key, None, 0), stop):
                            break
                        continue
                    if kind == 'phrase':
                        path = self.index.phrase(key)
                    else:
                        path = self.index.syllable(key)
                        if path is None and alt:
                            # 主读音没录音，退到备选读音
                            path = self.index.syllable(alt)
                            if path is not None:
                                self.recovered.add((key, alt))
                    if path is None:
                        if kind == 'char':
                            self.missing.add(key)
                        path = self.index.syllable(paths.SILENCE_NAME)
                        if path is None:
                            if not _put(q, ('pause', 0.08, None, 0), stop):
                                break
                            continue
                    try:
                        data, sr = load_sound_bytes(path)
                    except Exception:
                        if not _put(q, ('pause', 0.08, None, 0), stop):
                            break
                        continue
                    if not _put(q, ('audio', path, data, sr), stop):
                        break
            finally:
                _put(q, ('end', None, None, 0), stop, force=True)

        th = threading.Thread(target=producer, daemon=True, name='reader-prefetch')
        th.start()

        try:
            while True:
                item = q.get()
                if item[0] == 'end':
                    break
                kind, key, data, sr = item
                if stop.is_set():
                    break
                if kind == 'pause':
                    _interruptible_sleep(key, stop)
                else:
                    self._play(data, sr)
                done += _token_weight(key, kind)
                if self.on_progress:
                    try:
                        self.on_progress(min(done, total), total)
                    except Exception:
                        log.debug('进度回调异常', exc_info=True)
        except PlaybackStopped:
            pass
        except Exception as exc:
            self.error = exc
            self._log('朗读出错：%s' % exc)
            log.exception('朗读异常')
        finally:
            stop.set()
            try:
                self._pygame.mixer.stop()
            except Exception:
                pass
            if self.missing:
                self._log('未收录 %d 个音节：%s' %
                          (len(self.missing), ' '.join(sorted(self.missing)[:40])))
            if self.recovered:
                self._log('备选读音兜底 %d 处：%s' %
                          (len(self.recovered),
                           ' '.join('%s>%s' % r for r in sorted(self.recovered)[:20])))
            self._log('朗读结束')

    # ---------- 播放 ----------
    def _play(self, data, sr):
        pygame = self._pygame
        snd = pygame.mixer.Sound(buffer=data)
        ch = snd.play()
        if ch is None:
            return
        while ch.get_busy():
            if self._stop.is_set():
                ch.stop()
                raise PlaybackStopped()
            time.sleep(0.005)

    def _log(self, msg):
        log.info(msg)
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                log.debug('日志回调异常', exc_info=True)


def _init_pygame():
    import pygame
    try:
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, CHUNK)
    except Exception:
        pass
    pygame.init()
    if not pygame.mixer.get_init():
        raise RuntimeError('pygame 音频设备初始化失败')
    return pygame


def _put(q, item, stop, force=False):
    """带超时的入队：停止后立刻返回 False，避免永久阻塞。"""
    if force:
        try:
            q.put_nowait(item)
        except queue.Full:
            pass
        return True
    while not stop.is_set():
        try:
            q.put(item, timeout=PUT_TIMEOUT)
            return True
        except queue.Full:
            continue
    return False


def _interruptible_sleep(seconds, stop):
    """可被停止打断的等待"""
    end = time.time() + seconds
    while time.time() < end:
        if stop.is_set():
            return
        time.sleep(min(0.02, max(end - time.time(), 0)))


def _token_weight(key, kind):
    """进度计数：按字符数算，和 total（字符数）保持同一量纲"""
    if kind == 'char':
        return 1
    if kind == 'phrase':
        return len(key)
    return 0


def _hash_name(path):
    import hashlib
    return hashlib.sha1(os.path.abspath(path).encode('utf-8')).hexdigest()[:12]
