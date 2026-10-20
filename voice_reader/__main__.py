# coding=utf-8
"""入口。

    python -m voice_reader            启动图形界面
    python -m voice_reader --check    资源自检（不开界面），退出码表示结果
    python -m voice_reader --check --report <文件>   自检结果写到文件
    python -m voice_reader --play <文件>   朗读一个 txt 后退出（打包冒烟测试）

--check / --play 主要是给打包后的 exe 用的：窗口程序没有控制台，
所以结果同时写进报告文件，便于脚本判断。

注意：这里用的是【绝对导入】。PyInstaller 打包时会把本文件当脚本直接执行，
相对导入（from . import paths）会因为没有父包而失败。
"""
import os
import sys


def _check(report_path=None):
    """资源自检：语音包能否加载、索引是否可用、能否读出一段文本"""
    from voice_reader import paths
    from voice_reader.assets import AssetIndex
    from voice_reader.pinyin_map import (load_wtv_map, load_overrides,   # noqa: F401
                                         convert_to_pinyin)

    lines = []
    ok = True

    def item(name, good, detail):
        nonlocal ok
        lines.append('  [%s] %-12s %s' % ('PASS' if good else 'FAIL', name, detail))
        if not good:
            ok = False

    item('资源根目录', os.path.isdir(paths.BASE_DIR), paths.BASE_DIR)
    item('WTV.data', os.path.exists(paths.WTV_DATA), paths.WTV_DATA)
    item('读音表', os.path.exists(paths.PRONUNCIATIONS), paths.PRONUNCIATIONS)

    packs = paths.available_packs()
    item('语音包', bool(packs), ', '.join(packs) if packs else '没有可用语音包')

    # 导入播放链上的所有模块：numpy / soundfile / pygame 在打包后可能缺依赖，
    # 这里提前暴露出来，而不是等用户点"开始朗读"才崩
    # 导入播放链上的所有模块：numpy / soundfile / pygame 在打包后可能缺依赖，
    # 这里提前暴露出来，而不是等用户点"开始朗读"才崩。
    # 用 importlib 而不是 from x import y —— 目的就是"验证能加载"，
    # 不是要用里面的名字（from x import y 会被静态检查判为未使用）。
    try:
        import importlib
        mods = {}
        for name in ('numpy', 'soundfile', 'pygame',
                     'voice_reader.player', 'voice_reader.ui'):
            mods[name] = importlib.import_module(name)
        item('依赖库', True, 'numpy %s / soundfile %s / pygame %s'
             % (mods['numpy'].__version__, mods['soundfile'].__version__,
                mods['pygame'].version.ver))
    except Exception as exc:
        item('依赖库', False, '导入失败: %s' % exc)

    for p in packs:
        try:
            idx = AssetIndex(p)
            cov = idx.coverage()
            item('包 %s' % p, cov['音节(原包)'] > 0, str(cov))
        except Exception as exc:
            item('包 %s' % p, False, '加载失败: %s' % exc)

    try:
        wtv = load_wtv_map()
        ov = load_overrides()
        py = convert_to_pinyin('读书姬测试文本', wtv, None, ov)
        item('转写', len(py) == 7 and all(py), ' '.join(py))
    except Exception as exc:
        item('转写', False, '失败: %s' % exc)

    text = '\n'.join(lines)
    report = '%s\n  结论: %s\n' % (text, '通过' if ok else '有失败项')
    print(report)
    if report_path:
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)
        except OSError as exc:
            print('  报告写入失败: %s' % exc)
    return 0 if ok else 1


def _play(path, report_path=None):
    """朗读一个 txt 后退出 —— 用来冒烟测试打包后的 exe 是否真能出声"""
    import time
    from voice_reader import paths
    from voice_reader.pinyin_map import detect_encoding
    from voice_reader.player import Player

    lines = []
    t_start = time.time()

    def trace(msg):
        # 边跑边落盘：万一卡住，报告里能看到停在哪一步
        line = '  [%5.1fs] %s' % (time.time() - t_start, msg)
        lines.append(line)
        if report_path:
            try:
                with open(report_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines) + '\n')
            except OSError:
                pass

    ok = True
    try:
        text, enc = detect_encoding(path)
    except Exception as exc:
        trace('[FAIL] 读文件 %s: %s' % (path, exc))
        return 1
    trace('读文件 %s (编码 %s, %d 字)' % (os.path.basename(path), enc, len(text)))

    packs = paths.available_packs()
    trace('可用语音包: %s' % (', '.join(packs) if packs else '无'))
    if not packs:
        trace('[FAIL] 没有可用语音包')
        ok = False
    else:
        trace('创建 Player...')
        p = Player(packs[0], on_log=lambda m: trace('  %s' % m))
        trace('启动朗读...')
        p.start(text, path)
        trace('等待朗读结束...')
        p.join(timeout=120)
        trace('朗读线程已结束 alive=%s' % p.running)
        if p.error is not None:
            ok = False
            trace('[FAIL] 朗读异常: %s' % p.error)
        else:
            trace('[PASS] 朗读完成，未收录 %d 个音节' % len(p.missing))
    report = '\n'.join(lines) + '\n  结论: %s\n' % ('通过' if ok else '有失败项')
    print(report)
    if report_path:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    report = None
    if '--report' in argv:
        i = argv.index('--report')
        if i + 1 < len(argv):
            report = argv[i + 1]
    try:
        if '--check' in argv:
            return _check(report)
        if '--play' in argv:
            i = argv.index('--play')
            if i + 1 < len(argv):
                return _play(argv[i + 1], report)
            print('--play 需要一个 txt 文件参数')
            return 2
        from voice_reader.ui import main as ui_main
        ui_main()
        return 0
    except Exception:
        # 窗口程序里未捕获的异常会弹模态错误框，自动化环境下会无限等待。
        # 自己接住，写进报告文件。
        import traceback
        tb = traceback.format_exc()
        if report:
            try:
                with open(report, 'w', encoding='utf-8') as f:
                    f.write(tb)
            except OSError:
                pass
        try:
            print(tb)
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    sys.exit(main())
