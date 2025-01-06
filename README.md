## Introduction
本项目是基于阿里百炼的向量知识库检索系统。提供以下功能：
创建知识库、查询知识库列表、删除知识库、知识库增加新文件、查询知识库文件列表、删除知识库文件、检索知识库。

## Build docker image and upload to harbor
```sh
sh upload.sh
```

## Local run
添加环境变量
```
linux：export needle_pwd="your_pwd"
IDE配置：Configuration->Enviroment->Environment variables中添加needle_pwd=your_pwd
```

The app will be running on http://0.0.0.0:8471
```sh
python main.py
```
Run in background:
```sh
sh run.sh
```

Shutdown background:
```sh
sh shutdown.sh
```