import asyncio
import os
from azure.storage.blob import BlobServiceClient, ContentSettings
from app.config import settings

_client: BlobServiceClient | None = None


def _is_azure_enabled() -> bool:
    return bool(settings.azure_storage_connection_string and settings.azure_storage_account_name)


def _container_to_local_path(container: str) -> str:
    # Keep local folder names aligned with existing static mounts in main.py.
    mapping = {
        "profilepics": "profilepics",
        "posts-media": "posts_media",
        "chat-media": "chat-media",
    }
    return mapping.get(container, container)


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _get_client() -> BlobServiceClient | None:
    global _client
    if _client is None and _is_azure_enabled():
        _client = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    return _client


def get_blob_url(container: str, blob_name: str) -> str:
    if _is_azure_enabled():
        return f"https://{settings.azure_storage_account_name}.blob.core.windows.net/{container}/{blob_name}"

    local_container = _container_to_local_path(container).strip("/")
    local_blob = blob_name.lstrip("/").replace("\\", "/")
    return f"/{local_container}/{local_blob}"


async def upload_blob(container: str, blob_name: str, data: bytes, content_type: str) -> str:
    """Upload bytes to blob storage and return the public URL."""
    client = _get_client()
    if client is None:
        local_dir = _container_to_local_path(container)
        local_blob = blob_name.replace("/", os.sep)
        local_path = os.path.join(local_dir, local_blob)
        _ensure_parent_dir(local_path)
        await asyncio.to_thread(_write_bytes, local_path, data)
        return get_blob_url(container, blob_name)

    blob_client = client.get_blob_client(container=container, blob=blob_name)
    cs = ContentSettings(content_type=content_type)
    await asyncio.to_thread(blob_client.upload_blob, data, overwrite=True, content_settings=cs)
    return get_blob_url(container, blob_name)


async def delete_blob(container: str, blob_name: str) -> None:
    """Delete a blob silently (no-op if missing)."""
    client = _get_client()
    if client is None:
        local_dir = _container_to_local_path(container)
        local_blob = blob_name.replace("/", os.sep)
        local_path = os.path.join(local_dir, local_blob)
        await asyncio.to_thread(_delete_if_exists, local_path)
        return
    try:
        blob_client = client.get_blob_client(container=container, blob=blob_name)
        await asyncio.to_thread(blob_client.delete_blob)
    except Exception:
        pass


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _delete_if_exists(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
