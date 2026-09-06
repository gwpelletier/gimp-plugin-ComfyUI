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
from .client import ComfyUIEvent, ComfyUIEventType
from .generation import GenerationCoordinator, GenerationRequest
from .gimp_image import GimpImageOperations
from .export import ExportError, ImageExporter
from .resources import workflow_supports_vae
from .storage import PluginPaths, PromptHistory, StylePresetStore, WorkflowRegistry
from .workflow import validate_api_workflow, load_workflow


class ComfyUIGenerationDialog(GimpUi.Dialog):
    """Collect generation settings and resolve one request asynchronously."""

    def __init__(self, image: Gimp.Image | None):
        """Create a dialog targeting ``image`` for result-layer insertion."""
        super().__init__(title="ComfyUI Batch", flags=0)
        self.image = image
        self.image_operations = GimpImageOperations()
        self.plugin_paths = PluginPaths(Path(Gimp.directory()) / "comfyui")
        self.plugin_paths.ensure()
        self.workflow_registry = WorkflowRegistry(self.plugin_paths.workflow_registry)
        self.prompt_history = PromptHistory(self.plugin_paths.prompt_history)
        self.style_presets = StylePresetStore(self.plugin_paths.styles)
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
        self.workflow_selector = self._add_workflow_selector(grid, 1)
        self._ensure_default_workflows()
        self._refresh_workflow_selector()
        self.prompt = self._add_entry(grid, 2, "Prompt", "")
        self.negative_prompt = self._add_entry(grid, 3, "Negative prompt", "")
        self.checkpoint = self._add_searchable_combo(grid, 4, "Checkpoint")
        self.lora_selector, self.lora_strength, self.lora_rows = self._add_lora_controls(grid, 5)
        self.vae = self._add_searchable_combo(grid, 6, "VAE")
        self._update_vae_support()
        self.steps = self._add_spin(grid, 7, "Steps", 20, 1, 200, 1)
        self.cfg = self._add_spin(grid, 8, "CFG", 8.0, 1.0, 30.0, 0.5)
        self.denoise = self._add_spin(grid, 9, "Denoise", 1.0, 0.0, 1.0, 0.05)
        self.seed = self._add_spin(grid, 10, "Seed", -1, -1, 4294967295, 1)
        self.sampler = self._add_combo(grid, 11, "Sampler", ["euler", "euler_ancestral", "dpmpp_2m"], "euler")
        self.scheduler = self._add_combo(grid, 12, "Scheduler", ["normal", "karras", "simple"], "normal")
        self.output_mode = self._add_combo(
            grid,
            13,
            "Output",
            ["GIMP layers", "New image", "Export directory"],
            "GIMP layers",
        )
        self.output_directory = self._add_entry(grid, 14, "Export directory", "")
        self.status = Gtk.Label(label="Ready", xalign=0)
        grid.attach(self.status, 0, 15, 2, 1)

        action_area = self.get_action_area()
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", self._on_cancel)
        action_area.pack_start(cancel, False, False, 0)
        generate = Gtk.Button(label="Generate")
        generate.connect("clicked", self._on_generate)
        action_area.pack_start(generate, False, False, 0)
        self.generate_button = generate

        history_button = Gtk.Button(label="History")
        history_button.connect("clicked", self._show_history)
        action_area.pack_start(history_button, False, False, 0)
        delete_history_button = Gtk.Button(label="Delete History")
        delete_history_button.connect("clicked", self._delete_latest_history)
        action_area.pack_start(delete_history_button, False, False, 0)
        style_button = Gtk.Button(label="Save Style")
        style_button.connect("clicked", self._save_current_style)
        action_area.pack_start(style_button, False, False, 0)
        load_style_button = Gtk.Button(label="Load Style")
        load_style_button.connect("clicked", self._load_latest_style)
        action_area.pack_start(load_style_button, False, False, 0)
        delete_style_button = Gtk.Button(label="Delete Style")
        delete_style_button.connect("clicked", self._delete_latest_style)
        action_area.pack_start(delete_style_button, False, False, 0)

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

    def _add_workflow_selector(self, grid: Gtk.Grid, row: int) -> Gtk.ComboBoxText:
        """Add a registry-backed workflow selector and management controls."""
        label = Gtk.Label(label="Workflow", xalign=0)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        selector = Gtk.ComboBoxText()
        selector.set_hexpand(True)
        selector.connect("changed", self._on_workflow_changed)
        import_button = Gtk.Button(label="Import")
        import_button.connect("clicked", self._choose_workflows)
        remove_button = Gtk.Button(label="Remove")
        remove_button.connect("clicked", self._remove_selected_workflow)
        box.pack_start(selector, True, True, 0)
        box.pack_start(import_button, False, False, 0)
        box.pack_start(remove_button, False, False, 0)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(box, 1, row, 1, 1)
        return selector

    @staticmethod
    def _add_searchable_combo(grid: Gtk.Grid, row: int, label_text: str) -> Gtk.ComboBoxText:
        label = Gtk.Label(label=label_text, xalign=0)
        combo = Gtk.ComboBoxText.new_with_entry()
        combo.set_hexpand(True)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(combo, 1, row, 1, 1)
        return combo

    def _add_lora_controls(self, grid: Gtk.Grid, row: int):
        label = Gtk.Label(label="LoRAs", xalign=0)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        selector = Gtk.ComboBoxText.new_with_entry()
        selector.set_hexpand(True)
        strength = Gtk.SpinButton.new_with_range(-10.0, 10.0, 0.05)
        strength.set_value(1.0)
        add_button = Gtk.Button(label="Add")
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        controls.pack_start(selector, True, True, 0)
        controls.pack_start(strength, False, False, 0)
        controls.pack_start(add_button, False, False, 0)
        box.pack_start(controls, False, False, 0)
        box.pack_start(rows, False, False, 0)
        add_button.connect("clicked", lambda _button: self._add_lora_row(selector, strength, rows))
        grid.attach(label, 0, row, 1, 1)
        grid.attach(box, 1, row, 1, 1)
        return selector, strength, rows

    def _add_lora_row(self, selector: Gtk.ComboBoxText, strength: Gtk.SpinButton, rows: Gtk.Box) -> None:
        name = selector.get_child().get_text().strip()
        if not name:
            return
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row_name = Gtk.Label(label=name, xalign=0)
        row_name.set_hexpand(True)
        row_strength = Gtk.SpinButton.new_with_range(-10.0, 10.0, 0.05)
        row_strength.set_value(strength.get_value())
        remove = Gtk.Button(label="Remove")
        row.pack_start(row_name, True, True, 0)
        row.pack_start(row_strength, False, False, 0)
        row.pack_start(remove, False, False, 0)
        row._lora_name = name
        row._lora_strength = row_strength
        remove.connect("clicked", lambda _button: rows.remove(row))
        rows.pack_start(row, False, False, 0)
        rows.show_all()

    def _selected_loras(self) -> dict[str, float]:
        return {
            row._lora_name: row._lora_strength.get_value()
            for row in self.lora_rows.get_children()
        }

    def _settings_snapshot(self) -> dict:
        """Return dialog values that can be stored as history or a style."""
        return {
            "prompt": self.prompt.get_text(),
            "negative_prompt": self.negative_prompt.get_text(),
            "checkpoint": self.checkpoint.get_child().get_text(),
            "vae": self.vae.get_child().get_text(),
            "loras": self._selected_loras(),
            "steps": self.steps.get_value_as_int(),
            "cfg": self.cfg.get_value(),
            "denoise": self.denoise.get_value(),
            "seed": self.seed.get_value_as_int(),
            "sampler": self.sampler.get_active_text(),
            "scheduler": self.scheduler.get_active_text(),
        }

    def _apply_settings(self, settings: dict) -> None:
        """Apply stored prompt and generation values to the dialog."""
        self.prompt.set_text(str(settings.get("prompt", "")))
        self.negative_prompt.set_text(str(settings.get("negative_prompt", "")))
        self.checkpoint.get_child().set_text(str(settings.get("checkpoint", "")))
        self.vae.get_child().set_text(str(settings.get("vae", "")))
        self.steps.set_value(float(settings.get("steps", 20)))
        self.cfg.set_value(float(settings.get("cfg", 8.0)))
        self.denoise.set_value(float(settings.get("denoise", 1.0)))
        self.seed.set_value(float(settings.get("seed", -1)))
        for combo, key in ((self.sampler, "sampler"), (self.scheduler, "scheduler")):
            value = settings.get(key)
            if value:
                self._replace_combo_options(combo, [value])

    def _delete_latest_history(self, _button: Gtk.Button) -> None:
        if self.prompt_history.delete(0):
            self.status.set_text("History entry deleted")

    def _load_latest_style(self, _button: Gtk.Button) -> None:
        names = self.style_presets.list()
        if names:
            self._apply_settings(self.style_presets.load(names[0]))
            self.status.set_text("Loaded style")
        else:
            self.status.set_text("No saved styles")

    def _delete_latest_style(self, _button: Gtk.Button) -> None:
        names = self.style_presets.list()
        if names and self.style_presets.delete(names[0]):
            self.status.set_text("Style deleted")

    def _show_history(self, _button: Gtk.Button) -> None:
        entries = self.prompt_history.list()
        if not entries:
            self.status.set_text("No prompt history")
            return
        dialog = Gtk.Dialog(title="Prompt History", transient_for=self, flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_APPLY, Gtk.ResponseType.OK)
        selector = Gtk.ComboBoxText()
        for entry in entries:
            selector.append_text(str(entry.get("prompt", "(empty prompt)")))
        selector.set_active(0)
        dialog.get_content_area().pack_start(selector, True, True, 12)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            self._apply_settings(entries[selector.get_active()])
            self.status.set_text("History entry applied")
        dialog.destroy()

    def _save_current_style(self, _button: Gtk.Button) -> None:
        name = self.prompt.get_text().strip() or "untitled"
        self.style_presets.save(name, self._settings_snapshot())
        self.status.set_text("Style saved")

    def _ensure_default_workflows(self) -> None:
        """Register the workflows shipped with the plug-in."""
        workflow_directory = Path(__file__).resolve().parents[2] / "workflows"
        self.workflow_registry.add([
            workflow_directory / "image-edit-api.json",
            workflow_directory / "inpainting-api.json",
        ])

    def _refresh_workflow_selector(self) -> None:
        self.workflow_selector.remove_all()
        workflows = self.workflow_registry.list()
        for workflow in workflows:
            self.workflow_selector.append(workflow["path"], f'{workflow["title"]} - {workflow["path"]}')
        selected = self.workflow_registry.selected_path or (workflows[0]["path"] if workflows else None)
        if selected is not None:
            self.workflow_selector.set_active_id(selected)
        self._update_vae_support()

    def _on_workflow_changed(self, selector: Gtk.ComboBoxText) -> None:
        selected = selector.get_active_id()
        if selected:
            self.workflow_registry.select(selected)
        self._update_vae_support()

    def _update_vae_support(self) -> None:
        if not hasattr(self, "vae"):
            return
        selected = self.workflow_selector.get_active_id()
        if not selected:
            self.vae.set_sensitive(False)
            return
        try:
            self.vae.set_sensitive(workflow_supports_vae(load_workflow(selected)))
        except Exception:
            self.vae.set_sensitive(False)

    def _choose_workflows(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileChooserDialog(
            title="Import ComfyUI API Workflows",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        workflow_filter = Gtk.FileFilter()
        workflow_filter.set_name("ComfyUI API workflows (*.json)")
        workflow_filter.add_pattern("*.json")
        dialog.add_filter(workflow_filter)
        dialog.set_select_multiple(True)
        if dialog.run() == Gtk.ResponseType.OK:
            try:
                valid_paths = []
                for filename in dialog.get_filenames():
                    workflow = load_workflow(filename)
                    validate_api_workflow(workflow)
                    valid_paths.append(filename)
                self.workflow_registry.add(valid_paths)
                self._refresh_workflow_selector()
                self.status.set_text(f"Imported {len(valid_paths)} workflow(s)")
            except Exception as error:
                self.status.set_text(f"Workflow import error: {error}")
        dialog.destroy()

    def _remove_selected_workflow(self, _button: Gtk.Button) -> None:
        selected = self.workflow_selector.get_active_id()
        if selected and self.workflow_registry.remove(selected):
            self._refresh_workflow_selector()
            self.status.set_text("Workflow removed")

    def _load_remote_options(self) -> None:
        """Fetch model and sampler options without blocking the GTK thread."""
        endpoint = self.endpoint.get_text()
        threading.Thread(target=self._fetch_remote_options, args=(endpoint,), daemon=True).start()

    def _fetch_remote_options(self, endpoint: str) -> None:
        try:
            client = ComfyUIClient(endpoint, timeout=10)
            options = {
                "checkpoints": client.get_available_checkpoints(),
                "loras": client.get_available_loras(),
                "vaes": client.get_available_vaes(),
                "samplers": client.get_available_samplers(),
                "schedulers": client.get_available_schedulers(),
            }
            GLib.idle_add(self._apply_remote_options, options)
        except Exception as error:
            GLib.idle_add(self._show_option_error, str(error))

    def _apply_remote_options(self, options: dict[str, list[str]]) -> bool:
        """Apply background ComfyUI metadata on the GTK main thread."""
        self._replace_combo_options(self.checkpoint, options["checkpoints"])
        self._replace_combo_options(self.lora_selector, options["loras"])
        self._replace_combo_options(self.vae, options["vaes"])
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

    def _set_worker_status(self, message: str) -> None:
        """Schedule a worker status message on GTK's main thread."""
        GLib.idle_add(self._apply_worker_status, message)

    def _apply_worker_status(self, message: str) -> bool:
        self.status.set_text(message)
        return False

    def _on_generation_event(self, event: ComfyUIEvent) -> None:
        """Translate background ComfyUI events into GTK-safe status updates."""
        if event.event_type == ComfyUIEventType.PROGRESS:
            value = event.value or 0
            maximum = event.maximum or 0
            message = f"Generating: step {value}/{maximum}" if maximum else "Generating..."
        elif event.event_type == ComfyUIEventType.EXECUTING:
            message = f"Executing node {event.node_id}" if event.node_id else "Executing..."
        elif event.event_type == ComfyUIEventType.EXECUTION_ERROR:
            message = "ComfyUI reported an execution error; checking result status..."
        elif event.event_type == ComfyUIEventType.STATUS:
            message = "ComfyUI connected; waiting for progress..."
        else:
            return
        self._set_worker_status(message)

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
            workflow_path = self.workflow_selector.get_active_id()
            if not workflow_path:
                raise ValueError("Select a ComfyUI API workflow")
            workflow = load_workflow(workflow_path)
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
                "checkpoint": self.checkpoint.get_child().get_text() or None,
                "vae": self.vae.get_child().get_text() or None,
                "workflow_path": workflow_path,
                "loras": self._selected_loras(),
                "seed": self.seed.get_value_as_int(),
                "steps": self.steps.get_value_as_int(),
                "cfg": self.cfg.get_value(),
                "sampler": self.sampler.get_active_text(),
                "scheduler": self.scheduler.get_active_text(),
                "denoise": self.denoise.get_value(),
            }
            self.prompt_history.add(self._settings_snapshot())
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
                self._set_worker_status("Uploading input image...")
                uploaded = client.upload_image(input_path, subfolder="gimp_uploads")
                uploaded_name = "/".join(part for part in (uploaded.subfolder, uploaded.filename) if part)
            uploaded_mask_name = None
            if mask_path is not None:
                self._set_worker_status("Uploading selection mask...")
                uploaded_mask = client.upload_image(mask_path, subfolder="gimp_uploads")
                uploaded_mask_name = "/".join(
                    part for part in (uploaded_mask.subfolder, uploaded_mask.filename) if part
                )
            self._set_worker_status("Generating with ComfyUI...")
            result = coordinator.run(
                GenerationRequest(
                    workflow=workflow,
                    prompt=settings["prompt"],
                    negative_prompt=settings["negative_prompt"],
                    checkpoint=settings["checkpoint"],
                    vae=settings["vae"],
                    input_image=uploaded_name,
                    mask_image=uploaded_mask_name,
                    seed=settings["seed"],
                    steps=settings["steps"],
                    cfg=settings["cfg"],
                    sampler=settings["sampler"],
                    scheduler=settings["scheduler"],
                    denoise=settings["denoise"],
                    loras=settings["loras"],
                ),
                on_event=self._on_generation_event,
            )
            if not result.images:
                raise RuntimeError("ComfyUI completed without an image output")
            self._set_worker_status("Downloading results...")
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
            output_mode = self.output_mode.get_active_text()
            if output_mode == "Export directory":
                export_directory = self.output_directory.get_text().strip()
                if not export_directory:
                    raise ExportError("Choose an export directory")
                exporter = ImageExporter(export_directory)
                for output_index, output_path in enumerate(output_paths):
                    exporter.export(output_path.read_bytes(), output_path.name, index=output_index)
            elif output_mode == "New image" or self.image is None or not self.image.is_valid():
                image = self.image_operations.load_result(output_paths[0])
                Gimp.Display.new(image)
                for output_path in output_paths[1:]:
                    layer = self.image_operations.insert_layer(image, output_path, "ComfyUI Result")
                    self.image_operations.attach_generation_metadata(layer, metadata)
            else:
                for output_index, output_path in enumerate(output_paths):
                    layer = self.image_operations.insert_layer(
                        self.image,
                        output_path,
                        "ComfyUI Result" if output_index == 0 else f"ComfyUI Result {output_index + 1}",
                    )
                    self.image_operations.attach_generation_metadata(layer, metadata)
                Gimp.displays_flush()
            self.status.set_text("Exported" if output_mode == "Export directory" else "Done")
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