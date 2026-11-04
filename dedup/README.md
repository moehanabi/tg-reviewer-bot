# dedup bot — 查重

给投稿/审核 bot 配的独立查重 bot。检测审稿群里新投稿是否是重复内容（别人投过 / 已发布过），
命中则在审稿群发一条 `⚠️ 疑似重复` 标记（L0：只标记，不拦截、不代审稿人决策）。

文本查重只对**纯文本投稿**生效：带媒体的投稿（照片/视频/GIF/贴纸/文件）只查媒体本身，
其文字（caption）既不查重也不存入文本基线。

投稿消息 = 主 bot **顶层直发**（非回复）、无 inline keyboard 的内容消息。主 bot 的
**回复消息一律不是投稿**：审稿界面（meta+投票键盘）、投票反馈、`/append` 提示等操作
消息全是 `reply_text`，进不了查重基线（主 bot 的 `send_submission` 从不以回复形态发内容）。

设计、决策、指纹算法、DB 结构见根目录 `PLAN.md`。本文件只写「怎么跑」。

## 文件

| 文件 | 作用 |
|---|---|
| `env.py` | 所有 `DEDUP_*` 环境变量 |
| `fingerprint.py` | pHash / content_hash / text_hash / SimHash / 汉明距离（纯函数，无 DB） |
| `db.py` | `submission_contents` + `backfill_state` 建表 + 读写 helper |
| `detect.py` | `Baseline`：把 pHash/SimHash 载入 NumPy，向量化汉明距离扫描 |
| `bot.py` / `main.py` | **常驻 bot**（Bot API token）：看新投稿 → 算指纹 → 比对 → 命中发 ⚠️ |
| `backfill.py` / `run_backfill.py` | **一次性回填**（Telethon 用户账号）：读审稿群历史 → 边读边写 → 断点续查 |
| `test_offline.py` | 离线验证（指纹 + db + detect，合成图片/文本，无网络） |
| `test_bot.py` | 离线 handler mock 测试（`on_new_message` 分派逻辑，无网络） |

## 环境变量

| 变量 | 含义 |
|---|---|
| `DEDUP_TOKEN` | 查重 bot 的 token（`can_send_files` + `can_send_messages`） |
| `DEDUP_CUSTOMAPI` | 反向代理前缀，默认 `https://api.telegram.org/bot` |
| `DEDUP_REVIEWER_GROUP` | 审稿群 id(**逗号分隔多值**,= 主 bot 的 `TG_REVIEWER_GROUP`;一个进程看多个群,共用一个基线) |
| `DEDUP_MAIN_BOT_ID` | 主 bot 的 user id(**逗号分隔多值**;作者过滤:只认配置的主 bot 发的投稿。查重跨主 bot——任一主 bot 的内容都命中全部基线) |
| `DEDUP_DB_URL` | `sqlite:///data/dedup.db`（MySQL 亦可） |
| `DEDUP_PHASH_THRESHOLD` | pHash 距离阈值，默认 8 |
| `DEDUP_SIMHASH_THRESHOLD` | SimHash 距离阈值，默认 16 |
| `DEDUP_ENABLE_SIMHASH` | 是否启用近似文本查重，默认 True |
| `TG_USER_SESSION_FILE` | Telethon 用户账号 session 文件（回填用，必须在审稿群里） |
| `TG_USER_API_ID` / `TG_USER_API_HASH` | 首次建 session 用；已有 session 文件后不需要 |
| `DEDUP_BACKFILL_CHAT` | 回填目标（= 审稿群 id，**逗号分隔多值**；每个群独立断点） |

## 跑

```bash
# 1) 离线验证（改了算法后先跑这个）
python dedup/test_offline.py
python dedup/test_bot.py

# 2) 一次性历史回填（首次交互式登录用户账号；断点续查，可反复跑）
export TG_USER_SESSION_FILE=dedup/mt_user.session  # 首次还要 TG_USER_API_ID/HASH
export DEDUP_BACKFILL_CHAT="<审稿群id>" DEDUP_MAIN_BOT_ID="<主bot id>"
python dedup/run_backfill.py --limit 20   # 冒烟：只跑 20 条，断点续查
python dedup/run_backfill.py              # 全量（断点续查，可反复跑）
```

`--limit` 按**每个群各自**生效（如 `DEDUP_BACKFILL_CHAT="g1,g2" --limit 20` = 两群各 20 条）；
用户账号必须是每个回填群的成员。

`run_backfill.py` 目前把 `limit=None`（全量）。要做 `--limit` 冒烟测试，直接调用
`backfill(client, chat, limit=20)`（或临时改 `run_backfill.py`）。

```bash
# 3) 常驻 bot（回填跑完后；多群/多主 bot 用逗号分隔，单值用法不变）
export DEDUP_TOKEN="..." DEDUP_REVIEWER_GROUP="<审稿群id1>,<审稿群id2>" \
       DEDUP_MAIN_BOT_ID="<主bot1 id>,<主bot2 id>"
python dedup/main.py
```

多群部署注意：查重 bot **一个账号**必须能进、能发**每个**配置的审稿群（BotFather
privacy mode 关闭或设为 admin）。⚠️ 回复发往投稿所在的群；「首次出现」深链可能指向
**另一个群**（仅 supergroup 有公开深链）。一个 token = 一个进程 = 全局基线，
跨主 bot / 跨群互相查重。

## 部署顺序

1. BotFather 建 bot，token 开 `can_send_files`（下载媒体算 pHash）+ `can_send_messages`，
   把查重 bot 拉进审稿群。
2. `DEDUP_MAIN_BOT_ID` = 主 bot 的 `Bot.get_me().id`。
3. 先回填一小段（冒烟）→ 观察审稿群 → 再全量回填（20 万张图 ≈ 几小时到几天，断点续查）。
4. 启动 `main.py` 常驻（回填可断点续查地并行/收尾）。
5. 新图/重压缩图/相似文本 → 自动 `⚠️ 疑似重复（相似度 X%）` 标记。

## 验证

- `test_offline.py`：14 项（photo 重复/重压缩/不同图、text 精确/相似/不同、video 字节、
  基线重载、popcount 一致性）。
- `test_bot.py`：25 项（审稿消息/非主 bot 跳过、慢路径下载+存、快路径免下载+标记、
  媒体 caption 不入文本基线、纯文本查重仍生效、标记原文深链、编辑消息更新跳过、标记文案；
  多主 bot 兼容第二主 bot 且命中跨主 bot、第二审稿群入库行带该群 id、跨群命中深链指向首现群、
  主 bot 回复类操作提示跳过且不入文本基线）。
  env 用逗号列表 `99999,88888` / `100,-100...` 跑——单值写法是这些用例的子集，天然回归。
- 端到端（人工，P6）：回填一小段 → 投一张已知重复图 → 看 `⚠️` 标记 + 相似度 + 首次出现时间。
