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
from .resources import (
    CheckpointType,
    best_guess_option,
    checkpoint_profile,
    family_supports_mode,
    infer_checkpoint_type,
    validate_checkpoint_workflow,
    workflow_matches_checkpoint_type,
    workflow_supports_inpainting,
    workflow_supports_vae,
)
from .storage import PluginPaths, PromptHistory, StylePresetStore, WorkflowRegistry
from .workflow import validate_api_workflow, load_workflow


class ComfyUIGenerationDialog(GimpUi.Dialog):
    """Collect generation settings and resolve one request asynchronously."""

    def __init__(self, image: Gimp.Image | None, *, eraser_mode: bool = False):
        """Create a dialog targeting ``image`` for result-layer insertion."""
        super().__init__(title="ComfyUI AI Eraser" if eraser_mode else "ComfyUI Batch", flags=0)
        self.image = image
        self.eraser_mode = eraser_mode
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
        self._remote_options: dict[str, list[str]] = {}
        self._server_available = True
        self._options_fetch_active = False
        self._build_ui()

    def _build_ui(self) -> None:
        content = self.get_content_area()
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_border_width(12)
        content.pack_start(grid, True, True, 0)

        self.endpoint, self.retry_button = self._add_endpoint_row(grid, 0)
        self.mode = self._add_combo(grid, 1, "Mode", ["Image Edit", "Inpainting"], "Image Edit")
        self.mode.connect("changed", self._on_mode_changed)
        self.checkpoint, self.checkpoint_type, self.checkpoint_label = self._add_checkpoint_controls(grid, 2)
        self.workflow_selector = self._add_workflow_selector(grid, 3)
        self._ensure_default_workflows()
        self._refresh_workflow_selector()
        self.prompt = self._add_entry(grid, 4, "Prompt", "")
        self.negative_prompt = self._add_entry(grid, 5, "Negative prompt", "")
        self.unet = self._add_searchable_combo(grid, 6, "UNET")
        self.clip_l = self._add_searchable_combo(grid, 7, "Flux CLIP L")
        self.clip_t5 = self._add_searchable_combo(grid, 8, "Flux T5")
        self.krea_diffusion_model = self._add_searchable_combo(grid, 9, "Diffusion Model")
        self.krea_clip = self._add_searchable_combo(grid, 10, "Krea2 CLIP")
        self.lora_selector, self.lora_strength, self.lora_add_button, self.lora_rows = self._add_lora_controls(grid, 11)
        self.vae = self._add_searchable_combo(grid, 12, "VAE")
        self._update_vae_support()
        self.steps = self._add_spin(grid, 13, "Steps", 20, 1, 200, 1)
        self.cfg = self._add_spin(grid, 14, "CFG", 8.0, 1.0, 30.0, 0.5)
        self.denoise = self._add_spin(grid, 15, "Denoise", 1.0, 0.0, 1.0, 0.05)
        self.seed = self._add_spin(grid, 16, "Seed", -1, -1, 4294967295, 1)
        self.sampler = self._add_combo(grid, 17, "Sampler", ["euler", "euler_ancestral", "dpmpp_2m"], "euler")
        self.scheduler = self._add_combo(grid, 18, "Scheduler", ["normal", "karras", "simple"], "normal")
        self._profile_defaults = {"steps": 20, "cfg": 8.0, "denoise": 1.0, "sampler": "euler", "scheduler": "normal"}
        self.output_mode = self._add_combo(
            grid,
            19,
            "Output",
            ["GIMP layers", "New image", "Export directory"],
            "GIMP layers",
        )
        self.output_mode.connect("changed", self._on_output_mode_changed)
        self.output_directory = self._add_entry(grid, 20, "Export directory", "")
        self._on_output_mode_changed(self.output_mode)
        self.status = Gtk.Label(label="Ready", xalign=0)
        self.status.set_line_wrap(True)
        grid.attach(self.status, 0, 21, 2, 1)

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

        self._server_controls = [
            self.mode,
            self.checkpoint,
            self.checkpoint_type,
            self.workflow_selector,
            self.prompt,
            self.negative_prompt,
            self.unet,
            self.clip_l,
            self.clip_t5,
            self.krea_diffusion_model,
            self.krea_clip,
            self.lora_selector,
            self.lora_strength,
            self.lora_add_button,
            self.lora_rows,
            self.vae,
            self.steps,
            self.cfg,
            self.denoise,
            self.seed,
            self.sampler,
            self.scheduler,
            self.output_mode,
            self.output_directory,
            self.generate_button,
        ]

        self.show_all()
        self.checkpoint.get_child().connect("changed", self._on_checkpoint_changed)
        self.checkpoint_type.connect("changed", self._on_checkpoint_profile_changed)
        self._update_model_resource_support()
        self._apply_checkpoint_profile()
        if self.eraser_mode:
            self._configure_eraser_defaults()
        self._load_remote_options()

    @staticmethod
    def _add_entry(grid: Gtk.Grid, row: int, label_text: str, value: str) -> Gtk.Entry:
        label = Gtk.Label(label=label_text, xalign=0)
        entry = Gtk.Entry(text=value)
        entry.set_hexpand(True)
        entry._label_widget = label
        grid.attach(label, 0, row, 1, 1)
        grid.attach(entry, 1, row, 1, 1)
        return entry

    def _add_endpoint_row(self, grid: Gtk.Grid, row: int) -> tuple[Gtk.Entry, Gtk.Button]:
        """Add the ComfyUI URL field with a retry button that re-checks availability."""
        label = Gtk.Label(label="ComfyUI URL", xalign=0)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        entry = Gtk.Entry(text="http://127.0.0.1:8188")
        entry.set_hexpand(True)
        entry._label_widget = label
        entry.connect("activate", self._on_retry_connection)
        retry = Gtk.Button()
        retry.set_image(Gtk.Image.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON))
        retry.set_tooltip_text("Retry the connection to ComfyUI")
        retry.connect("clicked", self._on_retry_connection)
        box.pack_start(entry, True, True, 0)
        box.pack_start(retry, False, False, 0)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(box, 1, row, 1, 1)
        return entry, retry

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
        combo._label_widget = label
        grid.attach(label, 0, row, 1, 1)
        grid.attach(combo, 1, row, 1, 1)
        return combo

    @staticmethod
    def _add_checkpoint_controls(grid: Gtk.Grid, row: int):
        label = Gtk.Label(label="Family / Checkpoint", xalign=0)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        checkpoint = Gtk.ComboBoxText.new_with_entry()
        checkpoint.set_hexpand(True)
        profile = Gtk.ComboBoxText()
        for checkpoint_type in (
            CheckpointType.AUTO,
            CheckpointType.KREA2_TURBO,
            CheckpointType.FLUX,
            CheckpointType.SDXL,
            CheckpointType.SD15,
        ):
            profile.append_text(checkpoint_type.value)
        profile.set_active(0)
        profile.set_tooltip_text("Filter workflows and choose family-specific model resources")
        box.pack_start(profile, False, False, 0)
        box.pack_start(checkpoint, True, True, 0)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(box, 1, row, 1, 1)
        return checkpoint, profile, label

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
        return selector, strength, add_button, rows

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
            "mode": self.mode.get_active_text(),
            "prompt": self.prompt.get_text(),
            "negative_prompt": self.negative_prompt.get_text(),
            "checkpoint": self.checkpoint.get_child().get_text(),
            "checkpoint_type": self.checkpoint_type.get_active_text(),
            "unet": self.unet.get_child().get_text(),
            "clip_l": self.clip_l.get_child().get_text(),
            "clip_t5": self.clip_t5.get_child().get_text(),
            "diffusion_model": self.krea_diffusion_model.get_child().get_text(),
            "krea_clip": self.krea_clip.get_child().get_text(),
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
        mode = settings.get("mode")
        if mode in {"Image Edit", "Inpainting"}:
            self.mode.set_active(["Image Edit", "Inpainting"].index(mode))
        self.prompt.set_text(str(settings.get("prompt", "")))
        self.negative_prompt.set_text(str(settings.get("negative_prompt", "")))
        self.checkpoint.get_child().set_text(str(settings.get("checkpoint", "")))
        checkpoint_type = settings.get("checkpoint_type", CheckpointType.AUTO.value)
        profile_values = [item.value for item in CheckpointType]
        if checkpoint_type in profile_values:
            self.checkpoint_type.set_active(profile_values.index(checkpoint_type))
        self.unet.get_child().set_text(str(settings.get("unet", "")))
        self.clip_l.get_child().set_text(str(settings.get("clip_l", "")))
        self.clip_t5.get_child().set_text(str(settings.get("clip_t5", "")))
        self.krea_diffusion_model.get_child().set_text(str(settings.get("diffusion_model", "")))
        self.krea_clip.get_child().set_text(str(settings.get("krea_clip", "")))
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
        if not workflow_directory.is_dir():
            workflow_directory = Path(__file__).resolve().parents[1] / "workflows"
        self.workflow_registry.add([
            workflow_directory / "sdxl-image-edit-api.json",
            workflow_directory / "sdxl-inpainting-api.json",
            workflow_directory / "sd15-image-edit-api.json",
            workflow_directory / "sd15-inpainting-api.json",
            workflow_directory / "flux-image-edit-api.json",
            workflow_directory / "flux-inpainting-api.json",
            workflow_directory / "krea2-turbo-text-to-image-api.json",
        ])

    def _configure_eraser_defaults(self) -> None:
        """Select the bundled inpainting workflow and eraser prompt."""
        self.mode.set_active(1)
        self._refresh_workflow_selector()
        workflows = self.workflow_registry.list()
        inpainting = next(
            (item["path"] for item in workflows if Path(item["path"]).name == "sdxl-inpainting-api.json"),
            None,
        )
        if inpainting:
            self.workflow_selector.set_active_id(inpainting)
        self.prompt.set_text("Remove the selected object and reconstruct the background naturally")
        self.negative_prompt.set_text("visible seams, artifacts, distortion, duplicated objects")
        self.denoise.set_value(1.0)
        self.status.set_text("Paint the erase area with GIMP's brush, then click Generate")

    def _refresh_workflow_selector(self) -> None:
        self.workflow_selector.remove_all()
        mode = self.mode.get_active_text() if hasattr(self, "mode") else "Image Edit"
        family = self._selected_checkpoint_type()
        workflows = [
            workflow for workflow in self.workflow_registry.list()
            if Path(workflow["path"]).is_file()
            if ("inpainting" in Path(workflow["path"]).stem.casefold()) == (mode == "Inpainting")
            if self._workflow_matches_family(workflow["path"], family)
            if mode != "Inpainting" or self._workflow_supports_selected_inpainting(workflow["path"], family)
        ]
        for workflow in workflows:
            self.workflow_selector.append(workflow["path"], f'{workflow["title"]} - {workflow["path"]}')
        selected = self.workflow_registry.selected_path or (workflows[0]["path"] if workflows else None)
        if selected not in {workflow["path"] for workflow in workflows}:
            selected = workflows[0]["path"] if workflows else None
        if selected is not None:
            self.workflow_selector.set_active_id(selected)
        self._update_vae_support()
        self._update_model_resource_support()

    def _on_mode_changed(self, _selector: Gtk.ComboBoxText) -> None:
        if not family_supports_mode(self._selected_checkpoint_type(), self.mode.get_active_text() or ""):
            profile_values = [item.value for item in CheckpointType]
            self.checkpoint_type.set_active(profile_values.index(CheckpointType.AUTO.value))
        self._refresh_workflow_selector()
        self._apply_checkpoint_profile()

    def _on_output_mode_changed(self, selector: Gtk.ComboBoxText) -> None:
        """Show the export directory only when directory output is selected."""
        if not hasattr(self, "output_directory"):
            return
        self._set_control_visibility(
            self.output_directory,
            selector.get_active_text() == "Export directory",
        )

    def _on_workflow_changed(self, selector: Gtk.ComboBoxText) -> None:
        selected = selector.get_active_id()
        if selected:
            self.workflow_registry.select(selected)
        self._update_vae_support()
        self._update_model_resource_support()
        self._apply_checkpoint_profile()

    def _on_checkpoint_changed(self, _entry: Gtk.Entry) -> None:
        self._update_family_resource_guesses()
        self._apply_checkpoint_profile()

    def _on_checkpoint_profile_changed(self, _selector: Gtk.ComboBoxText) -> None:
        self._refresh_workflow_selector()
        self._update_family_resource_guesses()
        self._apply_checkpoint_profile()

    def _selected_checkpoint_type(self) -> CheckpointType:
        if not hasattr(self, "checkpoint_type"):
            return CheckpointType.AUTO
        try:
            return CheckpointType(self.checkpoint_type.get_active_text() or CheckpointType.AUTO.value)
        except ValueError:
            return CheckpointType.AUTO

    @staticmethod
    def _workflow_matches_family(workflow_path: str, family: CheckpointType) -> bool:
        try:
            return workflow_matches_checkpoint_type(load_workflow(workflow_path), family)
        except (OSError, ValueError):
            return False

    @staticmethod
    def _workflow_supports_selected_inpainting(workflow_path: str, family: CheckpointType) -> bool:
        if family == CheckpointType.KREA2_TURBO:
            return False
        try:
            return workflow_supports_inpainting(load_workflow(workflow_path))
        except (OSError, ValueError):
            return False

    def _apply_checkpoint_profile(self) -> None:
        if not hasattr(self, "steps"):
            return
        workflow_path = self.workflow_selector.get_active_id()
        if not workflow_path:
            return
        try:
            workflow = load_workflow(workflow_path)
            override = self._selected_checkpoint_type()
            profile = checkpoint_profile(workflow, self.checkpoint.get_child().get_text(), override)
        except (OSError, ValueError):
            return
        values = {
            "steps": profile.steps,
            "cfg": profile.cfg,
            "denoise": profile.denoise,
            "sampler": profile.sampler,
            "scheduler": profile.scheduler,
        }
        if self.steps.get_value_as_int() == self._profile_defaults["steps"]:
            self.steps.set_value(values["steps"])
        if self.cfg.get_value() == self._profile_defaults["cfg"]:
            self.cfg.set_value(values["cfg"])
        if self.denoise.get_value() == self._profile_defaults["denoise"]:
            self.denoise.set_value(values["denoise"])
        if self.sampler.get_active_text() == self._profile_defaults["sampler"]:
            self._replace_combo_options(self.sampler, [values["sampler"]])
        if self.scheduler.get_active_text() == self._profile_defaults["scheduler"]:
            self._replace_combo_options(self.scheduler, [values["scheduler"]])
        self._profile_defaults = values
        self.status.set_text(f"Profile: {profile.checkpoint_type.value} ({profile.confidence} confidence)")

    def _update_vae_support(self) -> None:
        if not hasattr(self, "vae"):
            return
        selected = self.workflow_selector.get_active_id()
        if not selected:
            self._set_control_visibility(self.vae, False)
            self.vae.set_sensitive(False)
            return
        try:
            has_vae = workflow_supports_vae(load_workflow(selected))
            self._set_control_visibility(self.vae, has_vae)
            self.vae.set_sensitive(has_vae and self._server_available)
        except Exception:
            self._set_control_visibility(self.vae, False)
            self.vae.set_sensitive(False)

    def _update_model_resource_support(self) -> None:
        if not hasattr(self, "unet"):
            return
        selected = self.workflow_selector.get_active_id()
        selected_family = self._selected_checkpoint_type()
        if not selected:
            show_negative_prompt = selected_family in {CheckpointType.AUTO, CheckpointType.SDXL, CheckpointType.SD15}
            self._set_control_visibility(self.negative_prompt, show_negative_prompt)
            if selected_family == CheckpointType.AUTO:
                self._update_primary_model_field(selected_family)
                self._set_control_visibility(self.checkpoint, True)
                for control in (self.unet, self.clip_l, self.clip_t5, self.krea_diffusion_model, self.krea_clip, self.vae):
                    self._set_control_visibility(control, False)
                    control.set_sensitive(False)
                self.checkpoint.set_sensitive(False)
                return
            show_checkpoint = selected_family in {CheckpointType.SDXL, CheckpointType.SD15}
            show_flux_resources = selected_family == CheckpointType.FLUX
            show_krea_resource = selected_family == CheckpointType.KREA2_TURBO
            self._update_primary_model_field(selected_family)
            self._set_control_visibility(self.checkpoint, True)
            self._set_control_visibility(self.unet, False)
            self._set_control_visibility(self.clip_l, show_flux_resources)
            self._set_control_visibility(self.clip_t5, show_flux_resources)
            self._set_control_visibility(self.krea_diffusion_model, False)
            self._set_control_visibility(self.krea_clip, show_krea_resource)
            self._set_control_visibility(self.vae, True)
            self.checkpoint.set_sensitive(show_checkpoint or show_flux_resources or show_krea_resource)
            self.unet.set_sensitive(False)
            self.clip_l.set_sensitive(show_flux_resources)
            self.clip_t5.set_sensitive(show_flux_resources)
            self.krea_diffusion_model.set_sensitive(False)
            self.krea_clip.set_sensitive(show_krea_resource)
            self._enforce_server_availability()
            return
        try:
            workflow = load_workflow(selected)
            classes = {node.get("class_type") for node in workflow.values() if isinstance(node, dict)}
        except (OSError, ValueError):
            classes = set()
            workflow = {}
        family = selected_family
        is_auto = family == CheckpointType.AUTO
        if is_auto:
            family = infer_checkpoint_type(workflow)
        self._update_primary_model_field(family)
        show_negative_prompt = family not in {CheckpointType.FLUX, CheckpointType.KREA2_TURBO}
        self._set_control_visibility(self.negative_prompt, show_negative_prompt)
        show_checkpoint = family in {CheckpointType.SDXL, CheckpointType.SD15} and (
            not is_auto or bool({"CheckpointLoader", "CheckpointLoaderSimple"} & classes)
        )
        show_flux_resources = family == CheckpointType.FLUX and (
            not is_auto or bool({"UNETLoader", "DualCLIPLoader"} & classes)
        )
        show_krea_resource = family == CheckpointType.KREA2_TURBO and (
            not is_auto or "CLIPLoader" in classes
        )
        self._set_control_visibility(self.checkpoint, True)
        self._set_control_visibility(self.unet, False)
        self._set_control_visibility(self.clip_l, show_flux_resources)
        self._set_control_visibility(self.clip_t5, show_flux_resources)
        self._set_control_visibility(self.krea_diffusion_model, False)
        self._set_control_visibility(self.krea_clip, show_krea_resource)
        self.checkpoint.set_sensitive(show_checkpoint or show_flux_resources or show_krea_resource)
        self.unet.set_sensitive(False)
        self.clip_l.set_sensitive(show_flux_resources)
        self.clip_t5.set_sensitive(show_flux_resources)
        self.krea_diffusion_model.set_sensitive(False)
        self.krea_clip.set_sensitive(show_krea_resource)
        show_vae = (
            family in {
                CheckpointType.KREA2_TURBO,
                CheckpointType.FLUX,
                CheckpointType.SDXL,
                CheckpointType.SD15,
            }
            if not is_auto
            else workflow_supports_vae(workflow)
        )
        self._set_control_visibility(self.vae, show_vae)
        self._enforce_server_availability()
        return

    def _update_primary_model_field(self, family: CheckpointType) -> None:
        """Change the primary model field label and options for a family."""
        uses_diffusion_model = family in {CheckpointType.FLUX, CheckpointType.KREA2_TURBO}
        self.checkpoint_label.set_text("Family / Diffusion Model" if uses_diffusion_model else "Family / Checkpoint")
        self.checkpoint.get_child().set_placeholder_text(
            "Select diffusion model" if uses_diffusion_model else "Select checkpoint"
        )
        option_key = "unets" if uses_diffusion_model else "checkpoints"
        self._replace_combo_options(self.checkpoint, self._remote_options.get(option_key, []))

    def _update_family_resource_guesses(self) -> None:
        """Choose likely CLIP resources after family or model changes."""
        family = self._selected_checkpoint_type()
        workflow_path = self.workflow_selector.get_active_id()
        if family == CheckpointType.AUTO and workflow_path:
            try:
                family = infer_checkpoint_type(load_workflow(workflow_path))
            except (OSError, ValueError):
                return
        if family == CheckpointType.FLUX:
            self._select_best_guess(self.clip_l, self._remote_options.get("clips", []), ("clip_l", "clip-l", "clipl"))
            self._select_best_guess(self.clip_t5, self._remote_options.get("clip_t5", []), ("t5", "t5xxl"))
        elif family == CheckpointType.KREA2_TURBO:
            self._select_best_guess(
                self.krea_clip,
                self._remote_options.get("krea_clips", []),
                ("krea2", "krea", "qwen"),
            )

    @staticmethod
    def _select_best_guess(combo: Gtk.ComboBoxText, options: list[str], hints: tuple[str, ...]) -> None:
        current = combo.get_child().get_text().strip()
        guess = best_guess_option(options, hints, current)
        if guess is not None:
            combo.get_child().set_text(guess)

    @staticmethod
    def _set_control_visibility(control: Gtk.Widget, is_visible: bool) -> None:
        control.set_visible(is_visible)
        label = getattr(control, "_label_widget", None)
        if label is not None:
            label.set_visible(is_visible)

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

    def _on_retry_connection(self, _widget: Gtk.Widget) -> None:
        """Re-check ComfyUI availability using the URL currently in the entry."""
        self.status.set_text(f"Checking ComfyUI at {self.endpoint.get_text()}...")
        self._load_remote_options()

    def _load_remote_options(self) -> None:
        """Fetch model and sampler options without blocking the GTK thread."""
        if self._options_fetch_active:
            return
        self._options_fetch_active = True
        self.retry_button.set_sensitive(False)
        endpoint = self.endpoint.get_text()
        threading.Thread(target=self._fetch_remote_options, args=(endpoint,), daemon=True).start()

    def _fetch_remote_options(self, endpoint: str) -> None:
        try:
            client = ComfyUIClient(endpoint, timeout=10)
            options = {
                "checkpoints": client.get_available_checkpoints(),
                "unets": client.get_available_unets(),
                "clips": client.get_available_clip_models(),
                "clip_t5": client.get_available_clip_models("clip_name2"),
                "krea_diffusion_models": client.get_available_unets(),
                "krea_clips": client.get_available_krea_clips(),
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
        self.retry_button.set_sensitive(True)
        self._options_fetch_active = False
        self._server_available = True
        self._remote_options = options
        self._set_server_availability(True)
        self._replace_combo_options(self.unet, options["unets"])
        self._replace_combo_options(self.clip_l, options["clips"])
        self._replace_combo_options(self.clip_t5, options["clip_t5"])
        self._replace_combo_options(self.krea_diffusion_model, options["krea_diffusion_models"])
        self._replace_combo_options(self.krea_clip, options["krea_clips"])
        self._replace_combo_options(self.lora_selector, options["loras"])
        self._replace_combo_options(self.vae, options["vaes"])
        self._replace_combo_options(self.sampler, options["samplers"])
        self._replace_combo_options(self.scheduler, options["schedulers"])
        self._update_model_resource_support()
        self._update_family_resource_guesses()
        self._apply_checkpoint_profile()
        self._set_status_connected()
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
        """Disable server-dependent controls and flag the status when ComfyUI is unreachable."""
        self.retry_button.set_sensitive(True)
        self._options_fetch_active = False
        self._server_available = False
        self._set_server_availability(False)
        detail = GLib.markup_escape_text(message)
        self.status.set_markup(
            f'<span weight="bold" foreground="#c01c28">ComfyUI is unavailable: {detail}. '
            "Check the URL or start ComfyUI, then retry.</span>"
        )
        return False

    def _set_status_connected(self) -> None:
        self.status.set_markup('<span weight="bold" foreground="#2ec27e">Connected to ComfyUI</span>')

    def _set_server_availability(self, available: bool) -> None:
        """Toggle every control that needs ComfyUI; the URL entry and retry button stay editable."""
        for control in self._server_controls:
            control.set_sensitive(available)
        if available:
            # Re-apply workflow- and family-driven sensitivity rules so fields such as
            # UNET stay disabled when the selected workflow does not use them.
            self._update_vae_support()
            self._update_model_resource_support()

    def _enforce_server_availability(self) -> None:
        """Keep server-dependent controls disabled after sensitivity recalculation while offline."""
        if not self._server_available:
            for control in self._server_controls:
                control.set_sensitive(False)

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
            if event.node_id and event.node_type:
                message = f"Executing {event.node_type} (node {event.node_id})"
            elif event.node_id:
                message = f"Executing node {event.node_id}"
            else:
                message = "Executing..."
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
            if self.mode.get_active_text() == "Inpainting" and (
                self.image is None or Gimp.Selection.is_empty(self.image)
            ):
                raise ValueError("Paint an inpainting area with GIMP's brush before generating")
            workflow = load_workflow(workflow_path)
            profile = checkpoint_profile(
                workflow,
                self.checkpoint.get_child().get_text(),
                CheckpointType(self.checkpoint_type.get_active_text() or CheckpointType.AUTO.value),
            )
            validate_checkpoint_workflow(profile.checkpoint_type, workflow)
            primary_model = self.checkpoint.get_child().get_text() or None
            unet = primary_model if profile.checkpoint_type == CheckpointType.FLUX else self.unet.get_child().get_text() or None
            diffusion_model = (
                primary_model
                if profile.checkpoint_type == CheckpointType.KREA2_TURBO
                else self.krea_diffusion_model.get_child().get_text() or None
            )
            client = ComfyUIClient(self.endpoint.get_text())
            self.active_client = client
            coordinator = GenerationCoordinator(client)
            self.active_coordinator = coordinator
            self.cancel_requested = False
            input_path = self._stage_input_image()
            mask_path = self._stage_mask_image()
            settings = {
                "mode": self.mode.get_active_text(),
                "prompt": self.prompt.get_text(),
                "negative_prompt": self.negative_prompt.get_text(),
                "checkpoint": self.checkpoint.get_child().get_text() or None,
                "checkpoint_type": self.checkpoint_type.get_active_text(),
                "unet": unet,
                "clip_l": self.clip_l.get_child().get_text() or None,
                "clip_t5": self.clip_t5.get_child().get_text() or None,
                "diffusion_model": diffusion_model,
                "krea_clip": self.krea_clip.get_child().get_text() or None,
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
                    unet=settings["unet"],
                    clip_l=settings["clip_l"],
                    clip_t5=settings["clip_t5"],
                    diffusion_model=settings["diffusion_model"],
                    krea_clip=settings["krea_clip"],
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
        self.generate_button.set_sensitive(self._server_available)
        return False

    def _show_error(self, message: str) -> bool:
        self.status.set_text(f"Error: {message}")
        self.generate_button.set_sensitive(self._server_available)
        Gimp.message(message)
        return False

    def _on_cancel(self, _button: Gtk.Button) -> None:
        self.completed = False
        self.cancel_requested = True
        coordinator = self.active_coordinator
        if coordinator is not None and self.worker and self.worker.is_alive():
            threading.Thread(target=coordinator.cancel, daemon=True).start()
        self.response(Gtk.ResponseType.CANCEL)