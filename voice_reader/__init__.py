# coding=utf-8
"""读书姬 —— 用二次元语音包朗读中文 TXT。

运行时（voice_reader/）：
    paths         资源路径与共享常量
    audio_io      音频读写（运行时与离线工具共用）
    pinyin_map    文本 -> 发音单元（pypinyin 上下文转写 + 磁盘缓存 + 词组切分）
    assets        语音包索引（原包录音 + 离线补齐 + 词组）
    player        播放引擎（预取线程 + 事件驱动，无忙等）
    ui            tkinter 界面

离线合成（voice_synth/，运行时不会加载）：
    psola         TD-PSOLA 基频变换
    tone_synth    声调重组引擎
"""
__version__ = '2.1.0'
