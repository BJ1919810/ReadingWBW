#coding=utf-8-sig
import re,os,easygui
now=os.getcwd()
VNS=os.listdir(now+"\VoicesPackages\\")
VoiceName=easygui.enterbox('现有语音包:\n'+str(VNS)+'\n请输入语音包名称:','请输入语音包名称')
pyl=open(now+"\\temp.data","r",encoding='utf-8-sig').read()
#print(orig)
def voices(a):#转拼音
    try:
        c=re.search(a+'.*?,',pyl).group().strip(',').strip(a)
        return c+'.ogg'
    except:
        return 'cnmlolololololol.ogg'
while 1:
    t=input('字:')
    for i in t:
        py=voices(i)
        print(py)
        if py in os.listdir(now+'\\VoicesPackages\\'+VoiceName):
            print('在呢。')
            v=now+"\\VoicesPackages\\"+VoiceName+"\\"+py
            os.system(v)
        else:
            print('鬼！木有！')
    
