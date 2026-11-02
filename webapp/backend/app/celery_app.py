"""Celery 应用：异步任务用的 broker / result backend。

Redis 可以是云端托管（Upstash / Redis Cloud 等），broker URL 走环境变量
``SHOPVISION_CELERY_BROKER_URL``，TLS 就用 ``rediss://`` 前缀。
三个同步接口不依赖这里；只有 /api/v1/tasks/* 需要 worker + Redis。
"""

from __future__ import annotations

from celery import Celery

from .config import get_settings

celery_app = Celery(
    "shopvision",
    broker=get_settings().celery_broker_url,
    backend=get_settings().celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    result_expires=get_settings().celery_result_expires,
    # Redis 挂掉时别让请求线程卡两分钟重试：快速失败，由 api 层转成 50001
    broker_connection_retry=False,
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=1,
    broker_connection_timeout=2,
    task_publish_retry_policy={"max_retries": 1, "interval_start": 0, "interval_step": 0.2},
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
    result_backend_transport_options={
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
        # 结果后端（Redis）不可达时不重试，直接报错；否则一次提交要卡 100+ 秒
        "retry_policy": {"max_retries": 0, "interval_start": 0, "interval_step": 0.1},
    },
)

if get_settings().celery_always_eager:
    # 测试/本地冒烟：任务在调用进程内同步执行，不连 broker
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=False,
        # 结果只留在进程内存（api/tasks.py 的 _EAGER_RESULTS），不连 result backend
        task_store_eager_result=False,
    )
