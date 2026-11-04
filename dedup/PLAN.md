# 查重 Bot 实现计划（PLAN）

> 本文件是**自包含**的实施计划，供一个全新的（无上下文的）实现会话直接照着做。
> 所有已确认的决策、数据库结构、指纹算法、回填逻辑、代码结构、工作计划都在这里。
> 目标：给现有的投稿/审核机器人（本项目）配一个**独立的查重 bot**，自动检测"重复投稿"。

---

## 1. 目标

做一个**独立的 Telegram bot**（不是改现有 bot），在投稿进入审稿群时自动检测它是否是**重复投稿**（别人投过 / 已发布过），命中则**在审稿群发一条标记消息**（只标记、不拦截、不代替审稿人决策）。

## 2. 现状（主 bot 的事实，已核对源码）

本项目是一个投稿/审核 bot（python-telegram-bot 21.0.1 / SQLAlchemy 2.0 / PyMySQL）。关键事实：

- **投稿流程**：用户在**私聊**里发给 bot → bot 回确认按钮（署名/匿名/取消）→ 确认后 `send_submission` 把内容发到**审稿群**（`TG_REVIEWER_GROUP`），并用 `reply_review_message` 发一条带投票键盘的审稿消息。
  - 代码：`submit_single.py:confirm_submission`（单条模式，默认 `TG_SINGLE_MODE=True`）、`submit.py`（多条合并模式）。
- **审稿消息**（`review_utils.py:reply_review_message`）：文本以 `reply_text` 发到审稿群，文本含状态标题（`❔ 待审稿件` 等）+ 隐藏的 base64/pickle meta + 标签 `#USER_` `#SUBMITTER_`；它**回复到** `submission_messages[0]`（第一条内容消息）。
- **内容在审稿群里的形态**（来自 `utils.py:send_submission` / `send_group`）：
  - 照片/视频 → 媒体组（`send_media_group`）或单独发；文本是**首条媒体的 caption**。
  - GIF（animation）→ `send_animation`（单独发）；贴纸 → `send_sticker`（**丢弃文本**）。
  - 纯文本投稿 → 单独一条文本消息（无媒体）。
- **已有"重复"概念**：`ReviewChoice.REJECT_DUPLICATE`（`review_utils.py:49`）"以重复投稿拒绝"，一票否决，理由文案"已在频道发布过或已有人投稿过"（`review_utils.py:533`）。本项目要做的是把"查"这一步**自动化**。
- **主 bot 目前不存任何内容指纹**——只在 DB 里记统计（`submitters`/`reviewers`/`banned_users`/`banned_origins`，见 `db_op.py`）。查重需要的指纹表是**新增**的。

**主 bot 账号 id**：用 `Bot.get_me().id`（或 `dedup_get_me`）拿；查重 bot 需要它做**作者过滤**（只认主 bot 发的投稿消息，主 bot 可能不止一个）。

## 3. 已确认的决策

| 项 | 决定 | 备注 |
|---|---|---|
| 架构 | **独立 bot**（新 token / 进程 / DB），不动主 bot | L0 模式下放弃"拦截"和"标记嵌进投票键盘"，可接受 |
| 检测范围 | **图片 pHash（感知哈希）为主** + 媒体字节哈希 + 文本 | 能抓"重新压缩/改尺寸"的图 |
| 命中动作 | **L0 标记**：审稿群发 `⚠️ 疑似重复` 回复，仍由审稿人决定 | 不拦、不自动拒 |
| 比对基线 | **所有历史投稿**（审稿群里主 bot 发过的全部，**不分是否发布**） | 能抓"已有人投稿过"（viral 图第 2~N 个） |
| 历史回填 | **Telethon 用户账号读审稿群历史**（用户账号必须在审稿群里） | 边读边写 + **断点续查** |
| 近似文本 | **加 SimHash 近似文本查重**（可开关，阈值可调） | 默认开 |
| 文本精确 | SHA-256 | 抓完全相同 |
| `file_unique_id` | **保留为缓存键**（bot 侧抓取时填） | 精确查重零下载 + 缓存命中免重算 |

## 4. 架构

