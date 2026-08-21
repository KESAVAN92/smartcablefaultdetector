from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class NotificationChannel(ABC):
    @abstractmethod
    def send(self, payload: Dict[str, Any]) -> None:
        raise NotImplementedError()


class DashboardChannel(NotificationChannel):
    """Sends notifications to the in-app dashboard/websocket.

    This implementation appends to `current_app.notifications` (a small in-memory list)
    and serves as the default channel for real-time UI to poll or to be pushed by a
    WebSocket broadcaster in future.
    """

    def __init__(self, app):
        self.app = app

    def send(self, payload: Dict[str, Any]) -> None:
        try:
            self.app.notifications = getattr(self.app, "notifications", []) + [payload]
        except Exception:
            # Best-effort; don't raise on UI notification failures
            pass
