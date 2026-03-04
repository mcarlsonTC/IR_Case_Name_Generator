import os
import json
import logging
import httpx
from fastapi import APIRouter, Request, BackgroundTasks
from slack_sdk.signature import SignatureVerifier

from services.gemini import generate_case_name, generate_ir_briefing, generate_custom_briefing

from services.slack_client import (
    create_private_channel,
    invite_members,
    post_message,
    post_ephemeral,
    set_channel_topic,
    get_dart_members,
    get_member_display_names,
    get_client
)
from services.case_tracker import get_existing_cases, register_case, is_duplicate
from services.channel_manager import assign_managers
from routes.slash_command import PENDING_REQUESTS, build_confirmation_blocks

logger = logging.getLogger(__name__)
router = APIRouter()

_verifier = None

def get_verifier():
    global _verifier
    if _verifier is None:
        _verifier = SignatureVerifier(os.environ["SLACK_SIGNING_SECRET"])
    return _verifier

def clear_ephemeral_buttons(response_url: str, message: str):
    try:
        httpx.post(response_url, json={"replace_original": True, "text": message})
    except Exception as e:
        logger.error(f"Failed to clear ephemeral buttons: {e}")

def handle_confirm_create(request_id: str, response_url: str):
    pending = PENDING_REQUESTS.get(request_id)
    if not pending:
        logger.error(f"No pending request found for {request_id}")
        return

    case_name = pending["suggested_name"]
    city_display = pending.get("city_display", "Unknown City")
    user_id = pending["user_id"]
    channel_id = pending["channel_id"]
    excluded_members = pending.get("excluded_members", [])

    try:
        if is_duplicate(case_name):
            existing = get_existing_cases()
            case_name, city_display = generate_case_name(existing)
            pending["suggested_name"] = case_name
            pending["city_display"] = city_display

        new_channel_id = create_private_channel(case_name)
        if not new_channel_id:
            clear_ephemeral_buttons(response_url, "Failed to create channel. Please try again.")
            return

        assign_managers(new_channel_id, user_id)

        dart_members = get_dart_members()
        filtered_members = [m for m in dart_members if m not in excluded_members]
        if filtered_members:
            invite_members(new_channel_id, filtered_members)

        set_channel_topic(new_channel_id, f"IR Case: {case_name} | Managed by <@{user_id}>")

        briefing = generate_custom_briefing(case_name) if not city_display else generate_ir_briefing(case_name, city_display)

        post_message(channel_id=new_channel_id, text=briefing)

        register_case(case_name, user_id, new_channel_id)

        PENDING_REQUESTS.pop(request_id, None)

        clear_ephemeral_buttons(response_url, f"IR channel `{case_name}` created successfully!")

    except Exception as e:
        logger.error(f"Error creating channel: {e}")
        clear_ephemeral_buttons(response_url, "Something went wrong. Please try again.")

def handle_regenerate(request_id: str, response_url: str):
    pending = PENDING_REQUESTS.get(request_id)
    if not pending:
        return

    try:
        existing = get_existing_cases()
        new_name, city_display = generate_case_name(existing)
        pending["suggested_name"] = new_name
        pending["city_display"] = city_display
        PENDING_REQUESTS[request_id] = pending

        blocks = build_confirmation_blocks(new_name, request_id)
        httpx.post(response_url, json={
            "replace_original": True,
            "text": f"Suggested IR Channel: {new_name}",
            "blocks": blocks
        })

    except Exception as e:
        logger.error(f"Error regenerating name: {e}")
        clear_ephemeral_buttons(response_url, "Failed to regenerate name.")

