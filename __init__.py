bl_info = {
    "name": "Blender ACES Manager",
    "author": "Lucas Tafuri",
    "version": (1, 0, 1),
    "blender": (3, 0, 0),
    "location": "Render Properties > ACES Switcher",
    "description": "Download and switch between Blender default color management and ACES (with auto-restart)",
    "category": "System",
}

import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty, BoolProperty


class BAM_AddonPreferences(AddonPreferences):
    bl_idname = __package__ if __package__ else "blender_aces_manager"

    aces_repo_preference: StringProperty(
        name="Custom ACES Repo (Zip) [Optional]",
        description="Optional custom ZIP URL to an ACES OCIO config. Leave empty to use defaults.",
        default="",
    )

    auto_restart: BoolProperty(
        name="Auto-Restart Blender",
        description="Automatically restart Blender after switching color management",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Blender ACES Manager Preferences")
        layout.prop(self, "aces_repo_preference")
        layout.prop(self, "auto_restart")


classes = (
    BAM_AddonPreferences,
)


def register():
    from . import operators as _operators
    from . import ui as _ui

    for cls in classes:
        bpy.utils.register_class(cls)

    _operators.register()
    _ui.register()


def unregister():
    from . import operators as _operators
    from . import ui as _ui

    _ui.unregister()
    _operators.unregister()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()


