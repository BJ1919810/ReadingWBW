# coding=utf-8
"""离线语音合成：为语音包补齐缺失的音节。

思路：把音节拆成 (F0 声调轮廓) x (频谱段内容)，再重新组合。
    段内容取自同一基础音节的已有录音（元音、声母、音色都是原声）；
    声调轮廓取自说话人自己对目标声调的统计模板。

基频变换用 TD-PSOLA（时域基频同步叠加）而不是声码器：
波形直接取自原音原始采样，只重排时间位置，不做频域重建。

    声码器路线（cheaptrick + d4c + synthesize）在这批素材上实测往返
    SNR=-4.3dB、LSD=16.3dB，重建出的声音被噪声污染 ——
    原因是该版本 pyworld 的 d4c 输出有约 15% 的频点是 NaN。
"""
from .psola import psola_resynth
from .tone_synth import (build_templates, compose, decompose, load_audio,
                          synth_neutral, synth_tone, validate_syllable)

__all__ = ['psola_resynth', 'build_templates', 'compose', 'decompose',
           'load_audio', 'synth_neutral', 'synth_tone', 'validate_syllable']
