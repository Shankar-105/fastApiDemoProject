import hashlib
import inspect
import json
from functools import wraps
from typing import Any, Callable, Coroutine, Dict, Optional

import structlog
from fastapi import Header, HTTPException, UploadFile, status
from fastapi.encoders import jsonable_encoder

from app.config import settings
from app.services import redis_service

logger = structlog.get_logger(__name__)

IDEMPOTENCY_KEY_PREFIX = "idempotency:"
IDEMPOTENCY_SCHEMA_VERSION = 1
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"

_IGNORED_ARGUMENT_NAMES = {
    "request",
    "response",
    "idempotency_key",
    "currentUser",
    "current_user",
    "db",
    "dbs",
    "_",
}


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _build_path_hash(path: str) -> str:
    return _hash_text(path)[:16]


def _normalize_for_hash(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {
            str(key): _normalize_for_hash(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }

    if isinstance(value, (list, tuple)):
        return [_normalize_for_hash(item) for item in value]

    if isinstance(value, set):
        return sorted(_normalize_for_hash(item) for item in value)

    if isinstance(value, UploadFile):
        return {"filename": value.filename, "content_type": value.content_type}

    if hasattr(value, "model_dump"):
        try:
            return _normalize_for_hash(value.model_dump(mode="json"))
        except Exception:
            return repr(value)

    try:
        return _normalize_for_hash(jsonable_encoder(value))
    except Exception:
        return repr(value)


def _build_request_hash(
    func: Callable[..., Coroutine[Any, Any, Any]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    signature = inspect.signature(func)
    bound_arguments = signature.bind_partial(*args, **kwargs)
    payload = {
        name: _normalize_for_hash(value)
        for name, value in bound_arguments.arguments.items()
        if name not in _IGNORED_ARGUMENT_NAMES
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return _hash_text(canonical)


def _build_scope_key(user_id: Optional[int], endpoint: str, idempotency_key: str) -> str:
    user_part = f"user:{user_id}" if user_id is not None else "public"
    path_hash = _build_path_hash(endpoint)
    return f"{IDEMPOTENCY_KEY_PREFIX}{user_part}:{path_hash}:{idempotency_key}"


def _build_record(
    *,
    state: str,
    request_hash: str,
    status_code: Optional[int] = None,
    body: Any = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "schema_version": IDEMPOTENCY_SCHEMA_VERSION,
        "state": state,
        "request_hash": request_hash,
    }
    if status_code is not None:
        record["status_code"] = status_code
    if body is not None:
        record["body"] = jsonable_encoder(body)
    if headers is not None:
        record["headers"] = headers
    return record


def build_idempotency_key(user_id: Optional[int], endpoint: str, idempotency_key: str) -> str:
    """Legacy compatibility helper retained for older imports."""
    user_part = f"user:{user_id}" if user_id is not None else "public"
    return f"{IDEMPOTENCY_KEY_PREFIX}{user_part}:{endpoint}:{idempotency_key}"


async def get_idempotency_result(key: str) -> Optional[Dict[str, Any]]:
    try:
        data = await redis_service.redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as exc:
        logger.error("Failed to get idempotency result", error=str(exc))
        return None


async def set_idempotency_processing(key: str, request_hash: str, ttl: int = 3600) -> bool:
    try:
        success = await redis_service.redis_client.set(
            key,
            json.dumps(_build_record(state=STATUS_PROCESSING, request_hash=request_hash)),
            nx=True,
            ex=ttl,
        )
        return bool(success)
    except Exception as exc:
        logger.error("Failed to set idempotency processing", error=str(exc))
        return True


async def set_idempotency_completed(
    key: str,
    request_hash: str,
    status_code: int,
    body: Any,
    headers: Optional[Dict[str, str]] = None,
    ttl: int = 86400,
) -> None:
    try:
        await redis_service.redis_client.set(
            key,
            json.dumps(
                _build_record(
                    state=STATUS_COMPLETED,
                    request_hash=request_hash,
                    status_code=status_code,
                    body=body,
                    headers=headers or {},
                )
            ),
            ex=ttl,
        )
    except Exception as exc:
        logger.error("Failed to set idempotency completed", error=str(exc))


async def delete_idempotency_key(key: str) -> None:
    try:
        await redis_service.redis_client.delete(key)
    except Exception as exc:
        logger.error("Failed to delete idempotency key", error=str(exc))


async def get_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", min_length=1, max_length=255)
) -> Optional[str]:
    return idempotency_key


def idempotent(endpoint_identifier: Optional[str] = None, success_status_code: Optional[int] = None):
    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("currentUser") or kwargs.get("current_user")
            response = kwargs.get("response")
            idempotency_key: Optional[str] = kwargs.get("idempotency_key")

            if not idempotency_key:
                return await func(*args, **kwargs)

            request_kwargs = dict(kwargs)
            request_kwargs.pop("response", None)
            request_hash = _build_request_hash(func, args, request_kwargs)

            user_id = current_user.id if current_user and hasattr(current_user, "id") else None
            endpoint = endpoint_identifier or func.__name__
            redis_key = _build_scope_key(user_id, endpoint, idempotency_key)

            existing = await get_idempotency_result(redis_key)
            if existing:
                if existing.get("request_hash") != request_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency-Key already used with different request data.",
                    )

                if existing.get("state") == STATUS_COMPLETED:
                    logger.info(
                        "Idempotent request - returning cached result",
                        user_id=user_id,
                        endpoint=endpoint,
                        idempotency_key=idempotency_key,
                    )
                    if response is not None and hasattr(response, "status_code"):
                        response.status_code = int(existing.get("status_code", success_status_code or 200))
                    return existing.get("body")

                if existing.get("state") == STATUS_PROCESSING:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Request is already being processed. Please try again later.",
                    )

            processing_success = await set_idempotency_processing(
                redis_key,
                request_hash=request_hash,
                ttl=settings.idempotency_processing_ttl,
            )
            if not processing_success:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Request is already being processed. Please try again later.",
                )

            try:
                result = await func(*args, **kwargs)

                resolved_status_code = success_status_code or 200
                if response is not None and hasattr(response, "status_code"):
                    response.status_code = resolved_status_code

                await set_idempotency_completed(
                    redis_key,
                    request_hash=request_hash,
                    status_code=resolved_status_code,
                    body=result,
                    headers={},
                    ttl=settings.idempotency_completed_ttl,
                )

                return result
            except Exception:
                await delete_idempotency_key(redis_key)
                raise

        if hasattr(func, "__annotations__"):
            wrapper.__annotations__ = func.__annotations__

            signature = inspect.signature(func)
            new_parameters = [param for param in signature.parameters.values() if param.name != "request"]
            wrapper.__signature__ = signature.replace(parameters=new_parameters)
        return wrapper

    return decorator
