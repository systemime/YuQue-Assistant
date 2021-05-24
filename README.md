# YuQue-Assistant
获取语雀工作区内文章并保存

添加vuepress的markdown格式头部信息，一键保存

优势：
  - 多进程+协程异步，速度快
  - 并发限制
  - 自动保存
  - 自动添加md文件头部信息

环境：
  - python 3.8

使用:
  - 创建 `.env` 文件
  - 写入以下内容
    ```shell script
    # 必要 浏览器头
    User-Agent=
    # 必要 语雀token
    token=
    # 进程数量，默认操作系统cpu数量
    processes=
    # 必要 语雀知识库地址 eg: https://www.yuque.com/api/v2/repos/sound-dmmna/xolni1/docs
    repos_url=
    # 必要 语雀知识库内文章地址 eg: https://www.yuque.com/api/v2/repos/sound-dmmna/xolni1/docs/{}
    # {} 是代码自动填充的占位符
    bolg_url=
    # 非必要 如果保存vuepress的md格式，该参数表示md的头部信息 eg: HEADERS="---\ntitle: {title}\nsubtitle: {description}\nauthor: systemime\ndate: {created_at}\n"
    HEADERS=
    # 非必要 如果是vuepress的md头部信息 该参数标示文章头图
    header_img=
    # 文件夹下按照文件后缀提取文件名 eg: suffix=md
    suffix=
    # 非必要 如果没有该变量，自动保存脚本同级目录下blog目录(手动创建)
    save_path=
    ```
  - 运行脚本
    ```shell
    python yuque.py
    ```
    
  - PS
    > 个人使用脚本，代码中少数path信息未修改，可以按照实际情形修改

优化计划
  - [x] 获取语雀知识库下文章链接
  - [x] 异步请求
  - [x] 多进程并发请求
  - [x] 使用uvloop
  - [x] 异步保存为md格式，并添加vuepress需要的头部信息
  - [x] 通过环境变量规范配置
  - [x] 原生进程池并发
  - [ ] ～～原生进程池并发增加总体并发限制方法 （aiohttp使用limit限制）～～
  - [ ] ～～引入线程池，增加并发能力（没必要了，aiofile本身就是通过线程池实现）～～

