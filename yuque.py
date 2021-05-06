# -*- coding: utf-8 -*-

import asyncio
import aiohttp
import concurrent.futures
import json
import ujson
import logging
import os
import ssl
import re
import time
import threading
from datetime import datetime
from pathlib import Path
import uvloop
import aiofiles
import requests

from collections import namedtuple

from asyncstdlib.builtins import map as async_map
from asyncstdlib.builtins import list as async_list

from aiohttp import ClientSession, TCPConnector
from multiprocessing import Manager, Pool
from aiomultiprocess import Pool

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

HEADERS = """---
title: {title}
subtitle: {description}
author: systemime
date: {created_at}
header_img: {header_img}
catalog: true
tags:
  - python
---

摘要.

<!-- more -->

"""


class YuQueAssistantBase:
    """
    YuQue助手基类
    """

    def __init__(self, *args, **kwargs):
        # 线程进程
        self.threadpool = concurrent.futures.ThreadPoolExecutor(
            max_workers=20, thread_name_prefix="YuQue"
        )
        self.process_pool = Pool(os.cpu_count())
        self.queue = Manager().Queue()
        # 基本loop
        self.session = None
        self.loop = kwargs["loop"]
        # 文件配置
        self.file_path = Path(__file__).resolve(strict=True).parent / "blog"
        self.file_list = [
            val.name.split(".md")[0] for val in self.file_path.iterdir()
        ]

    @property
    def get_and_update_file_list(self):
        self.file_list = [
            val.name.split(".json")[0] for val in self.file_path.iterdir()
        ]
        return self.file_list

    @staticmethod
    def load_loop():
        return asyncio.new_event_loop()

    @property
    def check_loop_running(self):
        return self.loop.is_running()

    @property
    def check_loop_closed(self):
        return self.loop.is_closed()

    @staticmethod
    def tcp_limiter(limit=10, ssl=True):
        """频率限制"""
        return TCPConnector(limit=limit, ssl=ssl)

    async def yq_session(self, new=False, **kwargs):
        if not self.session or new:
            self.session = ClientSession(connector=self.tcp_limiter(**kwargs))
        return self.session

    @staticmethod
    async def put_over_all_task():
        """取消当前未完成的任务"""
        task_list = iter(asyncio.all_tasks())
        next(task_list)
        for val in task_list:
            val.cancel()

        await asyncio.gather(*task_list, return_exceptions=True)

    def close_work_pool(self):
        self.threadpool.shutdown()

    def running_pool(self):
        self.process_pool.close()
        self.process_pool.join()

    @property
    def pool_restult(self):
        result = []
        # 从子进程读取结果并返回
        while not self.queue.empty():
            result.append(self.queue.get())
        return result


