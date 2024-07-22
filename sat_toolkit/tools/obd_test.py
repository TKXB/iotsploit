import logging
logger = logging.getLogger(__name__)
from sat_toolkit.tools.sat_utils import *
import socket
import os
import types
import struct
import time 
import random
import traceback

Shost = "169.254.19.1"
# Shost = "169.254.15.118"
Sport = 13400
errorcode = 0
prommod = 0

pincode2701 = {
0x1B61 :'424D533031',
0x1253 :'57F98CB834',
0x1B75 :'4D0713A342',
0x1B74 :'E2F17A2408',
0x1251 :'4291BD29FC',
0x1B76 :'87D9F6551F',
0x1B21 :'AF5641471E',
0x1B73 :'AEC142E8BE',
0x1BBC :'98738B9F0A',
0x1B79 :'A3A5B165B8',
0x1B78 :'66AD0A6158',
0x1B7A :'5B13E9D097',
0x1672 :'5341533031',
0x1B72 :'53574D3031'
}

efpincode2701 = {
0x1B61 :'424D533031',
0x1672 :'5341533031',
0x1B72 :'53574D3031'
}
erroview = {
0x11:'ServiceNotSupported/服务不支持，诊断仪发送的请求消息中服务标识符无法识别或不支持',
0x12:'SubFunctionNotSupported/不支持子服务，诊断仪发送的请求消息中子服务无法识别或不支持',
0x13:'IncorrectMessageLengthOrInvalidFormat/不正确的消息长度或无效的格式，请求消息长度与特定服务规定的长度不匹配或者是参数格式与特定服务规定的格式不匹配',
0x21:'BusyRepeatRequest/重复请求忙，表明ECU太忙而不能去执行请求。一般来说，在这种情况下，诊断仪应进行重复请求工作',
0x22:'conditionsNotCorrect/条件不正确，表明ECU的状态条件不允许支持该请求',
0x24:'requestSequenceError/请求序列错误，表明收到的是非预期的请求消息序列',
0x25:'noResponseFromSubnetComponent/子网节点无应答，表明ECU收到请求，但所请求的操作无法执行',
0x26:'failurePreventsExecutionOfRequestedAction/故障阻值请求工作执行，表明请求的动作因一故障原因而没有执行',
0x31:'requestOutOfRange/请求超出范围，请求消息包含一个超出允许范围的参数，或者是不支持的数据标识符/例程标识符的访问',
0x33:'securityAccessDenied/安全访问拒绝，诊断仪无法通过ECU的安全策略',
0x35:'invalidKey/密钥无效，诊断仪发送的密钥与ECU内存中的密钥不匹配',
0x36:'exceedNumberOfAttempts/超出尝试次数，诊断仪尝试获得安全访问失败次数超过了ECU安全策略允许的值',
0x37:'requiredTimeDelayNotExpired/所需时间延迟未到，在ECU所需的请求延迟时间过去之前诊断仪又执行了一次请求',
0x70:'uploadDownloadNotAccepted/不允许上传下载，表明试图向ECU内存上传/下载数据失败的原因是条件不允许',
0x71:'transferDataSuspended/数据传输暂停，表明由于错误导致数据传输操作的中止',
0x72:'generalProgrammingFailure/一般编程失败，表明在不可擦除的内存设备中进行擦除或编程时ECU检测到错误发生',
0x73:'wrongBlockSequenceCounter/错误的数据块序列计数器，ECU在数据块序列计数序列中检测到错误发生',
0x78:'requestCorrectlyReceived-ResponsePending/正确接收请求消息-等待响应 表明ECU正确接收到请求消息，但是将执行的动作未完成且ECU未准备好接收其它请求',
0x7E:'subFunctionNotSupportedInActiveSession/激活会话不支持该子服务，当前会话模式下ECU不支持请求的子服务',
0x7F:'serviceNotSupportedInActiveSession/激活会话不支持该服务，当前会话模式下ECU不支持请求的服务',
0x92:'voltageTooHigh/电压过高，当前电压值超过了编程允许的最大门限值',
0x93:'voltageTooLow/电压过低，当前电压值低于了编程允许的最小门限值'}

