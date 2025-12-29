# iotsploit-django

`iotsploit-django` 是 IoTSploit 项目的 **Django 外圈（ring）**包：负责 HTTP/WS、ORM、Celery、Redis、以及对 `iotsploit-core` / `iosploit-fuzzer` 的组装注入（composition root）。

> 当前：`iotsploit-django` 已成为 Django 外圈宿主（settings/urls/asgi/celery/ws/models 等已迁入），不再依赖 `sat_toolkit` 作为 Django app。


