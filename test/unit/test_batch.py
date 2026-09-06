import threading

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
