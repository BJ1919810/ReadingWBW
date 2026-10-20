# coding=utf-8
"""稳定性压力测试：连续朗读、反复启停、线程泄漏、预取是否跟得上。"""
import os
import time
import threading

from _common import ROOT  # noqa: F401  (导入即把项目根加入 sys.path)
from voice_reader import paths
from voice_reader.player import Player
from voice_reader.pinyin_map import detect_encoding

TXT = os.path.join(paths.ROOT, '原神之可莉小矮砸.txt')


def base_threads():
    return threading.active_count()


def test_restart_leak():
    """反复 开始/停止，检查线程是否泄漏"""
    print('=== 测试1：反复启停是否泄漏线程 ===')
    text = '我们一起去图书馆看书吧，你要喝点什么吗？'
    p = Player('hanser')
    before = base_threads()
    for i in range(6):
        p.start(text)
        time.sleep(0.35)
        p.stop()
        p.join(timeout=5)
        alive = p._thread.is_alive() if p._thread else False
        print('  第%d轮: 停止后线程仍存活=%s  当前线程数=%d' %
              (i + 1, alive, base_threads()))
        time.sleep(0.1)
    time.sleep(1.0)
    after = base_threads()
    print('  启停前线程数=%d  6轮后=%d  泄漏=%d' % (before, after, after - before))
    return after - before


def test_stop_midway():
    """朗读中途停止，验证能干净退出"""
    print()
    print('=== 测试2：中途停止 ===')
    text = '青林抱着自己的手机，狠了狠心输入支付密码，这已经是他氪的第三个648了。'
    p = Player('hanser')
    t0 = time.time()
    p.start(text)
    time.sleep(0.8)
    p.stop()
    p.join(timeout=5)
    print('  停止耗时 %.2fs  线程存活=%s' % (time.time() - t0, p._thread.is_alive()))


def test_long_run():
    """长文本连续朗读，观察是否掉音/卡死/内存涨"""
    print()
    print('=== 测试3：长文本连续朗读（离线推演，不实际出声）===')
    if not os.path.exists(TXT):
        print('  找不到测试文本')
        return
    text, _ = detect_encoding(TXT)
    p = Player('hanser')
    # 只跑 token 生成 + 资源解析，测吞吐与内存
    from voice_reader.pinyin_map import (PhraseIndex, load_wtv_map,
                                          convert_to_pinyin)
    wtv = load_wtv_map()
    py = convert_to_pinyin(text, wtv, None, load_overrides())
    idx = p.index
    ph = PhraseIndex(idx.phrases.keys())
    t0 = time.time()
    n = hit = miss = 0
    for kind, key, alt in ph.iter_tokens(text, py, wtv):
        n += 1
        if kind == 'char':
            if idx.has(key):
                hit += 1
            elif alt and idx.has(alt):
                hit += 1
            else:
                miss += 1
    dt = time.time() - t0
    print('  %d 字 -> %d 个发音单元，切分+解析 %.2fs (%.0f 单元/秒)'
          % (len(text), n, dt, n / max(dt, 1e-9)))
    print('  可播 %d / 缺失 %d' % (hit, miss))


def load_overrides():
    from voice_reader.pinyin_map import load_overrides as lo
    return lo()


if __name__ == '__main__':
    leak = test_restart_leak()
    test_stop_midway()
    test_long_run()
    print()
    print('结论: 线程泄漏 = %d' % leak)
