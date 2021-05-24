# -*- coding: utf-8 -*-

import asyncio
import aiofiles
import ujson
import logging
import os
import time
import threading
import uvloop
import sys
import random

from aiohttp import ClientSession, TCPConnector
from aiomultiprocess import Pool as APool
from multiprocessing import Pool as MPool
from collections import namedtuple
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
from psutil.tests import is_namedtuple

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
        # 文件配置
        self.suffix = os.getenv("suffix")
        self.file_path = (
            Path(os.getenv("save_path"))
            or Path(__file__).resolve(strict=True).parent / "blog"
        )

    @property
    def file_list(self):
        """返回存储文件夹下所有预设类型文件名"""
        return [val.name.split("." + self.suffix)[0] for val in self.file_path.iterdir()]

    @staticmethod
    def check_loop_running():
        """检查线程中是否有运行的loop"""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return False

    @staticmethod
    def load_loop():
        loop = YuQueAssistantBase.check_loop_running()
        if loop:
            asyncio.set_event_loop(loop)
            return loop
        return asyncio.new_event_loop()

    @staticmethod
    def tcp_limiter(limit=8, ssl=True):
        """频率限制"""
        return TCPConnector(limit=limit, ssl=ssl)

    @staticmethod
    async def put_over_all_task():
        """取消当前线程未完成的协程任务"""
        task_list = iter(asyncio.all_tasks())
        next(task_list)
        for val in task_list:
            val.cancel()

        await asyncio.gather(*task_list, return_exceptions=True)


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
        self.header_img_list = list(Path(os.getenv("header_img_path")).iterdir())
        self.loop = None

    def wrap(self, obj):

        if is_namedtuple(obj):
            return obj

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

    def _get_header_img(self):
        img = self.header_img_list[random.randint(1, len(self.header_img_list)) - 1]
        return f"/img/in-post/header/{img.name}"

    def run_until_complete(self, *mother, loop=None, clean=False):
        result = None
        if not loop and not self.loop:
            loop = YuQueAssistantBase.load_loop()
        else:
            loop = self.loop or YuQueAssistantBase.load_loop()
        try:
            result = loop.run_until_complete(asyncio.gather(*mother, loop=loop))
        except asyncio.exceptions.CancelledError as error:
            logger.error(f"在某个Future执行前，其对应的协程任务已取消\n {error}")
        if clean:
            loop.run_until_complete(YuQueAssistantBase.put_over_all_task())
            loop.stop()
            self.loop = None

        return result[0]

    async def get_bolg_index(self):
        """获取全部文章索引"""
        async with ClientSession(connector=YuQueAssistantBase.tcp_limiter()) as session:
            async with session.get(
                    self.repos_url, params={}, headers=self.headers
            ) as r:
                result = await r.json(loads=ujson.loads)

        logger.warning(f"博客总数: {len(result['data'])}")

        return result["data"]

    async def blog_worker(self, kwargs):
        logger.warning(
            f"{datetime.now()} :: 进程 {os.getpid()} :: 线程 {threading.currentThread().native_id} :: {kwargs['slug']} 任务开始"
        )
        extend = self.wrap(kwargs)
        async with extend.session.get(
                self.bolg_url.format(extend.slug), headers=self.headers
        ) as r:
            row = await r.json(loads=ujson.loads)
        if row.get("status") == 429:
            logger.warning(
                f"请求过多被限制, 将自动重试.\n请求参数: {kwargs}\n错误信息: {row.get('message')}"
            )
            await asyncio.create_task(self.blog_worker(kwargs))
        else:
            row = row["data"]
            if r"/" in row["title"]:  # 清理不规范的命名
                row["title"] = row["title"].replace("/", "、").replace(":", "：")

            Summary = HEADERS.format(
                title=row["title"],
                description=row["book"]["description"],
                created_at=row["created_at"].split("T")[0],
                header_img=self._get_header_img()
            )

            file_name = f"{row['created_at'].split('T')[0]}-{extend.slug}"
            if file_name not in extend.file_list:
                logger.warning(f"{datetime.now()} :: {row['title']} 已保存")
                result = row["body"]
                async with aiofiles.open(
                        extend.file_path / f"{file_name}.md", mode="x"
                ) as op:
                    await op.write(Summary + result)
                async with aiofiles.open(
                        extend.file_path.parent / "slug_title.txt", mode="a+"
                ) as f:
                    await f.write(f"{extend.slug}:{row['title']}\n")

    async def get_blog_info(self, args):
        *slug_list, file_list, file_path = args

        async with ClientSession(
                connector=YuQueAssistantBase.tcp_limiter(limit=7)
        ) as session:
            task_list = [
                # asyncio.create_task(  # 加不加一个样
                self.blog_worker(
                    {
                        "slug": slug,
                        "file_list": file_list,
                        "file_path": file_path,
                        "session": session,
                    }
                )
                # )
                for slug in slug_list
            ]
            # as_completed 快些
            # row = await asyncio.gather(*task_list)

            row = []
            try:
                for f in asyncio.as_completed(task_list, timeout=20):
                    row.append(await f)
            except asyncio.TimeoutError as error:
                logger.warning(
                    f"** 存在超时任务 {datetime.now()} **\nError: {error}\nStack: {sys.exc_info()}"
                )

        return row


class YuQueWorker(YuQueAssistantBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = kwargs["token"]

    def get_blog_summary_info(self):
        """获取空间下博客摘要信息"""
        yq_ass = YuQueArticleAssistant(token=self.token)
        result = yq_ass.run_until_complete(yq_ass.get_bolg_index(), clean=True)
        return [val["slug"] for val in result]

    def split_task(self, tasks, chunks=os.cpu_count()):
        """任务分割"""
        return [tasks[i::chunks] for i in range(chunks)]

    def run_in_process(self, task_list):
        """在进程池中运行"""
        p_loop = self.load_loop()
        yq_ass = YuQueArticleAssistant(token=self.token)
        p_loop.run_until_complete(yq_ass.get_blog_info(task_list))

    def pool_worker(self, split_tasks, worker):

        # 原生进程池
        if worker == 1:
            m_pool = MPool(processes=int(os.getenv("processes") or os.cpu_count()))
            for val in split_tasks:
                val.extend([self.file_list, self.file_path])
                m_pool.apply_async(self.run_in_process, args=(val,))
            m_pool.close()
            m_pool.join()

        # 第三方异步进程池
        elif worker == 2:
            yq_ass = YuQueArticleAssistant(token=self.token)

            async def run_all(yq_ass):
                # 建议总并发量不要超过5000/h(实际可以更高点)，否则语雀会返回too many request
                async with APool(
                        processes=int(os.getenv("processes") or os.cpu_count()),
                        queuecount=4,
                        childconcurrency=32,
                ) as pool:
                    # 为每个任务集中增加文件列表和文件位置
                    for val in split_tasks:
                        val.extend([self.file_list, self.file_path])
                    return await pool.map(
                        yq_ass.get_blog_info,
                        split_tasks,
                    )

            asyncio.run(run_all(yq_ass))


if __name__ == "__main__":
    yw = YuQueWorker(token=os.getenv("token"))

    started_at = time.monotonic()

    tasks = yw.get_blog_summary_info()
    split_tasks = yw.split_task(tasks)
    logger.warning(f"分割任务集 :: {split_tasks}")

    yw.pool_worker(split_tasks, 1)

    end = time.monotonic() - started_at
    print(f"time: {end:.2f} seconds")

    os._exit(0)
