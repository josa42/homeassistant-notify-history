"""Constants for the Notify History integration."""

from __future__ import annotations

DOMAIN = "notify_history"

CONF_NOTIFY_ENTITIES = "notify_entities"
CONF_NOTIFY_SERVICES = "notify_services"
CONF_MAX_AGE_DAYS = "max_age_days"

DEFAULT_MAX_AGE_DAYS = 14

# A hard cap on top of the age limit, so an automation that loops cannot grow
# the store without bound.
MAX_MESSAGES = 1000

SOURCE_ENTITY = "entity"
SOURCE_SERVICE = "service"

STATUS_OK = "ok"
STATUS_ERROR = "error"

SERVICE_DELETE = "delete"
SERVICE_CLEAR = "clear"

ATTR_MESSAGE_ID = "message_id"