```
[Telethon 用户账号]  ──一次性回填──▶  读审稿群历史 → 边读边写 → submission_contents
                                        (断点续查: backfill_state)
[查重 bot / 常驻]     ──长期运行──▶  只看审稿群的"新投稿"
                                     → 算指纹
                                     → 比对基线 submission_contents
                                     → 命中则发 ⚠️ 标记
                                     → 写入基线
```

两个进程、两套凭证：
- **回填**：Telethon **用户账号**（MTProto），只跑一次（或重跑续查，或可以指定消息 id 范围，记录 id 范围内的消息特征）。
- **查重 bot**：Bot API **token**，常驻在**审稿群**。

> **为什么用户账号 / bot 各管一半**：Bot API **没有读历史**的方法（无 `getChatHistory`），bot 只能收加入之后的新消息；读历史必须用 MTProto 用户协议。所以"读历史"用用户账号，"日常捕获新投稿"用 bot。

## 5. 检测方案（指纹）

### 5.1 为什么 MTProto 拿不到 `file_unique_id`
`file_unique_id` 是 **Bot API** 概念（`getFile` 返回的 `BotFile.file_unique_id`）。MTProto 用户协议没有这个字段/方法——用户账号只能**下载字节**。所以回填出的条目 `file_unique_id = NULL`。
**不影响功能**：`content_hash`（字节 SHA-256）两边都能算、对同字节值一致；且"字节相同 ⇒ 同 `file_unique_id`" 与 "字节相同 ⇒ 同 `content_hash`" 等价。`file_unique_id` 只在 **bot 侧**能拿到，用来做**缓存键 / 精确快路径**（见 5.4）。

### 5.2 内容指纹（按媒体类型）
- **图片（photo）→ pHash**（`imagehash`，64-bit）：主键，能抓重压缩/改尺寸/改质量。
- **视频 / GIF / document / sticker → `content_hash`**（字节 SHA-256）：字节级，跨两边一致。
- **文本（caption / 纯文本）→ `text_hash`（SHA-256，精确）+ `text_simhash`（SimHash，近似）**。

### 5.3 比对逻辑
- **精确**：`content_hash` / `text_hash` 走 SQL `WHERE` 查（有索引）。
- **图片近似**：启动时把已发布图片的 pHash 载入一个 **NumPy int64 数组**（~20 万条 ≈ 2MB），每张新图做一次**向量化 XOR + popcount 全扫描**（毫秒级），取最小距离 / 找 `≤ 阈值`。
- **文本近似**：SimHash 64-bit 汉明距离 `≤ 阈值` 判相似（同样 NumPy 全扫描）。
- **精确快路径**：bot 侧先 `getFile` 拿 `file_unique_id`，查"已见过的 `file_unique_id` 集合"，命中即重复（**不下载、不算 hash**）；否则才下载算 hash。

### 5.4 阈值
- **pHash 汉明距离**：0–5 同图；5–15 相似；>15 基本不同。默认 **8**（偏严）。
- **文本 SimHash 距离**：默认 **16**（64-bit，约 75% 相似）。可调。
- 命中消息里给相似度百分比（`100 - distance/64*100`），供人判断。

### 5.5 规模化（当前 ~20 万图片）：要不要向量库？
**结论：不需要。** pHash/SimHash 是 **64-bit 定长二进制**，不是高维 float 向量。向量库（CLIP embedding + FAISS/Pinecone 那类）是给**高维 float 语义检索**做 ANN 的；对 64-bit 哈希，"全扫描汉明距离"就是最优解，简单又快。
- **比对**：所有 pHash 存 NumPy int64 数组（~20 万 ≈ 2MB），每张新图一次向量化 XOR + popcount → **毫秒级**，轻松撑到**百万级**。精确查重走 SQL 索引，20 万行是毛毛雨。
- **可选**：真到几百万再考虑 FAISS **binary index**（原生支持汉明距离）。20 万规模 NumPy 足够，少一个依赖。
- **真正的 20 万规模问题不在比对，在回填**：下载 20 万张图 + 20 万次 `getFile` 是个体量很大的**一次性**离线任务（限速下可能几小时~几天）。`边读边写 + 断点续查` 就是为它设计的——要规划：预估时长、限速 `sleep`、失败重试、断点续跑。

