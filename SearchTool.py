# coding=utf-8
"""拼音/录音速查工具。

用法：
    python SearchTool.py              # 交互模式
    python SearchTool.py 椎名樱       # 直接查一段文字
    python SearchTool.py -p 椎       # 只看拼音，不播放
    python SearchTool.py -l           # 列出语音包

原来的版本读的是仓库里并不存在的 temp.data，一运行就崩；
现在直接用 voice_reader 的资源索引，和主程序共用同一套逻辑。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from voice_reader import paths
from voice_reader.assets import AssetIndex
from voice_reader.audio_io import load_audio
from voice_reader.pinyin_map import (load_wtv_map, load_overrides, convert_to_pinyin)


def play(path):
    """播放一个音频文件（跨平台）"""
    if not path:
        return False
    try:
        import pygame
        pygame.mixer.pre_init(48000, -16, 1, 512)
        pygame.init()
        data, sr = load_audio(path, target_sr=48000)
        snd = pygame.mixer.Sound(buffer=data.astype('float32').tobytes())
        snd.play()
        import time
        time.sleep(snd.get_length())
        pygame.quit()
        return True
    except Exception as exc:
        print('  播放失败：%s' % exc)
        return False


def lookup(index, text, wtv, overrides, do_play=True):
    py = convert_to_pinyin(text, wtv, None, overrides)
    print('%-12s -> %s' % (text, ' '.join(p for p in py if p)))
    for ch, pinyin in zip(text, py):
        if not pinyin or pinyin == ch:
            continue
        path = index.syllable(pinyin)
        origin = '原包'
        if path is None:
            alt = wtv.get(ch, '')
            if alt and alt != pinyin:
                path = index.syllable(alt)
                if path:
                    origin = '备选读音 %s' % alt
        if path is None:
            print('  %s  %-10s [未收录]' % (ch, pinyin))
            continue
        tag = '[补齐]' if pinyin in index.generated else '[%s]' % origin
        print('  %s  %-10s %s  %s' % (ch, pinyin, tag, os.path.basename(path)))
        if do_play:
            play(path)


def main(argv):
    packs = paths.available_packs()
    if not packs:
        print('没有找到可用语音包')
        return 1

    do_play = True
    args = [a for a in argv[1:]]
    if '-p' in args:
        args.remove('-p')
        do_play = False
    if '-l' in args:
        for p in packs:
            idx = AssetIndex(p)
            print('%-10s %s' % (p, idx.coverage()))
        return 0

    pack = packs[0]
    wtv = load_wtv_map()
    overrides = load_overrides()
    index = AssetIndex(pack)

    if args:
        lookup(index, ' '.join(args), wtv, overrides, do_play)
        return 0

    print('语音包: %s   (Ctrl+C 退出)' % pack)
    try:
        while True:
            s = input('字> ').strip()
            if not s:
                continue
            if s in ('q', 'quit', 'exit'):
                break
            lookup(index, s, wtv, overrides, do_play)
    except (KeyboardInterrupt, EOFError):
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
