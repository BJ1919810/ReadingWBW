# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件、无控制台窗口的 Windows 程序。

    pyinstaller voice_reader.spec

要点：
  * 资源（语音包 / WTV.data / 读音表）整包带进去，别人拿到 exe 直接能跑
  * 排除只用于离线构建的 scipy / pyworld / voice_synth —— 运行时用不到，
    去掉能把 exe 缩小一大截
  * 语音包里的"待切/"是切音节用的原始素材（140MB，含第三方下载音频），
    运行时完全用不到，不打进 exe
  * windowed（无控制台窗口）适合 GUI 程序；自检走 --check --report 写文件
"""
import os
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.getcwd())
PACKS = os.path.join(ROOT, 'VoicesPackages')

# ---- 随包分发的数据 ----
datas = [
    (os.path.join(ROOT, 'WTV.data'), '.'),
    (os.path.join(ROOT, 'pronunciations.json'), '.'),
]

# 语音包：只收顶层音频、phrases、_generated、assets.json
# 跳过 "待切/" 之类的源素材目录
#
# 注意 datas 的语义：传目录时，PyInstaller 会把【目录内容】平铺到目标目录。
# 所以 phrases / _generated 必须各自指定到自己的子目录，
# 否则它们的 ogg 会被倒进包根目录，还和顶层同名文件互相覆盖。
for pack in sorted(os.listdir(PACKS)) if os.path.isdir(PACKS) else []:
    pdir = os.path.join(PACKS, pack)
    if not os.path.isdir(pdir):
        continue
    rel = 'VoicesPackages/%s' % pack
    for name in sorted(os.listdir(pdir)):
        full = os.path.join(pdir, name)
        if os.path.isfile(full) and name.endswith(('.ogg', '.json')):
            datas.append((full, rel))
        elif os.path.isdir(full) and name in ('phrases', '_generated',
                                              '_generated_phoneme'):
            datas.append((full, '%s/%s' % (rel, name)))

# ---- 运行时用不到的，直接排除 ----
excludes = [
    'scipy', 'pyworld', 'voice_synth',
    # 本机 setuptools 版本有问题：pkg_resources.extern 缺失，
    # 而 PyInstaller 的 rthook 会在启动时 import 它 -> 直接崩
    'pkg_resources',
    'matplotlib', 'pandas', 'PIL', 'IPython', 'jupyter', 'notebook',
    'pytest', 'setuptools', 'pip', 'wheel', 'sqlite3', 'test',
    'lib2to3', 'unittest', 'email', 'http', 'xmlrpc',
]

hiddenimports = collect_submodules('pypinyin')
# numpy 的 Cython 层在运行时 import secrets，静态分析看不到，必须显式带上
hiddenimports += ['secrets', 'hmac', 'base64', 'random', 'statistics']

a = Analysis(
    ['voice_reader/__main__.py'],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='读书姬',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # 音频资源多，UPX 收益小还会拖慢启动
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # GUI 程序，不弹控制台
    # 关掉 PyInstaller 的模态错误框：自动化环境下没人点它，会一直挂着
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
