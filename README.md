# IotSploit

## Initial Setup

1. Clone and switch to dev branch:
```bash
git fetch
git checkout -b dev origin/dev
```

1. Set up Redis:
```bash
docker pull redis
docker run --name sat-redis -p 6379:6379 -d redis:latest
```

2. Install and configure Poetry:
```bash
pip install poetry
poetry lock        # This may take 10-20 minutes
poetry install     # This may take 10-20 minutes
poetry shell
```

3. Initialize Django database:
```bash
python manage.py makemigrations
python manage.py makemigrations sat_toolkit
python manage.py migrate
```

4. Start the application:
```bash
python console.py
```

## PI Install 
```shell

sat@raspberrypi:/etc/udev/rules.d $ cat 51-android.rules
SUBSYSTEM=="usb",ENV{DEVTYPE}=="usb_device", MODE="0666", GROUP="plugdev"

sudo udevadm control --reload-rules
sudo service udev restart
sudo udevadm trigger
adb kill-server
adb start-server


sat@ZeekrSAT:~ $ cat /etc/apt/sources.list.d/raspi.list

deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main contrib non-free non-free-firmware
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-updates main contrib non-free non-free-firmware
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-backports main contrib non-free non-free-firmware
deb https://mirrors.tuna.tsinghua.edu.cn/debian-security bookworm-security main contrib non-free non-free-firmware

deb http://archive.raspberrypi.com/debian/ bookworm main

# Uncomment line below then 'apt-get update' to enable 'apt-get source'
#deb-src http://archive.raspberrypi.com/debian/ bookworm main


sudo apt install -y libglib2.0-dev
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple bluepy

sudo apt update
sudo apt install -y raspi-config
sudo apt install -y adb
sudo apt install -y dsniff
sudo apt install -y hping3
sudo apt install -y xrdp
sudo apt install -y nmap
# sudo apt install -y iptables
sudo apt install -y hostapd
sudo apt upgrade -y
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages django
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages django_extensions
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages pyusb
# sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages bluepy
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages pywifi
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages pwntools
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages netifaces
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages python3-nmap
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --break-system-packages django-cors-headers


python manage.py makemigrations
python manage.py makemigrations sat_toolkit
python manage.py migrate
python manage.py createsuperuser


python manage.py dumpdata sat_toolkit > data_export.json
python manage.py loaddata data_export.json


sudo usermod -a -G bluetooth $(whoami)
```

## django cmd

```shell
#启动django
C:\Users\Cheng.Chang3\AppData\Local\Programs\Python\Python310\python.exe manage.py runserver 0.0.0.0:8000
python manage.py runserver 0.0.0.0:8000

#shell
C:\Users\Cheng.Chang3\AppData\Local\Programs\Python\Python310\python.exe manage.py shell
python manage.py shell


```


```shell
#新建APP
C:\Users\Cheng.Chang3\AppData\Local\Programs\Python\Python310\python.exe manage.py startapp sat_toolkit

#数据模型更新
C:\Users\Cheng.Chang3\AppData\Local\Programs\Python\Python310\python.exe manage.py makemigrations
C:\Users\Cheng.Chang3\AppData\Local\Programs\Python\Python310\python.exe manage.py migrate

#超级管理员
C:\Users\Cheng.Chang3\AppData\Local\Programs\Python\Python310\python.exe  manage.py createsuperuser



#pip安装
C:\Users\Cheng.Chang3\AppData\Local\Programs\Python\Python310\Scripts\pip.exe install -i https://pypi.tuna.tsinghua.edu.cn/simple pywifi


C:\Users\Cheng.Chang3\AppData\Local\Programs\Python\Python310\python.exe  manage.py graph_models sat_toolkit -o sat_toolkit_models.png


```

C:\Users\Cheng.Chang3\AppData\Local\Programs\Python\Python310\python.exe  -m pip install --upgrade pip



在 Django 中可以使用命令行工具 dumpdata 和 loaddata 导出和导入数据。下面是具体的步骤：

导出原 Django 应用的数据。
执行以下命令，将原 Django 应用的数据导出到指定的文件中：

C:\Users\Cheng.Chang3\AppData\Local\Programs\Python\Python310\python.exe manage.py dumpdata sat_toolkit > data_export.json
python manage.py dumpdata sat_toolkit > data.json
这条命令会将整个 Django 应用的数据导出为 JSON 格式的数据到名为 data.json 的文件中。