s = socket.socket()
def logout(str,logname='debug.log'):        #输出日志
    try:
        file = open(logname,'rt+')
    except:
        s = open(logname,'wb')
        s.close()
        file = open(logname,'rt+')

    file.seek(0,2)      #移动文件末尾
    file.write(str+'\r\n')    #写完回车
    file.flush()    #刷新缓冲区，将数据写入文件
    file.close()
    print(str)

def doipmake(myid,targetid,udscmd):                #生成doip报文
    data = b'\x02\xfd'  #ver 
    data += struct.pack(">H",0x8001) #msg type
    allbuf = struct.pack(">H",myid) 
    allbuf += struct.pack(">H",targetid)
    if type(udscmd) == type('a'):
        pay = bytes.fromhex(udscmd)
    else :
        pay = udscmd
    allbuf += pay
    data += struct.pack(">I",len(allbuf))
    data += allbuf
    return data

def resetuds():
    wakeupdata = bytes([0x02,0xfd,0x00,0x05,0x00,0x00,0x00,0x07,0x0e,0x80,0x00,0x00,0x00,0x00,0x00])
    livedata = bytes([0x02, 0xfd, 0x80, 0x01, 0x00, 0x00, 0x00, 0x06, 0x0e, 0x80, 0x1f, 0xff, 0x3e, 0x80])
    s.close()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((Shost,Sport))
    s.settimeout(0.1)
    s.send(wakeupdata)
    wakeupreq = s.recv(1024)
    s.send(livedata)
    livemsgreq = s.recv(1024)

def udssend(myid,targetid,udscmd,wait=0.3):
    buf = doipmake(myid,targetid,udscmd)
    # s.settimeout(wait)
    s.settimeout(5)
    try:
        uds_live()
        s.send(buf)
        print('send:',buf.hex())
        uds_ackflag = s.recv(1024)
        time.sleep(wait) #不设置延迟有些命令会报7f 78响应繁忙
        #if udscmd[0]!=0x36:
        request = s.recv(1024)#uds_request
        print('recv:',request.hex())
        if request[-3]==0x7f and request[-1]==0x78:  #繁忙
             print('接收太快，再试一次')
             time.sleep(wait)
             request = s.recv(1024)#uds_request
             print('recv:',request.hex())
        return request
    except Exception as e:
        logout('no request or no mcu or timeout:{}'.format(e))
        #print(traceback.format_exc())
        errorcode = 10
        return 0

def uds_init(fd = 1):         #建立连接
    wakeupdata = bytes([0x02,0xfd,0x00,0x05,0x00,0x00,0x00,0x07,0x0e,0x80,0x00,0x00,0x00,0x00,0x00])       #路由激活
    livedata = bytes([0x02, 0xfd, 0x80, 0x01, 0x00, 0x00, 0x00, 0x06, 0x0e, 0x80, 0x1f, 0xff, 0x3e, 0x80])    #确保处于激活状态
    global errorcode
    global s
    errorcode = 0
    
    try:
        if fd == 1:
            file = open('debug.log','wb')
            file.close()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((Shost,Sport))
        # s.settimeout(0.1)
        s.send(wakeupdata)
        wakeupreq = s.recv(1024)
        s.send(livedata)
        livemsgreq = s.recv(1024)
    except Exception as e:
        logout('cannot connect .vgm uds error:{}'.format(e))
        errorcode = 0xff
        s.close()
        raise_err('cannot connect .vgm uds error')

def uds_live():
    livedata = bytes([0x02, 0xfd, 0x80, 0x01, 0x00, 0x00, 0x00, 0x06, 0x0e, 0x80, 0x1f, 0xff, 0x3e, 0x80])
    try:
      s.send(livedata)
      livemsgreq = s.recv(1024)
    except:
        logout('live error')

