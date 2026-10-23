"""Notification response schema."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    id: str
    message: str
    change: str
    reason: str
    action: str
    timestamp: datetime
    read: bool
