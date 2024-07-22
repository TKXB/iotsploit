#!/bin/bash
while true; do
    prop=$(settings get system persist.sys.did_usbmode)   # 执行getprop命令，并将输出结果赋值给变量prop
    if [[ "$prop" == "0" ]]; then
        break   # 如果prop的值为123，就退出循环
    fi
    sleep 1   # 稍微等待一下，避免过多占用CPU资源
done
am start -n com.xuexiang.templateproject/com.zeekr.sandbox.activity.MainActivity
echo "xxxxxxxxxxxx" > /data/local/tmp/adsfasdf