## 6. 数据库结构

默认 `sqlite:///data/dedup.db`（`TG_DB_URL` 同套写法，可用 MySQL）。

```sql
-- 基线：审稿群里每个投稿的每条内容一行
CREATE TABLE submission_contents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_key  VARCHAR(190) NOT NULL,   -- 投稿标识（主 bot 的 first_message_id，用于聚合同一投稿）
    type            VARCHAR(32)  NOT NULL,   -- photo|video|gif|document|sticker|text
    phash           VARCHAR(32),             -- 图片：64-bit hex
    content_hash    VARCHAR(64),             -- 其它媒体 字节 SHA-256
    text_hash       VARCHAR(64),             -- 文本 SHA-256（精确）
    text_simhash    VARCHAR(32),             -- 文本 SimHash 64-bit hex（近似）
    file_unique_id  VARCHAR(190),            -- 缓存键：仅 bot 侧抓取时填
    source_chat_id      BIGINT NOT NULL,     -- 审稿群 id
    source_message_id   BIGINT NOT NULL,
    submitter_id        VARCHAR(190),        -- 回填时可能未知
    first_seen_date     DATETIME NOT NULL
);
CREATE INDEX idx_pcid    ON submission_contents(file_unique_id);
CREATE INDEX idx_phash   ON submission_contents(phash);
CREATE INDEX idx_content ON submission_contents(content_hash);
CREATE INDEX idx_text    ON submission_contents(text_hash);
CREATE INDEX idx_simhash ON submission_contents(text_simhash);

-- 回填断点
CREATE TABLE backfill_state (
    chat_id INTEGER PRIMARY KEY,
    last_min_message_id INTEGER,   -- 已处理到的"最老那条" message_id
    last_date DATETIME
);
```

## 7. 代码结构（`dedup/` 包，和主 bot 物理隔离）

```
dedup/
├── env.py            # DEDUP_* 环境变量
├── db.py             # 建表 + 读写 helper（仿主 bot db_op.py 的 DB 封装风格）
├── fingerprint.py    # pHash / content_hash / text_hash / SimHash / 汉明距离
├── detect.py         # 比对基线，返回命中的已发布条目 + 相似度
├── bot.py            # 常驻 bot：审稿群"新投稿" handler（检测→标记→写基线）
├── main.py           # 启动 bot 入口
├── backfill.py       # Telethon 用户账号：读审稿群历史 → 边读边写 → 断点续查
└── run_backfill.py   # 回填入口（读用户账号 session）
```

`fingerprint.py` 职责：
- `compute_phash(img_bytes) -> hex`（PIL + imagehash）
- `sha256_bytes(b) -> hex`（content_hash / text_hash）
- `simhash_text(text) -> hex`（字符 n-gram SimHash，CJK 友好）
- `hamming(hex_a, hex_b) -> int`
- `find_matches(item) -> list[(row, distance)]`

## 8. 环境变量

| 变量 | 含义 |
|---|---|
| `DEDUP_TOKEN` | 查重 bot 的 token |
| `DEDUP_REVIEWER_GROUP` | 审稿群 id（= 主 bot 的 `TG_REVIEWER_GROUP`） |
| `DEDUP_MAIN_BOT_ID` | 主 bot 的 user id（作者过滤，只认它发的投稿） |
| `DEDUP_DB_URL` | `sqlite:///data/dedup.db` |
| `DEDUP_PHASH_THRESHOLD` | pHash 距离阈值，默认 8 |
| `DEDUP_SIMHASH_THRESHOLD` | SimHash 距离阈值，默认 16 |
| `DEDUP_ENABLE_SIMHASH` | 是否启用近似文本查重，默认 True |
| `TG_USER_SESSION_FILE` | Telethon 用户账号 session 文件（回填用） |
| `DEDUP_BACKFILL_CHAT` | 回填目标 = 审稿群 id |

## 9. 详细工作计划

