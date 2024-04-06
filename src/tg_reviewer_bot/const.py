import os

# get args from environment virables
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_REVIEWER_GROUP = os.environ.get("TG_REVIEWER_GROUP")
TG_PUBLISH_CHANNEL = os.environ.get("TG_PUBLISH_CHANNEL")
TG_REJECTED_CHANNEL = os.environ.get("TG_REJECTED_CHANNEL")
TG_BOT_USERNAME = os.environ.get("TG_BOT_USERNAME")
APPROVE_NUMBER_REQUIRED = 2
REJECT_NUMBER_REQUIRED = 2
REJECTION_REASON = os.environ.get("TG_REJECTION_REASON").split(":")