def uds_close():
    try:
        s.close()
    except:
        time.sleep(0.01)

def compute_key(seed, pincode):
    #print("Observed seed: ",seed)
    if type(pincode) == type('a'):
        pincodes = bytes.fromhex(pincode)
    else :
        pincodes = pincode
    s1 = pincodes[0]
    s2 = pincodes[1]
    s3 = pincodes[2]
    s4 = pincodes[3]
    s5 = pincodes[4]
    seed_int = int.from_bytes(seed,'big')
    
    or_ed_seed = ((seed_int & 0xFF0000) >> 16) | (seed_int & 0xFF00) | (s1 << 24) | (seed_int & 0xff) << 16

    
    mucked_value = 0xc541a9
    
    for i in range(0,32):
        a_bit = ((or_ed_seed >> i) & 1 ^ mucked_value & 1) << 23
        v9 = v10 = v8 = a_bit | (mucked_value >> 1)
        mucked_value = v10 & 0xEF6FD7 | ((((v9 & 0x100000) >> 20) ^ ((v8 & 0x800000) >> 23)) << 20) | (((((mucked_value >> 1) & 0x8000) >> 15) ^ ((v8 & 0x800000) >> 23)) << 15) | (((((mucked_value >> 1) & 0x1000) >> 12) ^ ((v8 & 0x800000) >> 23)) << 12) | 32 * ((((mucked_value >> 1) & 0x20) >> 5) ^ ((v8 & 0x800000) >> 23)) | 8 * ((((mucked_value >> 1) & 8) >> 3) ^ ((v8 & 0x800000) >> 23))

    
    for j in range(0,32):
        v11 = ((((s5 << 24) | (s4 << 16) | s2 | (s3 << 8)) >> j) & 1 ^ mucked_value & 1) << 23
        v12 = v11 | (mucked_value >> 1)
        v13 = v11 | (mucked_value >> 1)
        v14 = v11 | (mucked_value >> 1)
        mucked_value = v14 & 0xEF6FD7 | ((((v13 & 0x100000) >> 20) ^ ((v12 & 0x800000) >> 23)) << 20) | (((((mucked_value >> 1) & 0x8000) >> 15) ^ ((v12 & 0x800000) >> 23)) << 15) | (((((mucked_value >> 1) & 0x1000) >> 12) ^ ((v12 & 0x800000) >> 23)) << 12) | 32 * ((((mucked_value >> 1) & 0x20) >> 5) ^ ((v12 & 0x800000) >> 23)) | 8 * ((((mucked_value >> 1) & 8) >> 3) ^ ((v12 & 0x800000) >> 23))

    key = ((mucked_value & 0xF0000) >> 16) | 16 * (mucked_value & 0xF) | ((((mucked_value & 0xF00000) >> 20) | ((mucked_value & 0xF000) >> 8)) << 8) | ((mucked_value & 0xFF0) >> 4 << 16)
    print(' ')
    return key.to_bytes(3, 'big')



