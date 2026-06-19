"""Error codes and the StageResult / Failure contract.

Golden rule: stages catch their own exceptions, wrap them in a Failure, and
return — they never raise out of the pipeline.
"""

from __future__ import annotations

from enum import Enum
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorCode(str, Enum):
    NO_CONTAINER_ID = "NO_CONTAINER_ID"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    INVALID_CONTAINER_STATUS_ID = "INVALID_CONTAINER_STATUS_ID"
    NO_BOOKING_ID = "NO_BOOKING_ID"
    INVALID_ECP_COUNT = "INVALID_ECP_COUNT"
    INVALID_CONTAINER_NUMBER = "INVALID_CONTAINER_NUMBER"


ERROR_CODES = frozenset(code.value for code in ErrorCode)


class Failure(BaseModel):
    stage: str
    file: str = ""
    message_id: str = ""
    reason: str = ""
    detail: str = ""


class StageResult(BaseModel, Generic[T]):
    value: Optional[T] = None
    failures: list[Failure] = Field(default_factory=list)

    @classmethod
    def ok(cls, value: T) -> "StageResult[T]":
        return cls(value=value, failures=[])

    @classmethod
    def fail(cls, failure: Failure) -> "StageResult[T]":
        return cls(value=None, failures=[failure])

    @property
    def succeeded(self) -> bool:
        return not self.failures
