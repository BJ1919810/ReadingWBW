# coding=utf-8
"""把本地提交 rebase 到远端之上，并解决 README 冲突。

远端有 4 个本地没有的提交（作者的 README + 删两个数据文件），
直接强推会丢它们，所以先 rebase 过去再强推。
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def git(*args, **kw):
    return subprocess.run(['git'] + list(args), capture_output=True,
                          text=True, encoding='utf-8', errors='replace', **kw)


# 1) 备份合并后的 README（解决冲突时用）
readme = io.open('README.md', encoding='utf-8').read()

# 2) 提交尚未提交的路径修复
git('add', '-A')
r = git('commit', '-m', '文件对话框默认目录改用程序所在目录（冻结后是 exe 目录，不是临时解包目录）')
print('提交:', 'ok' if r.returncode == 0 else r.stdout + r.stderr)

# 3) rebase：把 e665a10 之后的提交移到 origin/master 之上
r = git('rebase', '--onto', 'origin/master', 'e665a10', 'master')
print('rebase rc =', r.returncode)
out = r.stdout + r.stderr
print(out[-800:])

# 4) 有冲突就用备份的 README 解决
if r.returncode != 0:
    status = git('status', '--porcelain')
    if 'README.md' in status.stdout:
        io.open('README.md', 'w', encoding='utf-8').write(readme)
        git('add', 'README.md')
        while True:
            c = git('rebase', '--continue', env=dict(os.environ,
                                                    GIT_EDITOR='true'))
            if c.returncode == 0:
                print('冲突已解决')
                break
            if 'README.md' in git('status', '--porcelain').stdout:
                io.open('README.md', 'w', encoding='utf-8').write(readme)
                git('add', 'README.md')
                continue
            print('rebase --continue 失败:', c.stdout + c.stderr)
            break
    else:
        print('冲突不在 README.md，需人工处理：')
        print(status.stdout[:500])

print()
print('=== 结果 ===')
print(git('log', '--oneline', '-10').stdout)
print('工作区:', repr(git('status', '--porcelain').stdout[:200]))
