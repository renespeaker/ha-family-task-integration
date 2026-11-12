"""Constants for the Family Task Card Integration."""

DOMAIN = "family_tasks"
# Shown in HA; the domain, services and sensors keep the name family_tasks.
NAME = "Family Task Card Integration"

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

EVENT_POINTS_CHANGED = f"{DOMAIN}_points_changed"
SIGNAL_UPDATED = f"{DOMAIN}_updated"

SERVICE_AWARD = "award"
SERVICE_REVOKE = "revoke"
SERVICE_REDEEM = "redeem"
SERVICE_ADJUST = "adjust"
SERVICE_REQUEST_REWARD = "request_reward"
SERVICE_APPROVE = "approve"
SERVICE_DENY = "deny"
SERVICE_OFFER_CHORE = "offer_chore"
SERVICE_ANSWER_OFFER = "answer_offer"
SERVICE_COVER = "cover"
SERVICE_EVEN_OUT = "even_out"

ATTR_KEY = "key"
ATTR_PERSON = "person"
ATTR_POINTS = "points"
ATTR_TASK = "task"
ATTR_REWARD = "reward"
ATTR_REASON = "reason"
ATTR_REQUEST_ID = "request_id"
ATTR_TO = "to"
ATTR_CHORE = "chore"
ATTR_UNTIL = "until"
ATTR_OFFER_ID = "offer_id"
ATTR_ACCEPT = "accept"
ATTR_ABSENT = "absent"
ATTR_HELPER = "helper"

# Options: notify services (e.g. "mobile_app_moms_phone") that get approval pushes.
CONF_NOTIFY = "notify"

EVENT_REWARD_REQUESTED = f"{DOMAIN}_reward_requested"
EVENT_REWARD_DECIDED = f"{DOMAIN}_reward_decided"
EVENT_CHORE_OFFERED = f"{DOMAIN}_chore_offered"
EVENT_CHORE_ANSWERED = f"{DOMAIN}_chore_answered"

# Actionable notifications: the companion app fires this event on a button tap.
EVENT_NOTIFICATION_ACTION = "mobile_app_notification_action"
ACTION_APPROVE = "FAMILY_TASKS_APPROVE_"
ACTION_DENY = "FAMILY_TASKS_DENY_"
