"""Base channel adapter — defines the interface for multi-channel message adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IncomingMessage:
    """Normalized incoming message from any platform."""
    text: str
    sender_id: str  # platform-specific user identifier
    sender_name: Optional[str] = None
    conversation_id: Optional[str] = None  # platform-specific conversation/group id
    platform: str = ""
    raw: dict = field(default_factory=dict)  # original payload for debugging
    is_unsupported_type: bool = False  # set True when message type is not text


@dataclass
class OutgoingMessage:
    """Normalized outgoing message to any platform."""
    text: str
    markdown: bool = True  # whether text is markdown formatted


class BaseChannelAdapter(ABC):
    """Abstract base for platform-specific channel adapters."""

    platform: str = ""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def verify_request(self, headers: dict, body: bytes) -> bool:
        """Verify that the incoming webhook request is authentic."""
        ...

    @abstractmethod
    def parse_message(self, payload: dict) -> Optional[IncomingMessage]:
        """Parse the raw webhook payload into an IncomingMessage.

        Returns None if the payload is not a user message (e.g. verification event).
        """
        ...

    @abstractmethod
    async def send_reply(self, message: OutgoingMessage, incoming: IncomingMessage) -> bool:
        """Send a reply message back to the platform.

        Returns True on success.
        """
        ...

    def get_challenge_response(self, payload: dict) -> Optional[dict]:
        """Handle platform URL verification challenge.

        Returns the challenge response dict, or None if not a challenge request.
        """
        return None

    async def send_typing(self, incoming: "IncomingMessage") -> None:
        """Send a typing indicator to the platform (best-effort, no-op by default).

        Inspired by OpenClaw's typingMode: instant — sent at the start of the
        agent loop so users see immediate feedback while the AI is processing.
        Platforms that don't support typing indicators should leave this as-is.
        """
        return

    async def send_test_message(self, text: str = "这是一条测试消息，说明渠道配置正确。") -> bool:
        """Send a test message to the configured destination.

        Default implementation creates a synthetic IncomingMessage and calls send_reply.
        Returns True on success.
        """
        fake = IncomingMessage(text="test", sender_id="system", platform=self.platform)
        return await self.send_reply(OutgoingMessage(text=text, markdown=False), fake)
