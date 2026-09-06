"""GIMP 3 interactive UI for ComfyUI generation."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
from gi.repository import Gimp, GimpUi, GLib, Gtk

from .client import ComfyUIClient
from .generation import GenerationCoordinator, GenerationRequest, parse_lora_settings
from .gimp_image import GimpImageOperations
from .storage import PluginPaths
from .workflow import load_workflow


class ComfyUIGenerationDialog(GimpUi.Dialog):
    """Collect generation settings and resolve one request asynchronously."""

    def __init__(self, image: Gimp.Image | None):
        """Create a dialog targeting ``image`` for result-layer insertion."""
        super().__init__(title="ComfyUI Batch", flags=0)
        self.image = image
        self.image_operations = GimpImageOperations()
        self.worker: threading.Thread | None = None
        self.active_client: ComfyUIClient | None = None
        self.active_coordinator: GenerationCoordinator | None = None
        self.cancel_requested = False
        self.completed = False
        self._build_ui()

    def _build_ui(self) -> None:
        content = self.get_content_area()
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_border_width(12)
        content.pack_start(grid, True, True, 0)

        self.endpoint = self._add_entry(grid, 0, "ComfyUI URL", "http://127.0.0.1:8188")
        workflow_path = Path(__file__).resolve().parents[2] / "workflows" / "image-edit-api.json"
        self.workflow_path = self._add_file_entry(grid, 1, "Workflow", str(workflow_path))
        self.prompt = self._add_entry(grid, 2, "Prompt", "")
        self.negative_prompt = self._add_entry(grid, 3, "Negative prompt", "")
        self.checkpoint = self._add_entry(grid, 4, "Checkpoint", "")
        self.loras = self._add_entry(grid, 5, "LoRAs", "")
        self.steps = self._add_spin(grid, 6, "Steps", 20, 1, 200, 1)
        self.cfg = self._add_spin(grid, 7, "CFG", 8.0, 1.0, 30.0, 0.5)
        self.denoise = self._add_spin(grid, 8, "Denoise", 1.0, 0.0, 1.0, 0.05)
        self.seed = self._add_spin(grid, 9, "Seed", -1, -1, 4294967295, 1)
        self.sampler = self._add_combo(grid, 10, "Sampler", ["euler", "euler_ancestral", "dpmpp_2m"], "euler")
        self.scheduler = self._add_combo(grid, 11, "Scheduler", ["normal", "karras", "simple"], "normal")
        self.status = Gtk.Label(label="Ready", xalign=0)
        grid.attach(self.status, 0, 12, 2, 1)

        action_area = self.get_action_area()
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", self._on_cancel)
        action_area.pack_start(cancel, False, False, 0)
        generate = Gtk.Button(label="Generate")
        generate.connect("clicked", self._on_generate)
        action_area.pack_start(generate, False, False, 0)
        self.generate_button = generate

        self.show_all()
        self._load_remote_options()

    @staticmethod
    def _add_entry(grid: Gtk.Grid, row: int, label_text: str, value: str) -> Gtk.Entry:
        label = Gtk.Label(label=label_text, xalign=0)
        entry = Gtk.Entry(text=value)
        entry.set_hexpand(True)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(entry, 1, row, 1, 1)
        return entry

    def _add_file_entry(self, grid: Gtk.Grid, row: int, label_text: str, value: str) -> Gtk.Entry:
        """Add a path entry with a workflow file chooser button."""
        label = Gtk.Label(label=label_text, xalign=0)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        entry = Gtk.Entry(text=value)
        entry.set_hexpand(True)
        browse = Gtk.Button(label="Browse")
        browse.connect("clicked", self._choose_workflow)
        box.pack_start(entry, True, True, 0)
        box.pack_start(browse, False, False, 0)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(box, 1, row, 1, 1)
        return entry

    def _choose_workflow(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileChooserDialog(
            title="Select ComfyUI API Workflow",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        workflow_filter = Gtk.FileFilter()
        workflow_filter.set_name("ComfyUI API workflows (*.json)")
        workflow_filter.add_pattern("*.json")
        dialog.add_filter(workflow_filter)
        if dialog.run() == Gtk.ResponseType.OK:
            self.workflow_path.set_text(dialog.get_filename())
        dialog.destroy()

    def _load_remote_options(self) -> None:
        """Fetch model and sampler options without blocking the GTK thread."""
        endpoint = self.endpoint.get_text()
        threading.Thread(target=self._fetch_remote_options, args=(endpoint,), daemon=True).start()

    def _fetch_remote_options(self, endpoint: str) -> None:
        try:
            client = ComfyUIClient(endpoint, timeout=10)
            options = {
                "checkpoints": client.get_available_checkpoints(),
                "samplers": client.get_available_samplers(),
                "schedulers": client.get_available_schedulers(),
            }
            GLib.idle_add(self._apply_remote_options, options)
        except Exception as error:
            GLib.idle_add(self._show_option_error, str(error))

    def _apply_remote_options(self, options: dict[str, list[str]]) -> bool:
        """Apply background ComfyUI metadata on the GTK main thread."""
        if options["checkpoints"] and not self.checkpoint.get_text():
            self.checkpoint.set_text(options["checkpoints"][0])
        self._replace_combo_options(self.sampler, options["samplers"])
        self._replace_combo_options(self.scheduler, options["schedulers"])
        return False

    @staticmethod
    def _replace_combo_options(combo: Gtk.ComboBoxText, options: list[str]) -> None:
        if not options:
            return
        selected = combo.get_active_text()
        combo.remove_all()
        for option in options:
            combo.append_text(option)
        combo.set_active(options.index(selected) if selected in options else 0)

    def _show_option_error(self, message: str) -> bool:
        """Keep local defaults when remote metadata discovery fails."""
        self.status.set_text(f"Using defaults: {message}")
        return False

    @staticmethod
    def _add_spin(grid: Gtk.Grid, row: int, label_text: str, value: float, lower: float, upper: float, step: float):
        label = Gtk.Label(label=label_text, xalign=0)
        adjustment = Gtk.Adjustment(value=value, lower=lower, upper=upper, step_increment=step, page_increment=step * 10)
        spin = Gtk.SpinButton(adjustment=adjustment, digits=2 if step < 1 else 0)
        spin.set_numeric(True)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(spin, 1, row, 1, 1)
        return spin

    @staticmethod
    def _add_combo(grid: Gtk.Grid, row: int, label_text: str, options: list[str], selected: str):
        label = Gtk.Label(label=label_text, xalign=0)
        combo = Gtk.ComboBoxText()
        for option in options:
            combo.append_text(option)
        combo.set_active(options.index(selected) if selected in options else 0)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(combo, 1, row, 1, 1)
        return combo

    def _on_generate(self, _button: Gtk.Button) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            workflow = load_workflow(self.workflow_path.get_text())
            client = ComfyUIClient(self.endpoint.get_text())
            self.active_client = client
            coordinator = GenerationCoordinator(client)
            self.active_coordinator = coordinator
            self.cancel_requested = False
            input_path = self._stage_input_image()
            mask_path = self._stage_mask_image()
            settings = {
                "prompt": self.prompt.get_text(),
                "negative_prompt": self.negative_prompt.get_text(),
                "checkpoint": self.checkpoint.get_text() or None,
                "workflow_path": self.workflow_path.get_text(),
                "loras": parse_lora_settings(self.loras.get_text()),
                "seed": self.seed.get_value_as_int(),
                "steps": self.steps.get_value_as_int(),
                "cfg": self.cfg.get_value(),
                "sampler": self.sampler.get_active_text(),
                "scheduler": self.scheduler.get_active_text(),
                "denoise": self.denoise.get_value(),
            }
        except Exception as error:
            self.status.set_text(f"Error: {error}")
            return

        self.generate_button.set_sensitive(False)
        self.status.set_text("Submitting...")
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(client, coordinator, workflow, input_path, settings, mask_path),
            daemon=True,
        )
        self.worker.start()

    def _stage_input_image(self) -> Path | None:
        if self.image is None or not self.image.is_valid():
            return None
        paths = PluginPaths(Path(Gimp.directory()) / "comfyui")
        paths.ensure()
        return self.image_operations.save_image(self.image, paths.temporary_images / "main_input.png")

    def _stage_mask_image(self) -> Path | None:
        if self.image is None or not self.image.is_valid():
            return None
        paths = PluginPaths(Path(Gimp.directory()) / "comfyui")
        paths.ensure()
        return self.image_operations.create_mask(self.image, paths.temporary_images)

    def _run_worker(
        self,
        client: ComfyUIClient,
        coordinator: GenerationCoordinator,
        workflow: dict,
        input_path: Path | None,
        settings: dict,
        mask_path: Path | None,
    ) -> None:
        try:
            uploaded_name = None
            if input_path is not None:
                uploaded = client.upload_image(input_path, subfolder="gimp_uploads")
                uploaded_name = "/".join(part for part in (uploaded.subfolder, uploaded.filename) if part)
            uploaded_mask_name = None
            if mask_path is not None:
                uploaded_mask = client.upload_image(mask_path, subfolder="gimp_uploads")
                uploaded_mask_name = "/".join(
                    part for part in (uploaded_mask.subfolder, uploaded_mask.filename) if part
                )
            result = coordinator.run(
                GenerationRequest(
                    workflow=workflow,
                    prompt=settings["prompt"],
                    negative_prompt=settings["negative_prompt"],
                    checkpoint=settings["checkpoint"],
                    input_image=uploaded_name,
                    mask_image=uploaded_mask_name,
                    seed=settings["seed"],
                    steps=settings["steps"],
                    cfg=settings["cfg"],
                    sampler=settings["sampler"],
                    scheduler=settings["scheduler"],
                    denoise=settings["denoise"],
                    loras=settings["loras"],
                )
            )
            if not result.images:
                raise RuntimeError("ComfyUI completed without an image output")
            output_paths = []
            for image_index, image in enumerate(result.images):
                output = client.view_image(image)
                suffix = Path(image.filename).suffix or ".png"
                output_path = (
                    Path(Gimp.directory())
                    / "comfyui"
                    / "temporary_images"
                    / f"result-{image_index}-{uuid.uuid4().hex}{suffix}"
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(output)
                output_paths.append(output_path)
            metadata = {**settings, "seed": result.seed, "prompt_id": result.prompt_id}
            GLib.idle_add(self._finish_on_main_thread, output_paths, metadata)
        except Exception as error:
            GLib.idle_add(self._show_error, str(error))
        finally:
            for staged_path in (input_path, mask_path):
                if staged_path is not None:
                    staged_path.unlink(missing_ok=True)

    def _finish_on_main_thread(self, output_paths: list[Path], metadata: dict) -> bool:
        try:
            if self.cancel_requested:
                self.status.set_text("Cancelled")
                return False
            if self.image is not None and self.image.is_valid():
                for output_index, output_path in enumerate(output_paths):
                    layer = self.image_operations.insert_layer(
                        self.image,
                        output_path,
                        "ComfyUI Result" if output_index == 0 else f"ComfyUI Result {output_index + 1}",
                    )
                    self.image_operations.attach_generation_metadata(layer, metadata)
                Gimp.displays_flush()
            else:
                image = self.image_operations.load_result(output_paths[0])
                Gimp.Display.new(image)
                for output_path in output_paths[1:]:
                    layer = self.image_operations.insert_layer(image, output_path, "ComfyUI Result")
                    self.image_operations.attach_generation_metadata(layer, metadata)
            self.status.set_text("Done")
            self.completed = True
        except Exception as error:
            self._show_error(str(error))
        finally:
            for output_path in output_paths:
                output_path.unlink(missing_ok=True)
        self.generate_button.set_sensitive(True)
        return False

    def _show_error(self, message: str) -> bool:
        self.status.set_text(f"Error: {message}")
        self.generate_button.set_sensitive(True)
        Gimp.message(message)
        return False

    def _on_cancel(self, _button: Gtk.Button) -> None:
        self.completed = False
        self.cancel_requested = True
        coordinator = self.active_coordinator
        if coordinator is not None and self.worker and self.worker.is_alive():
            threading.Thread(target=coordinator.cancel, daemon=True).start()
        self.response(Gtk.ResponseType.CANCEL)