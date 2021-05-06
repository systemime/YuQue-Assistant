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
    # 必要 语雀知识库地址 eg: https://www.yuque.com/api/v2/repos/sound-dmmna/xolni1/docs
    repos_url=
    # 必要 语雀知识库内文章地址 eg: https://www.yuque.com/api/v2/repos/sound-dmmna/xolni1/docs/{}
    # {} 是代码自动填充的占位符
    bolg_url=
    # 非必要 如果保存vuepress的md格式，该参数表示md的头部信息 eg: HEADERS="---\ntitle: {title}\nsubtitle: {description}\nauthor: systemime\ndate: {created_at}\n"
    HEADERS=
    # 非必要 如果是vuepress的md头部信息 该参数标示文章头图
    header_img=
    # 非必要 如果没有该变量，自动保存脚本同级目录下blog目录(手动创建)
    save_path=
    ```
  - 运行脚本

优化计划
  - [x] 获取语雀知识库下文章链接
  - [x] 异步请求
  - [x] 多进程并发请求
  - [x] 异步保存为md格式，并添加vuepress需要的头部信息
  - [x] 通过环境变量规范配置
  - [] 引入线程池，增加并行