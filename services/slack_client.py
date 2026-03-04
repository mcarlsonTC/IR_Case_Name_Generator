import os
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)

_client = None
_bot_user_id = None

def get_client():
    global _client
    if _client is None:
        _client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    return _client

def get_bot_user_id() -> str:
    global _bot_user_id
    if _bot_user_id is None:
        try:
            result = get_client().auth_test()
            _bot_user_id = result["user_id"]
        except SlackApiError as e:
            logger.error(f"Failed to get bot user ID: {e.response['error']}")
            _bot_user_id = ""
    return _bot_user_id

def get_dart_members() -> list[str]:
    try:
        result = get_client().conversations_members(channel=os.environ["DART_CHANNEL_ID"])
        members = result["members"]
        bot_id = get_bot_user_id()
        return [m for m in members if m != bot_id]
    except SlackApiError as e:
        logger.error(f"Failed to get DART members: {e.response['error']}")
        return []

def get_member_display_names(user_ids: list[str]) -> list[dict]:
    members = []
    for uid in user_ids:
        try:
            result = get_client().users_info(user=uid)
            user = result["user"]
            name = user.get("real_name") or user.get("name", uid)
            members.append({"slack_id": uid, "display_name": name})
        except SlackApiError as e:
            logger.error(f"Failed to get user info for {uid}: {e.response['error']}")
            members.append({"slack_id": uid, "display_name": uid})
    return members

def create_private_channel(channel_name: str) -> str | None:
    try:
        result = get_client().conversations_create(name=channel_name, is_private=True)
        return result["channel"]["id"]
    except SlackApiError as e:
        logger.error(f"Failed to create channel {channel_name}: {e.response['error']}")
        return None

def invite_members(channel_id: str, user_ids: list[str]) -> bool:
    bot_id = get_bot_user_id()
    filtered = [uid for uid in user_ids if uid != bot_id]
    if not filtered:
        return True
    try:
        get_client().conversations_invite(channel=channel_id, users=",".join(filtered))
        return True
    except SlackApiError as e:
        logger.error(f"Failed to invite members: {e.response['error']}")
        return False

def post_message(channel_id: str, text: str = None, blocks: list = None) -> bool:
    try:
        get_client().chat_postMessage(
            channel=channel_id,
            text=text or "",
            blocks=blocks or []
        )
        return True
    except SlackApiError as e:
        logger.error(f"Failed to post message: {e.response['error']}")
        return False

def post_ephemeral(channel_id: str, user_id: str, text: str = None, blocks: list = None) -> bool:
    try:
        get_client().chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=text or "",
            blocks=blocks or []
        )
        return True
    except SlackApiError as e:
        logger.error(f"Failed to post ephemeral: {e.response['error']}")
        return False

def set_channel_topic(channel_id: str, topic: str) -> bool:
    try:
        get_client().conversations_setTopic(channel=channel_id, topic=topic)
        return True
    except SlackApiError as e:
        logger.error(f"Failed to set topic: {e.response['error']}")
        return False

def pin_message(channel_id: str, message_ts: str) -> bool:
    try:
        get_client().pins_add(channel=channel_id, timestamp=message_ts)
        return True
    except SlackApiError as e:
        logger.error(f"Failed to pin message: {e.response['error']}")
        return False
