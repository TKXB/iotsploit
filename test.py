from pwn import *
def remotesshgetfile():
    shell = ssh(host='198.18.34.1', user='root', port=22, password='')
    io = shell.process('sh')
    io.sendline('cat /var/some.tar;exit;')
    with open("./some.tar","wb") as file:
        file.write(io.recvall())
        file.flush()
        file.close()
        
def localsshgetfile():
    io = process(['ssh','root@198.18.34.1'])
    io.sendline("cat /var/my/123;exit;")
    with open("./123","wb") as file:
        file.write(io.recvall())
        file.flush()
        file.close()
    
if __name__ == "__main__":
    shell = ssh(host='198.18.34.1', user='root', port=22, password='')



