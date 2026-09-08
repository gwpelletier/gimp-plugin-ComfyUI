#!/usr/bin/env python3
"""GIMP 3 entry point; keep protocol and workflow logic outside this module."""

import sys

import gi

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
from gi.repository import Gimp, GimpUi

from comfyui_plugin.gimp_ui import ComfyUIGenerationDialog


class ComfyUIPlugin(Gimp.PlugIn):
    """GIMP 3 procedure owner for the ComfyUI generation dialog."""

    _GENERATE_PROCEDURE = "python-fu-comfyui-generate"
    _GENERATE_IMAGE_PROCEDURE = "python-fu-comfyui-generate-image"
    _ERASER_PROCEDURE = "python-fu-comfyui-eraser"

    def do_set_i18n(self, procedure_name):
        """Disable gettext lookup until translated catalogs are shipped."""
        return False, None, None

    def do_query_procedures(self):
        """Return the procedures registered by this plug-in."""
        return [self._GENERATE_PROCEDURE, self._GENERATE_IMAGE_PROCEDURE, self._ERASER_PROCEDURE]

    def do_create_procedure(self, name):
        """Create the GIMP procedure associated with ``name``."""
        is_eraser = name == self._ERASER_PROCEDURE
        is_image_generation = name == self._GENERATE_IMAGE_PROCEDURE
        if is_image_generation:
            procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, self.run, None)
            procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.ALWAYS)
            procedure.set_menu_label("Generate Image...")
            procedure.add_menu_path("<Image>/Tools/ComfyUI")
        else:
            procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, self.run, None)
            procedure.set_menu_label("AI Eraser..." if is_eraser else "Generate...")
            procedure.add_menu_path("<Image>/Filters/ComfyUI")
        procedure.set_documentation(
            "Erase selected objects with ComfyUI" if is_eraser else "Generate images with ComfyUI",
            "Paint an erase mask with GIMP's brush and fill it with ComfyUI."
            if is_eraser
            else "Submit an image batch to a ComfyUI workflow.",
            name,
        )
        procedure.set_attribution("GIMP Plugin ComfyUI contributors", "GIMP Plugin ComfyUI contributors", "2026")
        if not is_image_generation:
            procedure.set_image_types("*")
        return procedure

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        """Open the interactive generation dialog for a GIMP image."""
        return self._run_dialog(procedure, run_mode, image)

    @staticmethod
    def _run_dialog(procedure, run_mode, image):
        if run_mode != Gimp.RunMode.INTERACTIVE:
            return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, None)
        GimpUi.init("gimp-comfyui")
        is_eraser = procedure.get_name() == "python-fu-comfyui-eraser"
        generation_mode = "Inpainting" if is_eraser else "Text to Image" if image is None else "Image Edit"
        dialog = ComfyUIGenerationDialog(image, eraser_mode=is_eraser, generation_mode=generation_mode)
        dialog.run()
        dialog.destroy()
        status = Gimp.PDBStatusType.SUCCESS if dialog.completed else Gimp.PDBStatusType.CANCEL
        return procedure.new_return_values(status, None)


Gimp.main(ComfyUIPlugin.__gtype__, sys.argv)