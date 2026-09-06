"""Sequential batch coordination independent of GIMP and GTK."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Generic, TypeVar


Item = TypeVar("Item")
Result = TypeVar("Result")


class BatchItemStatus(str, Enum):
    """Lifecycle states for one batch item."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchItem(Generic[Item, Result]):
    """One independent batch input and its mutable execution state."""

    item_id: str
    input: Item
    status: BatchItemStatus = BatchItemStatus.QUEUED
    result: Result | None = None
    error: str | None = None
    attempts: int = 0


@dataclass(frozen=True)
class BatchSummary(Generic[Result]):
    """Final snapshot of a sequential batch run."""

    items: tuple[BatchItem[object, Result], ...]

    @property
    def completed(self) -> tuple[BatchItem[object, Result], ...]:
        return tuple(item for item in self.items if item.status == BatchItemStatus.COMPLETED)

    @property
    def failed(self) -> tuple[BatchItem[object, Result], ...]:
        return tuple(item for item in self.items if item.status == BatchItemStatus.FAILED)


class BatchQueue(Generic[Item, Result]):
    """Run independent items sequentially with retry and cancellation support."""

    def __init__(self, *, max_retries: int = 0):
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self.max_retries = max_retries

    def run(
        self,
        items: list[BatchItem[Item, Result]],
        processor: Callable[[Item], Result],
        *,
        cancellation_event: threading.Event | None = None,
        on_update: Callable[[BatchItem[Item, Result]], None] | None = None,
    ) -> BatchSummary[Result]:
        """Process items in order and retain partial successes."""
        cancellation_event = cancellation_event or threading.Event()
        for batch_item in items:
            if cancellation_event.is_set():
                batch_item.status = BatchItemStatus.CANCELLED
                self._notify(batch_item, on_update)
                continue
            batch_item.status = BatchItemStatus.RUNNING
            batch_item.error = None
            self._notify(batch_item, on_update)
            while batch_item.attempts <= self.max_retries:
                if cancellation_event.is_set():
                    batch_item.status = BatchItemStatus.CANCELLED
                    self._notify(batch_item, on_update)
                    break
                batch_item.attempts += 1
                try:
                    batch_item.result = processor(copy.deepcopy(batch_item.input))
                except Exception as error:
                    batch_item.error = str(error)
                    if batch_item.attempts > self.max_retries:
                        batch_item.status = BatchItemStatus.FAILED
                        self._notify(batch_item, on_update)
                    continue
                batch_item.status = BatchItemStatus.COMPLETED
                self._notify(batch_item, on_update)
                break
        return BatchSummary(tuple(items))

    @staticmethod
    def _notify(item: BatchItem[Item, Result], callback) -> None:
        if callback is not None:
            callback(item)