**P0 准备（人工）**
1. BotFather 建查重 bot，token 设 `can_send_files`（下载媒体算 pHash）+ `can_send_messages`（发标记）。
2. 把查重 bot 拉进**审稿群**。
3. 准备一个在**审稿群**里的用户账号（跑 Telethon 回填）。
4. 新 DB：`DEDUP_DB_URL`。

**P1 `fingerprint.py`**
- pHash（Pillow + imagehash）/ content_hash（sha256）/ text_hash（sha256）/ SimHash（字符 n-gram，n=4，64-bit）/ 汉明距离。
- `requirements.txt` 加 `Pillow`、`imagehash`、`Telethon`、`numpy`。

**P2 `db.py`**
- `submission_contents` + `backfill_state` 两张表（`Base.metadata.create_all`）。
- 读写 helper：`record_items(...)`, `find_exact(hash)`, `load_photo_phashes()`, `get_or_set_checkpoint(chat_id)`, `set_checkpoint(chat_id, min_id)`。

**P3 `backfill.py`（Telethon，用户账号，一次性/可续跑）**
- 登录用户账号（`TG_USER_SESSION_FILE`）→ 定位审稿群。
- `iterate_messages` **从新往旧**；`if message.id < last_min_message_id: break`（断点续查）。
- 只处理**主 bot 账号发的媒体消息**（含 caption 文本），跳过带投票键盘的审稿消息。
- 每条：下载 → 算指纹 → `INSERT` → 边读边写 → 更新 `backfill_state`。
- 支持 `--limit`、断点续查。

**P4 `bot.py` / `main.py`（常驻）**
- 只处理 `filters.UpdateType.MESSAGES`（新消息，忽略编辑）；`filters.Chat(id=DEDUP_REVIEWER_GROUP)`。
- 只认 `message.from_user.id == DEDUP_MAIN_BOT_ID` 且是**媒体**（或无 inline 键盘的纯文本投稿）；跳过投票键盘审稿消息。
- 流程：`getFile` 拿 `file_unique_id` → 命中已见集合则跳过下载 → 下载算指纹 → 比对基线 → 命中发 `⚠️ 标记` → 写基线。
- 用 `LRUCache`/内存缓存 `file_unique_id → hash` 与"已见 `file_unique_id` 集合"。

**P5 测试**
- 回填一小段历史（`--limit`）→ 投一张已知重复图 → 验证 `⚠️` 标记 + 相似度 + 链接。
- 验证：重复图第 1 次不标（写入基线）、第 2 次标；重压缩图能标；不同图不标。

**P6 部署**
- 全量回填（断点续查跑完）→ 启动 `main.py` 常驻。

## 10. 标记消息格式（发到审稿群）

```
⚠️ 疑似重复（相似度 88%）
与早前投稿内容相似（pHash 距离 5 / 阈值 8）
🔗 t.me/c/<审稿群>/<message_id>   （若审稿群可公开链接；否则只写最早出现时间）
```

## 11. 风险与验证点

1. **识别"投稿"是主要复杂度**：审稿群里混着审稿人的聊天/图片。**锚点** = 主 bot 账号 + 媒体消息 + 非投票键盘消息。P5 必须验证这个过滤不误伤/不误漏。
2. **`can_send_files` 是部署关键**：查重 bot 必须能下载审稿群里的媒体字节才能算 pHash。
3. **误报**：L0 只标记，误报只是多一次人工判断，不伤投稿。
4. **回填用户账号 API 调用量**：读历史 + 下载 20 万张图是个体量很大的离线任务（约 20万张图 + 20万次 `getFile`），脚本加 `sleep` 尊重 flood 限流、断点续查、失败重试；一次性，风险低但要预留几小时~几天。
5. **视频/GIF 只抓字节级重复**（不做视频帧近似），可接受（沙雕频道以图片为主）。

## 12. 明确不做（本阶段）
- 拦截投稿 / 自动拒。
- 把标记嵌进投票键盘（独立 bot 做不到，只能事后发独立消息）。
- 视频/GIF 近似查重。

## 13. 待确认
- 回填读**审稿群**（已确认，不是发布频道）。
- 是否要公开链接（审稿群是否 public，决定标记里能不能给 t.me 链接）。
