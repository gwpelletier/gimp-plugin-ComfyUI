import threading

import pytest

from comfyui_plugin.batch import BatchItem, BatchItemStatus, BatchQueue


class TestBatchQueue:
    def test_processes_sequentially_and_keeps_partial_successes(self):
        # Arrange
        items = [BatchItem("one", {"value": 1}), BatchItem("two", {"value": 2})]
        calls = []

        def process(item):
            calls.append(item["value"])
            if item["value"] == 2:
                raise ValueError("bad input")
            return item["value"] * 2

        # Act
        summary = BatchQueue().run(items, process)

        # Assert
        assert calls == [1, 2]
        assert summary.completed[0].result == 2
        assert summary.failed[0].error == "bad input"

    def test_retries_failed_item_and_reports_attempt_count(self):
        # Arrange
        item = BatchItem("one", {"value": 1})
        attempts = 0

        def process(_item):
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise ValueError("retry")
            return "done"

        # Act
        summary = BatchQueue(max_retries=1).run([item], process)

        # Assert
        assert summary.completed[0].result == "done"
        assert item.attempts == 2

    def test_cancellation_marks_remaining_items_without_processing_them(self):
        # Arrange
        items = [BatchItem("one", 1), BatchItem("two", 2)]
        cancellation = threading.Event()

        def process(value):
            cancellation.set()
            return value

        # Act
        summary = BatchQueue().run(items, process, cancellation_event=cancellation)

        # Assert
        assert summary.items[0].status == BatchItemStatus.COMPLETED
        assert summary.items[1].status == BatchItemStatus.CANCELLED

    def test_processor_receives_a_copy_of_mutable_input(self):
        # Arrange
        item = BatchItem("one", {"values": []})

        # Act
        BatchQueue().run([item], lambda value: value["values"].append("changed"))

        # Assert
        assert item.input == {"values": []}

    def test_negative_max_retries_raises_value_error(self):
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="max_retries must not be negative"):
            BatchQueue(max_retries=-1)

    def test_cancellation_between_retries_cancels_item_without_retrying(self):
        # Arrange
        item = BatchItem("one", "input")
        cancellation = threading.Event()
        calls = []

        def process(value):
            calls.append(value)
            cancellation.set()
            raise ValueError("boom")

        # Act
        summary = BatchQueue(max_retries=1).run([item], process, cancellation_event=cancellation)

        # Assert
        assert calls == ["input"]
        assert item.attempts == 1
        assert summary.items[0].status == BatchItemStatus.CANCELLED
        assert summary.items[0].error == "boom"

    def test_on_update_reports_status_transitions_in_processing_order(self):
        # Arrange
        items = [BatchItem("one", 1), BatchItem("two", 2)]
        transitions = []

        def process(value):
            if value == 1:
                raise ValueError("bad input")
            return value * 2

        # Act
        BatchQueue().run(
            items,
            process,
            on_update=lambda item: transitions.append((item.item_id, item.status)),
        )

        # Assert
        assert transitions == [
            ("one", BatchItemStatus.RUNNING),
            ("one", BatchItemStatus.FAILED),
            ("two", BatchItemStatus.RUNNING),
            ("two", BatchItemStatus.COMPLETED),
        ]
