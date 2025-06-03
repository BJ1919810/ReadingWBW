# coding=utf-8-sig
import os, re, time, tkinter, pygame, sys, threading, easygui, pickle
from tkinter.filedialog import askopenfilename

pygame.init()

now = os.getcwd()

VNS = os.listdir(now + "\\VoicesPackages\\")
# VoiceName=easygui.enterbox('现有语音包:\n'+str(VNS)+'\n请输入语音包名称:','请输入语音包名称')
VoiceName = "hanser"

fff = tkinter.Tk()
fff.withdraw()
fp = askopenfilename(title='请选择您的阅读文件~', filetypes=[('TXT', '*.txt'), ('All Files', '*')],
                     initialdir=os.getcwd())

for i in ['utf-8-sig', 'gbk']:
    try:
        f = open(fp, "r", encoding=i)
        p = f.read().replace('\n', '').replace(',', '，').replace('!', '！').replace('?', '？').replace('——', '，').replace(
            '......', '，').lower()  # 原稿
        break
    except FileNotFoundError:
        sys.exit()
    except UnicodeDecodeError:
        continue

py = open(now + "\\WTV.data", "rb")
py = pickle.load(py)  # 拼音库

try:
    phrases = os.listdir(now + "\\VoicesPackages\\" + VoiceName + "\\phrases")
    phrases = [i.replace(".ogg", "") for i in phrases]  # 词组库
except:
    sys.exit()


def voices(a):  # 转拼音
    try:
        c = re.search(a + '.*?,', py).group().strip(',').strip(a)
        return c
    except:
        return ' '


def checks(s, id):  # 检查是否为词组
    for i in range(len(s)):
        if p[id + i] != s[i]:
            return False
    return s


bj = []


def num(numbs):  # 读数字
    if len(numbs) >= 16:
        numbs = numbs.replace("$", '')
        for i in numbs:
            bj.append(voices(i))
    else:
        numbs = numbs.split("$")
        lz = len(numbs)
        if lz == 3:
            sign = len(numbs[0])
            for i in numbs[0]:
                bj.append(voices(i))
                if sign == 5:
                    bj.append(voices("万"))
                elif sign == 4:
                    bj.append(voices("千"))
                elif sign == 3:
                    bj.append(voices("百"))
                elif sign == 2:
                    bj.append(voices("十"))
                sign -= 1
            bj.append(voices("亿"))
            lz -= 1
            numbs.remove(numbs[0])
        if lz == 2:
            sign = len(numbs[0])
            for i in numbs[0]:
                bj.append(voices(i))
                if sign == 4:
                    bj.append(voices("千"))
                elif sign == 3:
                    bj.append(voices("百"))
                elif sign == 2:
                    bj.append(voices("十"))
                sign -= 1
            bj.append(voices("万"))
            lz -= 1
            numbs.remove(numbs[0])
        if lz == 1:
            sign = len(numbs[0])
            for i in numbs[0]:
                bj.append(voices(i))
                if sign == 4:
                    bj.append(voices("千"))
                elif sign == 3:
                    bj.append(voices("百"))
                elif sign == 2:
                    bj.append(voices("十"))
                sign -= 1


def toPinYin():
    id = 0
    pd = False
    nums = ""
    while id < len(p):
        pds = []
        try:
            if '0' <= p[id] <= '9':
                nums += p[id]
                id += 1
                continue
            elif (not '0' <= p[id] <= '9') and nums != "":  # 断开数字
                nums = list(nums[::-1])
                for fu in range(len(nums)):
                    if fu == 4:
                        nums.insert(4, "$")
                    elif fu == 8:
                        nums.insert(9, "$")
                nums = ''.join(nums)[::-1]
                num(nums)
                nums = ""
            for i in phrases:
                lol = checks(i, id)
                if lol:
                    pds.append(lol)
            if pds != []:
                pd = max(pds, key=len, default='')
                raise UserWarning
        except UserWarning:
            bj.append(pd)
            # print(pd)
            id += len(pd)
        else:
            bj.append(voices(p[id]))  # 直接拼音
            id += 1
    if nums != "":
        nums = list(nums[::-1])
        for fu in range(len(nums)):
            if fu == 4:
                nums.insert(4, "$")
            elif fu == 8:
                nums.insert(9, "$")
        nums = ''.join(nums)[::-1]
        num(nums)
        nums = ""


threading.Thread(target=toPinYin).start()


def isActionTime(lastTime, interval):
    if lastTime == 0:
        return True
    currentTime = time.time()
    return currentTime - lastTime >= interval


Nothave = []


def getsd(fool):
    if fool == ' ':
        return pygame.mixer.Sound(now + "/VoicesPackages/" + VoiceName + "/空.ogg")
    try:
        sd = pygame.mixer.Sound(now + "/VoicesPackages/" + VoiceName + "/" + fool + ".ogg")
    except FileNotFoundError:
        try:
            sd = pygame.mixer.Sound(now + "/VoicesPackages/" + VoiceName + "/phrases/" + fool + ".ogg")
        except FileNotFoundError:
            sd = pygame.mixer.Sound(now + "/VoicesPackages/" + VoiceName + "/空.ogg")
            if fool not in Nothave:
                Nothave.append(fool)
                print('未收录:' + fool)
    sd.set_volume(0.7)
    return sd


id = 1  # 读取index
lt = 0
itv = 0
sd = []
sd.append(getsd(bj[0]))
pid = 0  # 正在读的id
while pid < len(bj):
    if not isActionTime(lt, itv):
        if id < len(bj) and id <= pid + 20:
            sd.append(getsd(bj[id]))
            id += 1
        continue
    lt = time.time()
    lol = sd.pop(0)
    lol.play()
    itv = lol.get_length()
    del lol
    pid += 1
time.sleep(1)
