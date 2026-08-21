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


class SMSChannel(NotificationChannel):
    """Stub for future GSM/SMS integration.
    
    TODO: Integrate with an SMS gateway (e.g. Twilio, GSM modem) to dispatch critical alerts.
    """
    def send(self, payload: Dict[str, Any]) -> None:
        # TODO: Implement SMS dispatch
        print(f"SMS stub: sending {payload}")
        pass


class EmailChannel(NotificationChannel):
    """Stub for future Email integration.
    
    TODO: Integrate with SMTP/Email provider to dispatch reports and alerts.
    """
    def send(self, payload: Dict[str, Any]) -> None:
        # TODO: Implement Email dispatch
        print(f"Email stub: sending {payload}")
        pass
