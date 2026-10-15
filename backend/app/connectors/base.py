"""Connector interface. The order core only knows about InboundMessage, so a real
WhatsApp provider can be added later without touching order logic (see
whatsapp-connector/README.md). The local simulator posts to /api/messages/import.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class InboundMessage:
    source: str                 # simulator | import | whatsapp
    external_message_id: str    # provider message ID, used for duplicate protection
    sender_reference: str       # phone number / WhatsApp ID
    sender_name: str | None
    message_text: str


class MessageConnector(ABC):
    """A connector receives provider events and hands them to /api/messages/import."""

    @abstractmethod
    def to_inbound(self, provider_event: dict) -> list[InboundMessage]:
        """Translate a provider webhook payload into inbound messages."""

    def send_text(self, to: str, text: str) -> None:
        """Outbound replies are out of scope until templates and consent are approved."""
        raise NotImplementedError("Outbound messaging is not enabled")
