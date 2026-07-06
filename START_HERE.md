# AI 投研工作台启动说明

这是最轻量的文件夹版软件。用户不需要进终端，只需要把 Wind Excel 放到固定目录，然后双击启动文件。

## 1. 放入 Excel

把三个 Wind Excel 放到：

```text
data/wind/current/
```

文件名保持为：

```text
01_ETF清单和日频公式.xlsx
02_TL日频公式.xlsx
03_可转债数据.xlsx
```

## 2. 第一次使用先初始化

macOS 下第一次使用，先双击：

```text
初始化环境.command
```

它会在当前文件夹里创建 `.venv`，并安装系统运行需要的依赖。初始化只需要做一次。

## 3. 双击启动

macOS 下双击：

```text
启动AI投研.command
```

脚本会自动：

- 创建 `data/wind/current/`、`outputs/latest/`、`logs/`
- 检查三个 Excel 是否存在
- 检查运行依赖是否已安装
- 启动本地服务 `http://127.0.0.1:8766/frontend/`
- 自动打开浏览器

## 4. 刷新数据

进入页面后点击：

```text
一键刷新
```

系统会读取三个 Excel，生成 dashboard、日报、SQLite 数据和前端页面。

## 注意

- 关闭启动窗口会停止本地服务。
- 如果缺少某个 Excel，系统仍会启动；对应模块会降级显示，其他模块继续可用。
- 如果三个核心 Excel 都不存在，前端刷新会提示源文件缺失。
- 如果端口 8766 被占用，可以用终端临时指定端口：

```bash
AI_RESEARCH_PORT=8770 ./启动AI投研.command
```
