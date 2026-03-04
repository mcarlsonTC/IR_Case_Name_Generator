import os
import uuid
import logging
import httpx
from fastapi import APIRouter, Request, BackgroundTasks
from slack_sdk.signature import SignatureVerifier

from services.gemini import generate_case_name
from services.case_tracker import get_existing_cases

logger = logging.getLogger(__name__)
router = APIRouter()

PENDING_REQUESTS: dict = {}

_verifier = None

def get_verifier():
    global _verifier
    if _verifier is None:
        _verifier = SignatureVerifier(os.environ["SLACK_SIGNING_SECRET"])
    return _verifier

def build_confirmation_blocks(suggested_name: str, request_id: str) -> list:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Suggested IR Channel:* `{suggested_name}`\nReview before creating:"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Create Channel"},
                    "style": "primary",
                    "action_id": "confirm_create",
                    "value": request_id
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔄 Try Again"},
                    "action_id": "regenerate_name",
                    "value": request_id
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✏️ Custom Name"},
                    "style": "danger",
                    "action_id": "custom_name",
                    "value": request_id
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "👥 Edit Members"},
                    "action_id": "edit_members",
                    "value": request_id
                }
            ]
        }
    ]

def generate_and_store(request_id: str, user_id: str, channel_id: str, response_url: str):
    try:
        existing = get_existing_cases()
        suggested_name, city_display = generate_case_name(existing)

        PENDING_REQUESTS[request_id] = {
            "suggested_name": suggested_name,
            "city_display": city_display,
            "user_id": user_id,
            "channel_id": channel_id,
            "response_url": response_url,
            "excluded_members": []
        }

        blocks = build_confirmation_blocks(suggested_name, request_id)
        httpx.post(response_url, json={
            "response_type": "ephemeral",
            "text": f"Suggested IR Channel: {suggested_name}",
            "blocks": blocks
        })

    except Exception as e:
        logger.error(f"Error in generate_and_store: {e}")
        httpx.post(response_url, json={
            "response_type": "ephemeral",
            "text": "Failed to generate IR case name. Please try again."
        })

@router.post("/create-ir")
@router.post("/create_ir")
async def create_ir(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    if not get_verifier().is_valid_request(body, dict(request.headers)):
        return {"statusCode": 401, "body": "Invalid signature"}

    form = await request.form()
    user_id = form.get("user_id")
    channel_id = form.get("channel_id")
    response_url = form.get("response_url")

    request_id = str(uuid.uuid4())
    background_tasks.add_task(generate_and_store, request_id, user_id, channel_id, response_url)

    return {"response_type": "ephemeral", "text": "Generating IR case name..."}
