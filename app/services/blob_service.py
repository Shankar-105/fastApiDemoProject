import asyncio
import os
import re
import structlog
from azure.storage.blob import BlobServiceClient, ContentSettings
from fastapi import HTTPException, status
from app.config import settings


logger = structlog.get_logger(__name__)

_client: BlobServiceClient | None = None


def _is_azure_enabled() -> bool:
    """Check whether Azure Blob Storage credentials are configured.

    If the connection string and account name are both set in .env we assume
    we're running in production and route all blob ops through Azure.
    Otherwise we fall back to local filesystem storage.
    """
    return bool(settings.azure_storage_connection_string and settings.azure_storage_account_name)


def _container_to_local_path(container: str) -> str:
    """Map Azure container names to local filesystem directory names.

    Azure uses hyphens in container names; our dev static mounts use underscores
    (e.g. 'posts-media' → 'posts_media').  This translation lets us keep the same
    blob_name everywhere while writing to the correct directory.
    """
    mapping = {
        "profilepics": "profilepics",
        "posts-media": "posts_media",
        "chat-media": "chat-media",
    }
    return mapping.get(container, container)


def _ensure_parent_dir(path: str) -> None:
    """Create parent directories for *path* if they don't exist."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


MAX_UPLOAD_BYTES = settings.max_upload_size_mb * 1024 * 1024


def safe_extension(filename: str | None) -> str:
    """Strip everything except the last alphanumeric extension segment.

    We use this to sanitize user-supplied filenames when generating blob names.
    By rejecting any non-alphanumeric characters in the extension we prevent
    path-traversal tricks like ``.\\"../malware.exe\\"`` from reaching
    ``os.path.join``.
    """
    if not filename:
        return ""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    ext = re.sub(r"[^a-zA-Z0-9]", "", ext)
    return ext


async def validate_and_read_file(file) -> bytes:
    """Read an ``UploadFile`` and enforce the configured max-upload size.

    FastAPI's ``UploadFile.read()`` already spools the file to disk, so we
    enforce the size limit post-read rather than streaming.  A
    413 REQUEST_ENTITY_TOO_LARGE is raised if the file exceeds the limit.
    """
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max {settings.max_upload_size_mb} MiB.",
        )
    return data


def _get_client() -> BlobServiceClient | None:
    """Lazy-init Azure BlobServiceClient (singleton)."""
    global _client
    if _client is None and _is_azure_enabled():
        _client = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    return _client


def get_blob_url(container: str, blob_name: str) -> str:
    """Build a public URL for the given container/blob.

    Azure path → ``https://<account>.blob.core.windows.net/<container>/<blob>``
    Local path → ``/<local_container>/<blob>``  (served by a StaticFiles mount)
    """
    if _is_azure_enabled():
        return f"https://{settings.azure_storage_account_name}.blob.core.windows.net/{container}/{blob_name}"

    local_container = _container_to_local_path(container).strip("/")
    local_blob = blob_name.lstrip("/").replace("\\", "/")
    return f"/{local_container}/{local_blob}"


async def upload_blob(container: str, blob_name: str, data: bytes, content_type: str) -> str:
    """Upload *data* to blob storage and return its public URL.

    When Azure credentials are present we upload to Azure Blob Storage;
    otherwise we write to the local filesystem under the directory mapped
    by ``_container_to_local_path``.

    The local fallback guards against path-traversal attacks on *blob_name*
    by rejecting names containing ``..`` segments or leading ``/``.

    Called from post-creation (media uploads), profile-picture uploads,
    and chat-media uploads.
    """
    logger.info("Uploading blob", extra={"extra_info": {"container": container, "blob_name": blob_name, "content_type": content_type}})
    client = _get_client()
    if client is None:
        local_dir = _container_to_local_path(container)
        local_blob = blob_name.replace("\\", "/")
        if ".." in local_blob.split("/") or local_blob.startswith("/"):
            logger.error("path_traversal_attempt_blocked", blob_name=blob_name)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid blob name.")
        local_blob = local_blob.replace("/", os.sep)
        local_path = os.path.join(local_dir, local_blob)
        _ensure_parent_dir(local_path)
        await asyncio.to_thread(_write_bytes, local_path, data)
        logger.info("Blob uploaded locally", extra={"extra_info": {"container": container, "blob_name": blob_name}})
        return get_blob_url(container, blob_name)

    blob_client = client.get_blob_client(container=container, blob=blob_name)
    cs = ContentSettings(content_type=content_type)
    await asyncio.to_thread(blob_client.upload_blob, data, overwrite=True, content_settings=cs)
    logger.info("Blob uploaded to Azure", extra={"extra_info": {"container": container, "blob_name": blob_name}})
    return get_blob_url(container, blob_name)


async def delete_blob(container: str, blob_name: str) -> None:
    """Delete a blob, silently no-op if the blob doesn't exist.

    Used when a post, profile picture, or chat message with media is deleted
    so we don't leave orphaned files.  Silently returns on failure since
    orphaned blobs are preferable to failing the entire delete request.
    """
    logger.info("Deleting blob", extra={"extra_info": {"container": container, "blob_name": blob_name}})
    client = _get_client()
    if client is None:
        local_dir = _container_to_local_path(container)
        local_blob = blob_name.replace("\\", "/")
        if ".." in local_blob.split("/") or local_blob.startswith("/"):
            logger.error("path_traversal_attempt_blocked", blob_name=blob_name)
            return
        local_blob = local_blob.replace("/", os.sep)
        local_path = os.path.join(local_dir, local_blob)
        await asyncio.to_thread(_delete_if_exists, local_path)
        return
    try:
        blob_client = client.get_blob_client(container=container, blob=blob_name)
        await asyncio.to_thread(blob_client.delete_blob)
    except Exception:
        pass


def _write_bytes(path: str, data: bytes) -> None:
    """Synchronous helper: write *data* to *path*.

    Runs inside ``asyncio.to_thread`` so the event loop isn't blocked by
    filesystem I/O.
    """
    with open(path, "wb") as f:
        f.write(data)


def _delete_if_exists(path: str) -> None:
    """Synchronous helper: delete *path* or silently no-op.

    Runs inside ``asyncio.to_thread``.
    """
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
