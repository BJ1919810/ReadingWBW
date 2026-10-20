# coding=utf-8
"""一条命令跑完全部体检。

    python tools/check_all.py            # 全部检查
    python tools/check_all.py -q         # 只看结论
    python tools/check_all.py 覆盖率 融合度   # 只跑指定项

有检查不通过时退出码为 1 —— 可以直接挂到 CI 或 git hook 上。
"""
import sys
import time

from _common import ROOT   # noqa: F401  (自动把项目根加入 sys.path)
from checks import ALL_CHECKS


def main(argv):
    only = [a for a in argv[1:] if not a.startswith('-')]
    quiet = '-q' in argv[1:]

    selected = [(n, f) for n, f in ALL_CHECKS if not only or n in only]
    if not selected:
        print('没有匹配的检查项。可用：%s' % ' / '.join(n for n, _ in ALL_CHECKS))
        return 2

    print('=' * 68)
    print('读书姬 体检  (%d 项)' % len(selected))
    print('=' * 68)

    results = []
    t0 = time.time()
    for name, fn in selected:
        try:
            _, ok, value, detail = fn()
        except Exception as exc:
            ok, value, detail = False, '异常: %s' % exc, ''
        results.append((name, ok, value, detail))
        if not quiet:
            print('  [%-4s] %-12s %-34s %s'
                  % ('PASS' if ok else 'FAIL', name, value, detail))
        else:
            print('  [%-4s] %-12s %s' % ('PASS' if ok else 'FAIL', name, value))

    dt = time.time() - t0
    nfail = sum(1 for _, ok, _, _ in results if not ok)
    print('-' * 68)
    print('  %d/%d 通过，用时 %.1fs' % (len(results) - nfail, len(results), dt))
    if nfail:
        print('  失败项：%s' % '、'.join(n for n, ok, _, _ in results if not ok))
    return 1 if nfail else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
