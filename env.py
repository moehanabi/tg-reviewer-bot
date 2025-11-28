import os

# get args from environment virables
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CUSTOMAPI = os.environ.get("TG_CUSTOMAPI", "https://api.telegram.org/bot")
TG_REVIEWER_GROUP = os.environ.get("TG_REVIEWER_GROUP")
TG_PUBLISH_CHANNEL = os.environ.get("TG_PUBLISH_CHANNEL").split(":")
TG_REJECTED_CHANNEL = os.environ.get("TG_REJECTED_CHANNEL")
TG_BOT_USERNAME = os.environ.get("TG_BOT_USERNAME")
TG_RETRACT_NOTIFY = os.getenv("TG_RETRACT_NOTIFY", "True") == "True"
TG_BANNED_NOTIFY = os.getenv("TG_BANNED_NOTIFY", "True") == "True"
TG_REJECT_REASON_USER_LIMIT = (
    os.getenv("TG_REJECT_REASON_USER_LIMIT", "True") == "True"
)

TG_REVIEWONLY = os.getenv("TG_REVIEWONLY", "False") == "True"
try:
    APPROVE_NUMBER_REQUIRED = int(os.getenv("TG_APPROVE_NUMBER_REQUIRED", 2))
except (TypeError, ValueError):
    APPROVE_NUMBER_REQUIRED = 2
try:
    REJECT_NUMBER_REQUIRED = int(os.getenv("TG_REJECT_NUMBER_REQUIRED", 2))
except (TypeError, ValueError):
    REJECT_NUMBER_REQUIRED = 2
REJECTION_REASON = os.environ.get("TG_REJECTION_REASON", "").split(":")
TG_DB_URL = os.environ.get("TG_DB_URL", "")
TG_SINGLE_MODE = os.getenv("TG_SINGLE_MODE", "True") == "True"
TG_TEXT_SPOILER = os.getenv("TG_TEXT_SPOILER", "True") == "True"
TG_EXPAND_LENGTH = int(os.getenv("TG_EXPAND_LENGTH", 200))
TG_SELF_APPROVE = os.getenv("TG_SELF_APPROVE", "True") == "True"
