# coding=utf-8
"""一键打包成 exe。

    python tools/build_exe.py            # 构建
    python tools/build_exe.py --test     # 构建后自动跑 --check / --play 冒烟

产物：dist/读书姬.exe（单文件，双击即用，目标机器无需装 Python）
"""
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, 'voice_reader.spec')
DIST = os.path.join(ROOT, 'dist')
BUILD = os.path.join(ROOT, 'build')
EXE = os.path.join(DIST, '读书姬.exe')


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, **kw)


def kill_stale():
    """exe 还在跑的话会锁住文件，导致构建失败"""
    run(['taskkill', '/F', '/IM', '读书姬.exe'],
        capture_output=True, encoding='utf-8', errors='replace')
    time.sleep(1)


def main(argv):
    if not os.path.exists(SPEC):
        print('找不到 %s' % SPEC)
        return 1
    try:
        import importlib
        importlib.import_module('PyInstaller')
    except ImportError:
        print('缺少 PyInstaller：pip install pyinstaller')
        return 1

    kill_stale()
    shutil.rmtree(BUILD, ignore_errors=True)
    shutil.rmtree(DIST, ignore_errors=True)

    print('开始打包（约 30~60 秒）…')
    t0 = time.time()
    r = run([sys.executable, '-m', 'PyInstaller', SPEC, '--noconfirm', '--clean'],
            capture_output=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print('打包失败：')
        print((r.stdout or '')[-1500:])
        print((r.stderr or '')[-1500:])
        return 1
    print('打包完成，用时 %.0fs' % (time.time() - t0))

    if not os.path.exists(EXE):
        print('没有生成 exe')
        return 1
    print('  %s  %.1f MB' % (EXE, os.path.getsize(EXE) / 1e6))

    if '--test' in argv:
        print()
        print('冒烟测试…')
        smoke = os.path.join(ROOT, '_smoke_test.txt')
        with open(smoke, 'w', encoding='utf-8') as f:
            f.write('我们一起去图书馆看书吧。')
        try:
            rep = os.path.join(DIST, 'play_report.txt')
            r = run([EXE, '--play', smoke, '--report', rep], timeout=180)
            ok = r.returncode == 0
            if ok and os.path.exists(rep):
                with open(rep, encoding='utf-8') as f:
                    print(f.read())
            else:
                print('  朗读冒烟失败，退出码 %s' % r.returncode)
            return 0 if ok else 1
        finally:
            if os.path.exists(smoke):
                os.remove(smoke)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
