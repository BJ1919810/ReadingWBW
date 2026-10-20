# coding=utf-8
"""tkinter 界面。"""
import os
import queue
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import paths
from .player import Player
from .pinyin_map import detect_encoding

log = logging.getLogger(__name__)

TEXT_FILTER = [('TXT', '*.txt'), ('所有文件', '*.*')]


class ReaderApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('读书姬 2.0')
        self.root.geometry('720x520')
        self.root.minsize(560, 420)

        self.current_path = None
        self.player = None
        self.msg_q = queue.Queue()
        self._user_stopped = False

        self._build()
        self.root.after(100, self._drain)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    # ---------- 界面 ----------
    def _build(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill='x')
        ttk.Label(top, text='语音包').pack(side='left')
        self.pack_var = tk.StringVar()
        packs = paths.available_packs()
        self.pack_combo = ttk.Combobox(top, textvariable=self.pack_var,
                                      values=packs, state='readonly', width=18)
        self.pack_combo.pack(side='left', padx=(6, 0))
        if packs:
            self.pack_var.set(packs[0])

        ttk.Button(top, text='打开文件…', command=self.open_file).pack(side='right')
        ttk.Button(top, text='停止', command=self.stop).pack(side='right', padx=6)
        self.start_btn = ttk.Button(top, text='开始朗读', command=self.start)
        self.start_btn.pack(side='right')
        self.phoneme_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text='音素级补齐',
                        variable=self.phoneme_var).pack(side='left', padx=(12, 0))

        self.file_var = tk.StringVar(value='未选择文件')
        ttk.Label(self.root, textvariable=self.file_var, padding=(10, 0)).pack(fill='x')

        self.progress = ttk.Progressbar(self.root, mode='determinate')
        self.progress.pack(fill='x', padx=10, pady=(6, 0))

        self.status_var = tk.StringVar(value='就绪')
        ttk.Label(self.root, textvariable=self.status_var, padding=(10, 6)).pack(fill='x')

        paned = ttk.PanedWindow(self.root, orient='vertical')
        paned.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        self.log_box = tk.Text(paned, height=8, wrap='word', state='disabled',
                               font=('Consolas', 9))
        paned.add(self.log_box, weight=1)

        self.text_box = tk.Text(paned, height=12, wrap='word', state='disabled',
                                font=('Microsoft YaHei', 10))
        paned.add(self.text_box, weight=3)

    # ---------- 行为 ----------
    def open_file(self):
        path = filedialog.askopenfilename(title='请选择要朗读的文本文件',
                                          filetypes=TEXT_FILTER,
                                          initialdir=self._last_dir())
        if not path:
            return
        self.current_path = path
        self.file_var.set(os.path.basename(path))

    def _last_dir(self):
        r"""文件对话框的默认目录。

        用 USER_DIR（程序所在目录），不是 BASE_DIR ——
        打包成 exe 后 BASE_DIR 是临时解包目录（AppData\Local\Temp\_MEIxxxx），
        弹出来是个用不了的临时文件夹。小说 txt 就在 exe 旁边，
        默认打开那里才对。
        """
        if self.current_path and os.path.isdir(os.path.dirname(self.current_path)):
            return os.path.dirname(self.current_path)
        d = paths.USER_DIR
        return d if os.path.isdir(d) else os.getcwd()

    def start(self):
        if self.player and self.player.running:
            messagebox.showinfo('提示', '正在朗读中')
            return
        if not self.current_path:
            messagebox.showwarning('提示', '请先选择一个 TXT 文件')
            return
        pack = self.pack_var.get()
        if not pack:
            messagebox.showwarning('提示', '没有可用的语音包')
            return
        try:
            text, enc = detect_encoding(self.current_path)
        except Exception as exc:
            messagebox.showerror('读取失败', '无法读取文件：%s' % exc)
            return
        if not text.strip():
            messagebox.showwarning('提示', '文件是空的')
            return

        self.text_box.configure(state='normal')
        self.text_box.delete('1.0', 'end')
        self.text_box.insert('1.0', text[:20000])
        self.text_box.configure(state='disabled')
        self._clear_log()
        self._user_stopped = False

        self.player = Player(pack, on_progress=self._on_progress,
                             on_log=self._on_log,
                             use_phoneme=self.phoneme_var.get())
        try:
            self.player.start(text, self.current_path)
        except Exception as exc:
            messagebox.showerror('启动失败', str(exc))
            return
        self.status_var.set('朗读中…（编码 %s）' % enc)
        self.start_btn.configure(state='disabled')

    def stop(self):
        self._user_stopped = True
        if self.player:
            self.player.stop()
        self.status_var.set('已停止')
        self.start_btn.configure(state='normal')

    # ---------- 回调 ----------
    def _on_progress(self, done, total):
        self.msg_q.put(('progress', done, total))

    def _on_log(self, msg):
        self.msg_q.put(('log', msg))

    def _drain(self):
        try:
            while True:
                item = self.msg_q.get_nowait()
                if item[0] == 'progress':
                    _, done, total = item
                    pct = min(100.0, 100.0 * done / max(total, 1))
                    self.progress['value'] = pct
                elif item[0] == 'log':
                    self._append_log(item[1])
                    if '朗读结束' in item[1]:
                        self.start_btn.configure(state='normal')
                        if self.player and self.player.error:
                            self.status_var.set('出错结束')
                            messagebox.showerror('朗读出错', str(self.player.error))
                        elif self._user_stopped:
                            self.status_var.set('已停止')
                        else:
                            self.status_var.set('已结束')
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _append_log(self, msg):
        self.log_box.configure(state='normal')
        self.log_box.insert('end', msg + '\n')
        self.log_box.see('end')
        self.log_box.configure(state='disabled')

    def _clear_log(self):
        self.log_box.configure(state='normal')
        self.log_box.delete('1.0', 'end')
        self.log_box.configure(state='disabled')

    def _on_close(self):
        if self.player:
            self.player.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    ReaderApp().run()


if __name__ == '__main__':
    main()
