# -*- coding: utf-8 -*-

import asyncio
import aiofiles
import ujson
import logging
import os
import time
import uvloop
import sys

from aiohttp import ClientSession, TCPConnector
from aiomultiprocess import Pool
from collections import namedtuple
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

load_dotenv(dotenv_path=Path(".") / ".env", verbose=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

HEADERS = os.getenv("HEADERS")


class YuQueAssistantBase:
    """
    YuQue助手基类
    """

    def __init__(self, *args, **kwargs):
        # 基本loop
        self.session = None
        self.loop = kwargs["loop"]
        # 文件配置
        self.file_path = (
            os.getenv("save_path")
            or Path(__file__).resolve(strict=True).parent / "blog"
        )
        self.file_list = [val.name.split(".md")[0] for val in self.file_path.iterdir()]

    @property
    def check_loop_running(self):
        return self.loop.is_running()

    @property
    def check_loop_closed(self):
        return self.loop.is_closed()

    @staticmethod
    def load_loop():
        return asyncio.new_event_loop()

    @staticmethod
    def tcp_limiter(limit=8, ssl=True):
        """频率限制"""
        return TCPConnector(limit=limit, ssl=ssl)

    @staticmethod
    async def put_over_all_task():
        """取消当前未完成的任务"""
        task_list = iter(asyncio.all_tasks())
        next(task_list)
        for val in task_list:
            val.cancel()

        await asyncio.gather(*task_list, return_exceptions=True)

    async def yq_session(self, new=False, **kwargs):
        if not self.session or new:
            self.session = ClientSession(connector=self.tcp_limiter(**kwargs))
        return self.session


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
            "User-Agent": os.getenv("User-Agent"),
            "X-Auth-Token": f"{kwargs['token']}",
        }
        self.repos_url = os.getenv("repos_url")
        self.bolg_url = os.getenv("bolg_url")

    def wrap(self, obj):
        for val in obj.copy():
            if val.startswith("_"):
                obj.pop(val)

        CHECK_KEY = ("session", "slug", "file_list", "file_path")

        try:
            assert all(map(lambda x: x in obj.keys(), CHECK_KEY))
        except AssertionError:
            logger.error("object中缺少必要key")

        class JObject(namedtuple("JObject", obj.keys())):
            __slots__ = ()

            def __getattr__(self, name):
                logger.warning(f"尝试获取不存在键值，已返回空字符串")
                return ""

        return JObject(*obj.values())

    def run_until_complete(self, *mother, loop=None):
        result = None
        if not loop:
            loop = YuQueAssistantBase.load_loop()
        try:
            result = loop.run_until_complete(asyncio.gather(*mother))
        except asyncio.exceptions.CancelledError as error:
            logger.error(f"在某个Future执行前，其对应的协程任务已取消\n {error}")

        return result[0]

    async def get_bolg_index(self, session):
        """获取全部文章索引"""
        async with session.get(self.repos_url, params={}, headers=self.headers) as r:
            result = await r.json(loads=ujson.loads)

        await session.close()
        print(result)
        logger.warning(f"博客总数: {len(result['data'])}")

        return result["data"]

    async def blog_worker(self, kwargs):
        extend = self.wrap(kwargs)
        async with extend.session.get(
            self.bolg_url.format(extend.slug), headers=self.headers
        ) as r:
            row = await r.json(loads=ujson.loads)
        if row.get("status") == 429:
            logger.warning(f"请求过多被限制, 将自动重试.\n请求参数: {kwargs}\n错误信息: {row.get('message')}")
            await self.blog_worker(kwargs)
        else:
            row = row["data"]
            if r"/" in row["title"]:  # 清理不规范的命名
                row["title"] = row["title"].replace("/", "、").replace(":", "：")

            Summary = HEADERS.format(
                title=row["title"],
                description=row["book"]["description"],
                created_at=row["book"]["created_at"].split("T")[0],
                header_img=os.getenv("header_img")
                or "/img/in-post/2020-10-29/header.jpg",
            )

            file_name = f"{row['book']['created_at'].split('T')[0]}-{row['title']}"
            if file_name not in extend.file_list:
                logger.warning(f"{datetime.now()} :: {file_name} 已保存")
                result = row["body"]
                async with aiofiles.open(
                    extend.file_path / f"{file_name}.md", mode="x"
                ) as op:
                    await op.write(Summary + result)

    async def get_blog_info(self, args):
        *slug_list, file_list, file_path = args

        async with ClientSession(connector=YuQueAssistantBase.tcp_limiter()) as session:
            task_list = [
                asyncio.create_task(
                    self.blog_worker(
                        {
                            "slug": slug,
                            "file_list": file_list,
                            "file_path": file_path,
                            "session": session,
                        }
                    )
                )
                for slug in slug_list
            ]
            row = []
            try:
                for f in asyncio.as_completed(task_list, timeout=20):
                    row.append(await f)
            except asyncio.TimeoutError as error:
                logger.warning(f"** 存在超时任务 {datetime.now()} **\nError: {error}\nStack: {sys.exc_info()}")

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
        """任务分割"""
        return [tasks[i::chunks] for i in range(chunks)]

    def pool_worker(self, split_tasks):
        yq_ass = YuQueArticleAssistant(token=self.token)

        async def run_all(yq_ass):
            # 建议总并发量不要超过33，否则语雀会返回too many request
            async with Pool(processes=4, queuecount=2, childconcurrency=32) as pool:
                # 为每个任务集中增加文件列表和文件位置
                for val in split_tasks:
                    val.extend([self.file_list, self.file_path])
                return await pool.map(
                    yq_ass.get_blog_info,
                    split_tasks,
                )

        return asyncio.run(run_all(yq_ass))


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    yw = YuQueWorker(loop=loop, token=os.getenv("token"))

    started_at = time.monotonic()

    tasks = yw.get_blog_summary_info()
    split_tasks = yw.split_task(tasks)
    logger.warning(f"分割任务集 :: {split_tasks}")

    yw.pool_worker(split_tasks)

    end = time.monotonic() - started_at
    print(f"time: {end:.2f} seconds")
