"""Notification adapters for files, Telegram, and an injected MT5 bridge.

No adapter places or modifies orders. MT5 integration is a caller-provided
message callback so this research package cannot silently trade an account.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class Notifier(ABC):
    @abstractmethod
    def send(self, message: str) -> None:
        raise NotImplementedError


class FileNotifier(Notifier):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, message: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")


class TelegramNotifier(Notifier):
    """Send text via Telegram Bot API using explicit values or environment vars."""

    def __init__(self, bot_token: str, chat_id: str, *, timeout: float = 10.0) -> None:
        if not bot_token or not chat_id:
            raise ValueError("Telegram bot token and chat id are required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._token = bot_token
        self._chat_id = chat_id
        self.timeout = timeout

    @classmethod
    def from_env(cls, *, timeout: float = 10.0) -> TelegramNotifier:
        return cls(
            os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            os.environ.get("TELEGRAM_CHAT_ID", ""),
            timeout=timeout,
        )

    def send(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = urlencode({"chat_id": self._chat_id, "text": message}).encode("utf-8")
        request = Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            if not body.get("ok", False):
                raise RuntimeError("Telegram API rejected the notification")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            # Do not expose the request URL because it contains the bot token.
            raise RuntimeError("Telegram notification failed; verify network and bot configuration") from None


class MT5Notifier(Notifier):
    """Forward a message to an explicitly injected terminal/EA bridge callback."""

    def __init__(self, sender: Callable[[str], object]) -> None:
        if not callable(sender):
            raise TypeError("MT5Notifier requires a callable message bridge")
        self._sender = sender

    def send(self, message: str) -> None:
        self._sender(message)
