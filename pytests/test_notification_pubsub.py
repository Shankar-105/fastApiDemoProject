from contextlib import asynccontextmanager
from datetime import datetime
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import NotificationType
from app.services import notification_service


@pytest.mark.asyncio
async def test_create_notification_publishes_to_redis_and_includes_receiver_id():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    notif_obj = MagicMock()
    notif_obj.id = 42
    notif_obj.created_at = datetime(2026, 5, 3, 12, 0, 0)
    mock_db.refresh.side_effect = lambda notif: setattr(notif, "id", notif_obj.id) or setattr(notif, "created_at", notif_obj.created_at)

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(return_value=1)
    mock_manager = AsyncMock()
    mock_manager.send_personal_message = AsyncMock()

    @asynccontextmanager
    async def mock_session_factory():
        yield mock_db

    with patch.object(notification_service, "_session_factory", mock_session_factory):
        with patch.object(notification_service.redis_service, "redis_client", mock_redis):
            with patch.object(notification_service, "manager", mock_manager):
                with patch("app.services.notification_service.delete_cache_pattern", AsyncMock()):
                    await notification_service.create_notification(
                        actor_id=1,
                        owner_id=2,
                        notif_type=NotificationType.like,
                        actor_username="alice",
                        entity_id=99,
                        entity_type="post",
                    )

    mock_redis.publish.assert_called_once()
    channel, payload_json = mock_redis.publish.call_args.args
    assert channel == "notifications:messages"

    payload = json.loads(payload_json)
    assert payload["receiver_id"] == 2
    assert payload["actor_id"] == 1
    assert payload["notif_type"] == "like"
    assert payload["text"] == "alice liked your post"
    mock_manager.send_personal_message.assert_not_called()


@pytest.mark.asyncio
async def test_create_notification_falls_back_to_local_send_when_redis_fails():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    mock_db.refresh.side_effect = lambda notif: setattr(notif, "id", 100) or setattr(notif, "created_at", datetime(2026, 5, 3, 12, 0, 0))

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(side_effect=RuntimeError("redis down"))
    mock_manager = AsyncMock()
    mock_manager.send_personal_message = AsyncMock()

    @asynccontextmanager
    async def mock_session_factory():
        yield mock_db

    with patch.object(notification_service, "_session_factory", mock_session_factory):
        with patch.object(notification_service.redis_service, "redis_client", mock_redis):
            with patch.object(notification_service, "manager", mock_manager):
                with patch("app.services.notification_service.delete_cache_pattern", AsyncMock()):
                    await notification_service.create_notification(
                        actor_id=1,
                        owner_id=2,
                        notif_type=NotificationType.follow,
                        actor_username="alice",
                    )

    mock_redis.publish.assert_called_once()
    mock_manager.send_personal_message.assert_called_once()
    assert mock_manager.send_personal_message.call_args.args[1] == 2