class Singleton(type):
    def __init__(self, *args, **kwargs):
        self.__instance = None
        super().__init__(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self.__instance is None:
            self.__instance = super().__call__(*args, **kwargs)
            return self.__instance
        else:
            return self.__instance


class YuQueArticleAssistant(metaclass=Singleton):
    """
    yuque操作业务类
    https://github.com/Alir3z4/html2text
    html转markdown
    """

    def __init__(self, *args, **kwargs):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36",
            "X-Auth-Token": f"{kwargs['token']}",
        }
        self.repos_url = "https://www.yuque.com/api/v2/repos/sound-dmmna/xolni1/docs"
        self.bolg_url = "https://www.yuque.com/api/v2/repos/sound-dmmna/xolni1/docs/{}"
        self.pattern = "<[\w\d]+(([\s\S])*?)<\/[\w\d]+>"  # html标签匹配

    def wrap(self, obj):
        for val in obj.copy():
            if val.startswith("_"):
                obj.pop(val)

        class JObject(namedtuple("JObject", obj.keys())):
            __slots__ = ()

            def __getattr__(self, name):
                return ""

        return JObject(*obj.values())

    def run_until_complete(self, *mother, loop=None):
        result = None
        if not loop:
            loop = YuQueAssistantBase.load_loop()
        try:
            result = loop.run_until_complete(asyncio.gather(*mother))
        except asyncio.exceptions.CancelledError:
            logger.error(f"在某个Future执行前，其对应的协程任务已取消")

        return result[0]

    async def get_bolg_index(self, session):
        """获取全部文章索引"""
        async with session.get(self.repos_url, params={}, headers=self.headers) as r:
            result = await r.json(loads=ujson.loads)

        await session.close()
        logger.warning(f"博客总数: {len(result['data'])}")

        return result["data"]

    async def blog_worker(self, kwargs):
        # 玩玩就好，不要使用
        # for item in kwargs:
        #     globals()[item] = kwargs[item]
        extend = self.wrap(kwargs)
        async with extend.session.get(self.bolg_url.format(extend.slug), headers=self.headers) as r:
            row = await r.json(loads=ujson.loads)

            row = row["data"]
            if r"/" in row["title"]:
                row["title"] = row["title"].replace("/", "、")
                row["title"] = row["title"].replace(":", "：")
            Summary = HEADERS.format(
                title=row["title"],
                description=row["book"]["description"],
                created_at=row["book"]["created_at"].split("T")[0],
                header_img="/img/in-post/2020-10-29/header.jpg"
            )

            file_name = f"{row['book']['created_at'].split('T')[0]}-{row['title']}"
            if file_name not in extend.file_list:
                logger.warning(f"{datetime.now()} :: {file_name} 已保存")
                # result = re.sub(self.pattern, "", row["body"])
                result = row["body"]
                async with aiofiles.open(extend.file_path / f"{file_name}.md", mode="x") as op:
                    # await op.write(ujson.dumps(row))
                    await op.write(Summary + result)

    async def get_blog_info(self, args):
        *slug_list, file_list, file_path = args

        session = ClientSession(connector=TCPConnector(limit=5, ssl=True))

        task_list = [
            asyncio.create_task(self.blog_worker({
                "slug": slug,
                "file_list": file_list,
                "file_path": file_path,
                "session": session,
            }))
            for slug in slug_list
        ]
        row = await asyncio.gather(*task_list)

        # 依赖 asyncstdlib 库 性能不及 create_task
        # row = await async_list(
        #     async_map(
        #         self.blog_worker,
        #         [
        #             {
        #                 "slug": slug,
        #                 "file_list": file_list,
        #                 "file_path": file_path,
        #                 "session": session,
        #             }
        #             for slug in slug_list
        #         ],
        #     )
        # )
        await session.close()

        return row


class YuQueWorker(YuQueAssistantBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = kwargs["token"]

    def get_blog_summary_info(self):
        """获取空间下博客摘要信息"""
        yq_ass = YuQueArticleAssistant(token=self.token)
        session = yq_ass.run_until_complete(self.yq_session(), loop=self.loop)
        result = yq_ass.run_until_complete(
            yq_ass.get_bolg_index(session), loop=self.loop
        )
        return [val["slug"] for val in result]

    def split_task(self, tasks, chunks=os.cpu_count()):
        """
        任务分割
        """
        return [tasks[i::chunks] for i in range(chunks)]

    def pool_worker(self, split_tasks):
        yq_ass = YuQueArticleAssistant(token=self.token)

        async def run_all(yq_ass):
            # 算了一下，大概33是请求上限 /s
            async with Pool(processes=4, queuecount=2, childconcurrency=30) as pool:
                # list传入请求列表，request_one单次请求函数
                for val in split_tasks:
                    val.extend([self.file_list, self.file_path])
                return await pool.map(
                    yq_ass.get_blog_info,
                    split_tasks,
                )

        return asyncio.run(run_all(yq_ass))


if __name__ == "__main__":

    """
    这是一个调试版本
    """

    loop = asyncio.get_event_loop()
    yw = YuQueWorker(loop=loop, token="你的token")

    started_at = time.monotonic()

    tasks = yw.get_blog_summary_info()
    split_tasks = yw.split_task(tasks)
    logger.warning(f"分割任务集 :: {split_tasks}")

    yw.pool_worker(split_tasks)

    end = time.monotonic() - started_at
    print(f"time: {end:.2f} seconds")
