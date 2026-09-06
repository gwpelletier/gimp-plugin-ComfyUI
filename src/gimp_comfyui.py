#!/usr/bin/env python3
"""GIMP 3 entry point; keep protocol and workflow logic outside this module."""

import sys

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp


class ComfyUIPlugin(Gimp.PlugIn):
    def do_query_procedures(self):
        return ["python-fu-comfyui-batch"]

    def do_create_procedure(self, name):
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
        # The dockable UI and worker queue will be added in the next slice.
        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)


Gimp.main(ComfyUIPlugin.__gtype__, sys.argv)