将数据导入到新的 Django 应用中。
将导出的 data.json 文件复制到新的 Django 应用的根目录，并执行以下命令将数据导入到新的数据库中：

python manage.py loaddata data.json

这条命令会将导出的数据从 JSON 文件中加载到新的数据库中。



from sat_toolkit.tools.report_mgr import Report_Mgr
from sat_toolkit.tools.teststands_mgr import TestStands_Mgr
from sat_toolkit.tools.testgroup_mgr import TestGroup_Mgr
from sat_toolkit.tools.testcase_mgr import TestCase_Mgr
from sat_toolkit.tools.teststep_mgr import TestStep_Mgr
Report_Mgr.Instance().start_audit("TOC_TEST")
TestStep_Mgr.Instance().list_all()
TestCase_Mgr.Instance().list_all()
TestGroup_Mgr.Instance().list_all()
TestStands_Mgr.Instance().list_all()
TestStands_Mgr.Instance().exec(3)
Report_Mgr.Instance().stop_audit()

----------------------------------
----------------------------------
sudo apt update
sudo apt upgrade -y
sudo apt install -y openssh-server
sudo service ssh status

privacy -- screen -- 永不休眠 自动登录
accessiblity  -- always show menu  keyboard-》screenkeyboard on  clickassist on


/etc/apt/sources.list
# 默认注释了源码镜像以提高 apt update 速度，如有需要可自行取消注释
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy main restricted universe multiverse
deb-src https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy main restricted universe multiverse
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-updates main restricted universe multiverse
deb-src https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-updates main restricted universe multiverse
deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-backports main restricted universe multiverse
deb-src https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-backports main restricted universe multiverse

deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-security main restricted universe multiverse
deb-src https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-security main restricted universe multiverse

# 预发布软件源，不建议启用
# deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-proposed main restricted universe multiverse
# deb-src https://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports/ jammy-proposed main restricted universe multiverse



sudo apt update
sudo apt install -y raspi-config
sudo raspi-config
打开SSH，I2C, SPI, UART 接口
设置locale
扩展sd卡空间


sudo apt install -y chromium-browser
sudo apt install -y net-tools
sudo apt install -y adb
sudo apt install -y dsniff
sudo apt install -y hping3
sudo apt install -y xrdp
sudo apt install -y nmap
sudo apt install -y hostapd
sudo apt install -y python3-pip
sudo apt install -y git
sudo apt install -y python-is-python3
sudo apt install -y python3-psutil
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple django
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple django_extensions
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyusb
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pywifi
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pwntools
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple netifaces
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple python3-nmap
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple django-cors-headers
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple smbus
sudo pip install -i https://pypi.tuna.tsinghua.edu.cn/simple mistune

git config --global user.name "changcheng@sat"
git config --global user.email "changcheng@sat.lab"
sudo apt upgrade -y

语言支持 --安装
chromium，放到favorite，其他favorite的全部去掉


mkdir zeekr_sat_repo
cd zeekr_sat_repo/
git clone http://192.168.8.150:3000/changcheng/zeekr_sat_rep_local.git
cd zeekr_sat_rep_local/
git clone http://192.168.8.150:3000/changcheng/zeekr_sat_ui.git
cd zeekr_sat_ui/
python static_file_location_converter.py
cd ..


## Preparing: Before run sat_shell.py
To perform database migrations, run the following commands:

```shell
sudo python manage.py makemigrations
sudo python manage.py makemigrations sat_toolkit
sudo python manage.py migrate
```

To create a superuser, use the following command:

```shell
sudo python manage.py createsuperuser
```

To load data from a backup file, run the following command:

```shell
sudo python manage.py loaddata db_backup/20231210_1106.json
```

Please ensure that the paths specified in the `sat_ui.service` and `sat_server.service` files are valid.
sudo cp -rf sat_server.service /etc/systemd/system/
<!-- sudo cp -rf sat_ui.service /etc/systemd/system/ -->
sudo systemctl daemon-reload

sudo service sat_server restart
sudo systemctl enable sat_server
<!-- sudo systemctl enable sat_ui -->

sudo systemctl status sat_server
<!-- sudo systemctl status sat_ui -->

搜狗拼音输入法支持


sudo git config --global --add safe.directory /home/sat/zeekr_sat_main
sudo git config --global --add safe.directory /home/sat/zeekr_sat_main/zeekr_sat_ui