def handle_edit_members(request_id: str, trigger_id: str):
    pending = PENDING_REQUESTS.get(request_id)
    if not pending:
        return

    excluded = pending.get("excluded_members", [])
    dart_member_ids = get_dart_members()
    members_with_names = get_member_display_names(dart_member_ids)

    options = []
    initial_options = []

    for member in members_with_names:
        option = {
            "text": {"type": "plain_text", "text": member["display_name"]},
            "value": member["slack_id"]
        }
        options.append(option)
        if member["slack_id"] not in excluded:
            initial_options.append(option)

    try:
        get_client().views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": f"edit_members_modal_{request_id}",
                "title": {"type": "plain_text", "text": "Edit Members"},
                "submit": {"type": "plain_text", "text": "Confirm"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Uncheck members to exclude from the IR channel:"
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "members_block",
                        "optional": True,
                        "label": {"type": "plain_text", "text": "Members to invite"},
                        "element": {
                            "type": "checkboxes",
                            "action_id": "members_checkboxes",
                            "options": options,
                            "initial_options": initial_options
                        }
                    }
                ]
            }
        )
    except Exception as e:
        logger.error(f"Failed to open edit members modal: {e}")

def handle_custom_name(request_id: str, custom_name: str):
    pending = PENDING_REQUESTS.get(request_id)
    if not pending:
        return

    sanitized = custom_name.lower().strip().replace(" ", "-")
    sanitized = "".join(c for c in sanitized if c.isalnum() or c == "-")
    pending["suggested_name"] = sanitized
    pending["city_display"] = None  # signals custom name — no city
    PENDING_REQUESTS[request_id] = pending

    handle_confirm_create(request_id, pending.get("response_url", ""))


@router.post("/slack/actions")
async def slack_actions(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    if not get_verifier().is_valid_request(body, dict(request.headers)):
        return {"statusCode": 401, "body": "Invalid signature"}

    form = await request.form()
    payload = json.loads(form.get("payload"))
    payload_type = payload.get("type")

    if payload_type == "view_submission":
        callback_id = payload["view"]["callback_id"]

        if callback_id.startswith("custom_name_modal_"):
            request_id = callback_id.replace("custom_name_modal_", "")
            custom_name = (
                payload["view"]["state"]["values"]
                ["custom_name_block"]["custom_name_input"]["value"]
            )
            background_tasks.add_task(handle_custom_name, request_id, custom_name)

        elif callback_id.startswith("edit_members_modal_"):
            request_id = callback_id.replace("edit_members_modal_", "")
            selected = (
                payload["view"]["state"]["values"]
                .get("members_block", {})
                .get("members_checkboxes", {})
                .get("selected_options", [])
            )
            selected_ids = [opt["value"] for opt in selected]
            all_dart = get_dart_members()
            excluded = [m for m in all_dart if m not in selected_ids]
            if request_id in PENDING_REQUESTS:
                PENDING_REQUESTS[request_id]["excluded_members"] = excluded

        return {"response_action": "clear"}

    action = payload["actions"][0]
    action_id = action["action_id"]
    request_id = action["value"]
    response_url = payload.get("response_url", "")

    if request_id in PENDING_REQUESTS:
        PENDING_REQUESTS[request_id]["user_id"] = payload["user"]["id"]
        PENDING_REQUESTS[request_id]["channel_id"] = payload["channel"]["id"]
        PENDING_REQUESTS[request_id]["response_url"] = response_url

    if action_id == "confirm_create":
        background_tasks.add_task(handle_confirm_create, request_id, response_url)

    elif action_id == "regenerate_name":
        background_tasks.add_task(handle_regenerate, request_id, response_url)

    elif action_id == "custom_name":
        trigger_id = payload["trigger_id"]
        get_client().views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": f"custom_name_modal_{request_id}",
                "title": {"type": "plain_text", "text": "Custom IR Name"},
                "submit": {"type": "plain_text", "text": "Create"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "custom_name_block",
                        "label": {"type": "plain_text", "text": "Channel Name"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "custom_name_input",
                            "placeholder": {"type": "plain_text", "text": "e.g. 2026-ir-chicago"}
                        }
                    }
                ]
            }
        )

    elif action_id == "edit_members":
        trigger_id = payload["trigger_id"]
        background_tasks.add_task(handle_edit_members, request_id, trigger_id)

    return {"statusCode": 200}
