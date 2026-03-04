import os
import json
import logging
from datetime import datetime
from azure.storage.blob import BlobServiceClient

logger = logging.getLogger(__name__)

CONTAINER_NAME = "ir-case-data"
REGISTRY_BLOB = "case-registry.json"

def _get_blob_client():
    service = BlobServiceClient.from_connection_string(
        os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    )
    return service.get_blob_client(container=CONTAINER_NAME, blob=REGISTRY_BLOB)

def _load_registry() -> dict:
    """Pull registry from blob, return empty structure if it doesn't exist yet."""
    try:
        blob = _get_blob_client()
        data = blob.download_blob().readall()
        return json.loads(data)
    except Exception:
        return {"cases": {}}

def _save_registry(registry: dict):
    """Upload updated registry back to blob."""
    try:
        blob = _get_blob_client()
        blob.upload_blob(
            json.dumps(registry, indent=2),
            overwrite=True
        )
    except Exception as e:
        logger.error(f"Failed to save registry: {e}")

def get_existing_cases() -> list[str]:
    """Return list of all existing case names."""
    registry = _load_registry()
    return list(registry["cases"].keys())

def is_duplicate(case_name: str) -> bool:
    """Check if a case name already exists."""
    return case_name in get_existing_cases()

def register_case(case_name: str, created_by: str, channel_id: str):
    """Write a new case entry to the registry."""
    registry = _load_registry()
    registry["cases"][case_name] = {
        "created_by": created_by,
        "created_at": datetime.utcnow().isoformat(),
        "channel_id": channel_id
    }
    _save_registry(registry)
    logger.info(f"Registered new case: {case_name}")
