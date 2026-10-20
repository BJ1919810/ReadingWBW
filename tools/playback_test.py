# coding=utf-8
"""播放链路实测：真的出声，并测时间准确度。"""
import time

from _common import ROOT  # noqa: F401  (导入即把项目根加入 sys.path)
from voice_reader.player import Player

TEXT = '我们一起去图书馆看书吧，你要喝点什么吗？'

p = Player('hanser', on_log=lambda m: print('  [log]', m),
           on_progress=lambda d, t: None)
print('资源:', p.index.coverage())
t0 = time.time()
p.start(TEXT)
p.join(timeout=60)
dt = time.time() - t0
print('朗读 "%s" 用时 %.1fs' % (TEXT, dt))
print('未收录:', sorted(p.missing))
print('备选兜底:', sorted(p.recovered))
print('仍在运行?', p.running)
