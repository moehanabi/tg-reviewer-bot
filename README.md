# tg-reviewer-bot

## 开发前准备

### 安装依赖项

可以手动运行下面的指令来安装

```shell
pip install python-telegram-bot
```

或使用 poetry 来管理依赖

```shell
pip install poetry
poetry install
```

### 配置环境变量

本项目使用了以下环境变量来防止硬编码造成的意外泄露，您务必在运行代码前手动添加它们：

* `TG_TOKEN`
* `TG_REVIEWER_GROUP`
* `TG_PUBLISH_CHANNEL`
* `TG_REJECTED_CHANNEL`
* `TG_BOT_USERNAME`
* `REJECTION_REASON`
