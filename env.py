import os

# get args from environment virables
# required settings
TG_TOKEN                = os.environ.get("TG_TOKEN")

TG_REVIEWER_GROUP       = os.environ.get("TG_REVIEWER_GROUP")

TG_PUBLISH_CHANNEL      = os.environ.get("TG_PUBLISH_CHANNEL").split(":")

TG_BOT_USERNAME         = os.environ.get("TG_BOT_USERNAME")

# non-required settings
# bool
TG_SINGLE_MODE          = os.getenv("TG_SINGLE_MODE", "True")       == "True"

TG_TEXT_SPOILER         = os.getenv("TG_TEXT_SPOILER", "True")      == "True"

TG_SELF_APPROVE         = os.getenv("TG_SELF_APPROVE", "True")      == "True"

TG_RETRACT_NOTIFY       = os.getenv("TG_RETRACT_NOTIFY", "True")    == "True"

TG_BANNED_NOTIFY        = os.getenv("TG_BANNED_NOTIFY", "True")     == "True"

TG_REJECT_REASON_USER_LIMIT = os.getenv("TG_REJECT_REASON_USER_LIMIT", "True") == "True"

# int
try:
    APPROVE_NUMBER_REQUIRED     = int(os.getenv("TG_APPROVE_NUMBER_REQUIRED", 2))
except (TypeError, ValueError):
    APPROVE_NUMBER_REQUIRED     = 2

try:
    REJECT_NUMBER_REQUIRED      = int(os.getenv("TG_REJECT_NUMBER_REQUIRED", 2))
except (TypeError, ValueError):
    REJECT_NUMBER_REQUIRED      = 2

try:
    TG_EXPAND_LENGTH            = int(os.getenv("TG_EXPAND_LENGTH", 200))
except (TypeError, ValueError):
    TG_EXPAND_LENGTH            = 200

# string
TG_REJECTED_CHANNEL     = os.environ.get("TG_REJECTED_CHANNEL")

REJECTION_REASON        = os.environ.get("TG_REJECTION_REASON", "已有其他相似投稿:内容不够有趣:内容过于火星:引起感官不适:内容 NSFW:没有 Get 到梗:不在可接受范围内:点错了，正在召唤补发").split(":")

TG_DB_URL               = os.environ.get("TG_DB_URL", "sqlite:///data/database.db")
