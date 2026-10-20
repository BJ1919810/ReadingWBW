# coding=utf-8
"""针对性复现：长文本下生产者线程阻塞导致的泄漏。"""
import time
import threading

from _common import ROOT  # noqa: F401  (导入即把项目根加入 sys.path)
from voice_reader.player import Player

LONG = ('青林抱着自己的手机，狠了狠心输入支付密码，这已经是他氪的第三个648了，'
        '这个月和下个月的生活费都给他充进了游戏里。他看着屏幕上那个熟悉又陌生的'
        '界面，忽然觉得有些不真实，仿佛刚才发生的一切都只是一场梦。' * 40)

print('测试文本 %d 字' % len(LONG))
p = Player('hanser')
before = threading.active_count()
p.start(LONG)
time.sleep(2.0)          # 让生产者把队列塞满
mid = threading.active_count()
print('朗读中线程数: %d (基线 %d)' % (mid, before))
names = [t.name for t in threading.enumerate()]
print('  线程: %s' % names)

p.stop()
p.join(timeout=5)
print('停止后主线程存活=%s' % p._thread.is_alive())
time.sleep(1.5)
after = threading.active_count()
print('停止 1.5s 后线程数: %d  (基线 %d)  泄漏=%d' % (after, before, after - before))
alive = [t.name for t in threading.enumerate() if t.name != 'MainThread']
print('  残留线程: %s' % alive)
for t in alive:
    print('    %s 状态=%s' % (t.name, t.is_alive()))
    if hasattr(t, '_sys'):
        pass
print()
if after > before:
    print('>>> 确认：存在线程泄漏，生产者阻塞在 queue.put()')
else:
    print('>>> 未复现泄漏')
