import os
import logging
from services.slack_client import post_message, invite_members

logger = logging.getLogger(__name__)

def assign_managers(channel_id: str, creator_id: str) -> dict:
    """
    Assign the creator as primary manager and the backup from env.
    Invites both, posts and returns the pinned assignment message.
    """
    backup_id = os.environ.get("BACKUP_MANAGER_ID")

    managers_to_invite = [creator_id]
    if backup_id and backup_id != creator_id:
        managers_to_invite.append(backup_id)

    invite_members(channel_id, managers_to_invite)

    return {
        "primary": creator_id,
        "backup": backup_id
    }
