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

    def do_set_i18n(self, procedure_name):
        """Disable gettext lookup until translated catalogs are shipped."""
        return False, None, None

    def do_query_procedures(self):
        """Return the procedures registered by this plug-in."""
        return ["python-fu-comfyui-batch"]

    def do_create_procedure(self, name):
        """Create the GIMP procedure associated with ``name``."""
        procedure = Gimp.ImageProcedure.new(self, name, Gimp.PDBProcType.PLUGIN, self.run, None)
        procedure.set_menu_label("ComfyUI Batch...")
        procedure.add_menu_path("<Image>/Filters/AI")
        procedure.set_documentation(
            "Process images through ComfyUI",
            "Submit an image batch to a ComfyUI workflow.",
            name,
        )
        procedure.set_attribution("GIMP Plugin ComfyUI contributors", "GIMP Plugin ComfyUI contributors", "2026")
        procedure.set_image_types("*")
        return procedure

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        """Open the interactive generation dialog for a GIMP image."""
        if run_mode != Gimp.RunMode.INTERACTIVE:
            return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, None)
        GimpUi.init("gimp-comfyui")
        dialog = ComfyUIGenerationDialog(image)
        response = dialog.run()
        dialog.destroy()
        status = Gimp.PDBStatusType.SUCCESS if dialog.completed else Gimp.PDBStatusType.CANCEL
        return procedure.new_return_values(status, None)


Gimp.main(ComfyUIPlugin.__gtype__, sys.argv)