def progress_bar():
  for i in range(1, 101):
    print("\r", end="")
    print("解密中: {}%: ".format(i), "#" * (i // 2), end="")
    uds_live()
    #sys.stdout.flush()
    time.sleep(0.05)
  print(" ")


def server27(mcuid, mode ,pincode,entermode =b'\x10\x03'):
    senddata = b'\x27'
    senddata += mode.to_bytes(1,'little')
    global errorcode,prommod
    errorcode = 0
    
    #uds_init()
    try:
        prommod = 0
        if prommod !=1:
          print('进入编程模式')
          rev = udssend(0x0e80,mcuid,entermode)#enter program mode
          if type(rev) == type(1):
              logout('program mode error')
              errorcode = 3
              return 3
          if rev[12]==0x7f and len(rev)==15:
              logout('program mode error'+ erroview[rev[-1]])
              errorcode = 3
              return 3
          else :
              prommod = 1
        rev = udssend(0x0e80,mcuid,senddata)
        if type(rev) == type(1):
            time.sleep(3)
            rev = udssend(0x0e80,mcuid,senddata)
        if type(rev) == type(1) :
            logout('error')
            print(traceback.format_exc())
            errorcode = 5
            return 5

        if rev[-1] == 0x37:
                while True:
                    rev = udssend(0x0e80,mcuid,senddata)
                    if rev[-1] != 0x37:
                        break
        if rev[12]!=0x7f:
            seed = rev[-3::]
            print('获得seed数据',seed.hex(),'认证算法计算中')
            #progress_bar()
            key = compute_key(seed,pincode)#build key
            nextmode = mode +1
            senddata = b'\x27'
            senddata+= nextmode.to_bytes(1,'little')
            senddata +=key
            rev = udssend(0x0e80,mcuid,senddata)
            if rev[12]!=0x7f:
                logout('27服务解锁成功')
                errorcode = 0
                return 0
            else:

                if rev[-1]==0x35:
                    logout(erroview[rev[-1]])
                    errorcode = 1
                    return rev[-1]
                elif rev[-1]==0x36:
                    logout(erroview[rev[-1]])
                    errorcode = 6
                    return rev[-1]
                elif rev[-1]==0x37:
                    logout(erroview[rev[-1]])
                    errorcode = 6
                    return rev[-1]
                elif rev[-1]==0x7f:
                    logout(erroview[rev[-1]] +'already clear programmode. try again')
                    errorcode = 6
                    prommod = 0
                    return rev[-1]
                elif rev[-1]==0x12:
                    logout(erroview[rev[-1]])
                    errorcode = 4
                    prommod = 0
                    return rev[-1]
                else:
                    logout(erroview[rev[-1]])
                    errorcode = 6
                    return rev[-1]
        elif rev[-1]==0x7f:
             logout(erroview[rev[-1]] + 'service Not Supported InActive Session . already clear programmode')
             errorcode = 5
             prommod = 0
             return rev[-1]
        elif rev[-1]==0x12:
            logout(erroview[rev[-1]])
            errorcode = 4
            return rev[-1]
        elif rev[-1]==0x13:
            logout(erroview[rev[-1]])
            errorcode = 5
            return rev[-1]
        else :
            logout(erroview[rev[-1]])
            errorcode = 5
            return rev[-1]
    except:
        logout('error')
        print(traceback.format_exc())
        errorcode = 5
        return 5
    #uds_close()

def memmem(a,b,n = 0):
    a_s = len(a)
    b_s = len(b) - a_s + 1
    while n < b_s:
        memb = b[n::]
        if memb[0:a_s] == a :
            return n
            #return memb
        n+=1
    return -1

def getallid():
    allmcuid =[]
    recvx = b''
    recvx+= newallid()
    recvx+= newallid()
    recvx+= newallid()
    recvx+= newallid()
    n = 0
    flag = 0
    idnum = 0
    try:
        while True:
           n = memmem(b'\x0e\x80\x50',recvx,n+4)
           if n == -1:
               break
           idnum = int.from_bytes(recvx[n-2:n],'big')
           flag = 0
           for x in allmcuid:
               if x == idnum:
                   flag = 1
                   break
           if flag == 0:
                   allmcuid.append(idnum)
    except:
        pass
    for i in allmcuid:
        logout('0x{:02X}'.format(i)+',')
    print(len(allmcuid))
    print(allmcuid)
    return allmcuid

def newallid():
    buf = doipmake(0x0e80,0x1fff,'1001')
    s.settimeout(5)
    request = b''
    try:
        s.send(buf)
        print('send:',buf.hex())
        uds_ackflag = s.recv(1024)
        while True:
            request += s.recv(1024)
    except:
        print(request.hex())
        return request
    

def scanid(start,end):
    global errorcode
    allmcuid =[]
    x=start
    while x!=end:
        er= udssend(0x0e80,x,b'\x10\x01',wait = 0.1)
        if type(res)==type(b'\x11'):
            #print(hex(x))
            if er[0xc] == 0x50:
                allmcuid.append(x)
                logout(hex(x))
        errorcode=0
        x+=1
    return allmcuid



def test27():
    data = b'\x10\x01'
    pincode = bytes([0xFF,0xFF,0xFF,0xFF,0xFF])
    pincode2 = bytes([0x55,0x55,0x55,0x55,0x55])
    mcuid = 0x1b21
    i = 0
    trycount = 0
    howtry = 8
    ci = 0
    #while True:
    # ci = 0
    # mcuid = random.randint(0x0001, 0xffff)
     #if mcuid == 0x1b21:
        # mcuid +=2
     #mcuid =0x1b24
    while ci!=100:
            i = 0
            ci +=1
            logout('test '+ str(hex(mcuid)) + ' 27 mode:' +str(hex(i)))
            uds_live()
            #time.sleep(2)
            server27(mcuid, i ,pincode2)
            if errorcode ==6:
                logout('punish !wait 10s try again')
                prommod = 0
                time.sleep(10)
                trycount+=1
                if(trycount!=howtry):
                   continue
            elif errorcode == 5:
                print('wait 2s try again')
                #time.sleep(2)
                trycount+=1
                if(trycount!=howtry):
                   continue
            elif errorcode == 0 or errorcode == 1:
                i+=1
            i+=1
            trycount=0

def scan22(mcu,mode = 1):
    n= 0
    readf0 = 0x0000
    if mode!=1:
        senddata = b'\x10'
        senddata += mode.to_bytes(1,'little')
        udssend(0x0e80,mcu,senddata)
    while readf0!=0x10000:
        data =b'\x22'
        data +=readf0.to_bytes(2,'big')
        logout(data.hex())
        data = udssend(0x0e80,mcu,data,wait = 0.1)
        if type(data)==type(b'\x11'):
            logout(data.hex())
        readf0+=1

def scan2E(mcu,mode = 1):
    n= 0
    readf0 = 0x0000
    if mode!=1:
        senddata = b'\x10'
        senddata += mode.to_bytes(1,'little')
        udssend(0x0e80,mcu,senddata)
    while readf0!=0x10000:
        data =b'\x2E'
        data +=readf0.to_bytes(2,'big')
        data +=b'\x66\x66\x66\x66\x66'
        #uds_live()
        logout(data.hex())
        data = udssend(0x0e80,mcu,data,wait = 0.1)
        if type(data)==type(b'\x11'):
            logout(data.hex())
        readf0+=1

def scan2EXX(mcu,xx,mode = 1):
    n= 0
    readf0 = 0x00
    if mode!=1:
        senddata = b'\x10'
        senddata += mode.to_bytes(1,'little')
        udssend(0x0e80,mcu,senddata)
    while readf0!=0x100:
        data =b'\x2E'
        data +=xx
        data +=readf0.to_bytes(1,'big')
        #uds_live()
        logout(data.hex())
        data = udssend(0x0e80,mcu,data,wait = 0.1)
        if type(data)==type(b'\x11'):
            logout(data.hex())
        readf0+=1

def scan3101(mcu,mode = 1):
    n= 0
    readf0 = 0x0000
    if mode!=1:
        senddata = b'\x10'
        senddata += mode.to_bytes(1,'little')
        udssend(0x0e80,mcu,senddata)
    while readf0!=0x10000:
        data =b'\x31\x01'
        data +=readf0.to_bytes(2,'big')

        #uds_live()
        logout(data.hex())
        data = udssend(0x0e80,mcu,data,wait = 0.1)
        if type(data)==type(b'\x11'):
            logout(data.hex())
        readf0+=1

#2E可写命令长度测试
def check2elen(mcu,did,mode = 1):
    n= 0
    readf0 = 1
    if mode!=1:
        senddata = b'\x10'
        senddata += mode.to_bytes(1,'little')
        udssend(0x0e80,mcu,senddata)
    sdata =b'\x00'
    while readf0!=32:
        data =b'\x2e'
        data +=bytes.fromhex(did)
        data += sdata
        data = udssend(0x0e80,mcu,data,wait = 0.3)
        if type(data)==type(b'\x11'):
            if data[12]!=0x7f:
                return readf0
        readf0+=1
        sdata += b'\x00'
    return 0

def opendebug(mcu = 0x1201,kg=1):
    pincode = b'\xFF\xFF\xFF\xFF\xFF'
    #F6D6D04BDC
    #pincode = b'\x5b\xda\x4e\x31\xfc'
    server27(mcu,0x19,pincode)
    if kg == 1:
       udssend(0x0e80,mcu,b'\x2e\xc0\x3e\x01')
    else:
       udssend(0x0e80,mcu,b'\x2e\xc0\x3e\x00')

def tcamopendebug(mcu = 0x1011,kg=1):
    #pincode = bytes([0xAC,0xB3,0x82,0x91,0xB3])
    #pincode = bytes([0x0A,0xD9,0x9A,0xE7,0x0D])
    pincode = bytes.fromhex('FFFFFFFFFF')
    server27(mcu,0x19,pincode)
    if kg == 1:
       req = udssend(0x0e80,mcu,'3101DC01')
    else:
       req = udssend(0x0e80,mcu,b'\x31\x02\x02\x32')

#34命令测试功能
def makedownloaddata(memaddr,memsize,compress):
    data =b'\x34'
    compressionMethod = compress &0x0f  #0x01含压缩    VBF头那种
    encryptingMethod =  0x00 &0x0f  #0x01含加密    VBF头那种
    dataFormatIdentifier = (compressionMethod << 4) + encryptingMethod 
    memsize_len =  0x04 &0x0f  #大小长度为4
    memaddr_len =  0x04 &0x0f  #地址长度为4
    addressAndLengthFormatIdentifier = (memsize_len << 4) + memaddr_len 
    data += dataFormatIdentifier.to_bytes(1,'big')
    data += addressAndLengthFormatIdentifier.to_bytes(1,'big')
    data += memaddr.to_bytes(4,'big')
    data += memsize.to_bytes(4,'big')
    return data

#一整个上传命令
def download(mcuid,memaddr,writedata,compress = 0x00,wait = 0):
    senddata = makedownloaddata(memaddr,len(writedata),compress)
    req = udssend(0x0e80,mcuid,senddata)
    #req = b'\x02\xFD\x80\x01\x00\x00\x00\x08\x12\x53\x0E\x80\x74\x20\x03\x02'
    sendmax = 0
    if req[12] == 0x7f and len(req)==15:
        print(erroview[req[-1]])
        return 0
    tmp = int.from_bytes(req[13:14],'big')
    tmp = tmp >> 4
    sendmax = int.from_bytes(req[14: 14 +tmp],'big')   #block size
    sendmax -= 2   #去除命令与block占用的两个字节
    filesize = len(writedata)
    if wait == 0:
        waittime = sendmax/0x2a0
        if waittime > 3:waittime = 2.0
    else :
        waittime = wait

    blockcountmax = filesize//sendmax

    for i in range(0,blockcountmax): #块序列 每次递增
            uds_live()
            senddata = b'\x36'
            blockcount = i + 1
            blockcount = blockcount & 0xff
            senddata += blockcount.to_bytes(1,'big')
            senddata += writedata[i * sendmax:i * sendmax + sendmax]
            req = udssend(0x0e80,mcuid,senddata,wait=waittime)

            print('传输中',i,'/',blockcountmax)
    enddata = filesize % sendmax
    if enddata != 0:
            senddata = b'\x36'
            blockcount = blockcountmax +  1
            blockcount = blockcount & 0xff
            senddata += blockcount.to_bytes(1,'big')
            senddata += writedata[blockcountmax * sendmax:blockcountmax * sendmax + enddata]
            req = udssend(0x0e80,mcuid,senddata,wait=waittime)

    req = udssend(0x0e80,mcuid,b'\x37')  #通知传输结束
    if req[12] == 0x7f and len(req)==15:
            print(erroview[req[-1]])
            return 0
    print('完成')
    return 1


#扫隐藏27服务
def scan27server(mculist,entermode = b'\x10\x03'):
    pin = 'FFFFFFFFFF'
    wujiance = 0
    for i in mculist:
        #resetvgm()
        logout(hex(i)+':'+pin)
        udssend(0x0e80,i,entermode)
        for x in range(256):
            if x&1 ==0:
                continue
            rev = udssend(0x0e80,i,'27'+'{:02X}'.format(x),wait=0.3)
            if type(rev)==type(0):
                logout(hex(x) + '无响应')
                wujiance+=1
                if wujiance == 10:
                    wujiance = 0
                    break
                continue
            logout('{:02X}'.format(x)+ ':' + rev.hex())
            wujiance = 0



#扫未知后门拓展服务
def scan10server(mculist):
    wujiance = 0
    for i in mculist:
        resetvgm()
        for x in range(256):
            if x ==2 or x ==0x82:  #or x==98 or x==226
                continue
            rev = udssend(0x0e80,i,'10'+'{:02X}'.format(x),wait=0.3)
            if type(rev)==type(0):
                logout(hex(x) + '无响应')
                wujiance+=1
                if wujiance == 10:
                    wujiance = 0
                    break
                continue
            logout('{:02X}'.format(x)+ ':' + rev.hex())
            wujiance = 0


def scan10_27server(mculist):
    wujiance = 0
    for i in mculist:
        #resetvgm()
        for x in range(256):
            if x ==2 or x ==0x82 or x==98 or x==226:
                continue
            rev = udssend(0x0e80,i,'10'+'{:02X}'.format(x),wait=0.3)
            if type(rev)==type(0):
                logout(hex(x) + '无响应')
                wujiance+=1
                if wujiance == 10:
                    wujiance = 0
                    break
                continue
            logout('{:02X}'.format(x)+ ':' + rev.hex())
            wujiance = 0


#1101、1002
def scan11011002(mculist,cmd = '1002'):
    for i in mculist:
        if i == 0x1001 or i == 0x1201 or i == 0x1A01:
            continue
        ret = udssend(0x0e80,i,cmd,wait=0.3)
        if type(ret)!=type(0):
            logout(hex(i) +'    '+ ret.hex())



#扫未知可读DID服务
def scan22server(mculist,mode):
    for i in mculist:
        #resetvgm()
        scan22(i,mode)
#扫未知可写DID服务
def scan2Eserver(mculist,mode):
    for i in mculist:
        resetvgm()
        scan2E(i,mode)
def scan31server(mculist,mode):
    for i in mculist:
        resetvgm()
        scan3101(i,mode)

#扫vbf签名问题
def scanqianming(mculist):
    for i in mculist:
        #uds_live()
        ret = udssend(0x0e80,i,'1002',wait=1)
        if type(ret)!=type(0):
            logout(ret.hex())
        ret = udssend(0x0e80,i,'22d01c',wait=1)
        if type(ret)!=type(0):
            logout(ret.hex())

#扫弱口令
def scanpincode(mculist):
    for i in mculist:
        if i == 0x1001:
            continue
        try:
            pin =pincode2701[i]
        except:
            pin = '5555555555'
        logout(hex(i)+':'+pin)
        server27(i,0x01,pin,entermode = b'\x10\x02')

#全模块发命令
def allsend(mculist,cmd = '1002'):
    for i in mcu:
        ret = udssend(0x0e80,i,cmd,wait=0.3)
        if type(ret)!=type(0):
            logout(hex(i) +'    '+ ret.hex())

def resetvgm():
    while True:
        ret = udssend(0x0e80,0x1001,'1101',wait=0.3)
        if type(ret)!=type(0):
            if ret[12] != 0x7f:
                break
    uds_close()
    uds_init(0)
    while True:
        time.sleep(0.5)
        ret = udssend(0x0e80,0x1001,'1001',wait=0.3)
        if type(ret)!=type(0):
            if ret[12] != 0x7f:
                break
#读内存
def readmem2314(mcu):
    log22 = open('ddmmemory.bin','wb')
    log22
    server27(mcu,0x05,'C4AC3D769F')
    addr = 0
    while True:
        ret = udssend(0x0e80,mcu,'1002')
    
    while True:
        cmdstr = '2314'
        cmdstr+='{:08X}'.format(addr)+'80'
        ret = udssend(0x0e80,0x1a12,cmdstr)
        if ret[12] == 0x7f:
            log22.close()
            break
        log22.write(ret[13::])
        log22.flush()
        addr +=0x80
             

mcu = [0x1301,0x1212,0x1701,0x1635,0x1B61,0x1023,0x1A11,0x1650,0x1A01,0x1A12,0x1201,0x1253,0x1012,0x1B75,0x1B74,0x1314,0x1630,0x1633,0x1344,0x1BB3,0x1BB4,0x1251,0x1637,0x1A30,0x1B76,0x1631,0x1B21,0x1A13,0x1A15,0x1B77,0x1720,0x1670,0x1BB5,0x1BB7,0x1BB6,0x1A21,0x1310,0x1B78,0x1A22,0x1213,0x1672,0x1A29,0x1A27,0x1A28,0x1C01,0x1614,0x1B72,0x1011,0x1601,0x1015,0x1615,0x1656,0x1001]
#ef1e = ['0x1001', '0x1011', '0x1015', '0x1023', '0x1201', '0x1202', '0x1212', '0x1217', '0x1218', '0x1301', '0x1314', '0x1344', '0x1601', '0x1614', '0x1630', '0x1631', '0x1633', '0x1635', '0x1637', '0x1650', '0x1670', '0x1672', '0x1701', '0x1720', '0x1a01', '0x1a11', '0x1a12', '0x1a13', '0x1a15', '0x1a21', '0x1a22', '0x1a23', '0x1a24', '0x1a27', '0x1a28', '0x1a30', '0x1a31', '0x1a32', '0x1b61', '0x1b72', '0x1bb3', '0x1bb4', '0x1c01']
ef1enew = [4097, 4113, 4117, 4131, 4609, 4610, 4626, 4631, 4632, 4865, 4884, 4932, 5633, 5652, 5680, 5681, 5683, 5685, 5687, 5712, 5744, 5746, 5889, 5920, 6657, 6673, 6674, 6675, 6677, 6689, 6690, 6691, 6692, 6695, 6696, 6704, 6705, 6706, 7009, 7026, 7091, 7092, 7169]
data =b''
bigmcu = [0x1023,0x1a01,0x1201,0x1011,0x1601,0x1015,0x1630,0x1001,0x1301]  #BNCM CEM DHU TCAM VDDM WAM ECM VGM ADCU
bxecu = [
0x1201,
0x1023,
0x1025,
0x1026,
0x1024,
0x1015,
0x1301,
0x1701,
0x1A01,
0x1A15,
0x1601,
0x1BB2,
0x1672,
0x1C01,
0x1631,
0x1A11,
0x1A12,
0x1633,
0x1670,
0x1351,
0x1BB3,
0x1637,
0x1650,
0x1656,
0x1BB4,
0x1212,
0x1A13,
0x1635,
0x1A21,
0x1A22,
0x1A27,
0x1314,
0x1011,
0x1A28,
0x1A30,
0x1350,
0x1330,
0x1331,
0x1344,
0x1317,
0x1001]