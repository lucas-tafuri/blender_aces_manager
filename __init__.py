bl_info = {
    "name": "Blender ACES Manager",
    "author": "Lucas Tafuri",
    "version": (1, 0, 8),
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

    auto_check_updates: BoolProperty(
        name="Auto-Check for Updates",
        description="Check for updates shortly after enabling Blender",
        default=True,
    )

    include_prereleases: BoolProperty(
        name="Include Pre-releases",
        description="Consider pre-release versions when checking for updates",
        default=False,
    )

    update_repo: StringProperty(
        name="Update Repo",
        description="GitHub repo to check for updates (owner/name)",
        default="lucas-tafuri/blender_aces_manager",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Blender ACES Manager Preferences")
        layout.prop(self, "aces_repo_preference")
        layout.prop(self, "auto_restart")
        box = layout.box()
        box.label(text="Updater")
        box.prop(self, "auto_check_updates")
        box.prop(self, "include_prereleases")
        box.prop(self, "update_repo")


classes = (
    BAM_AddonPreferences,
)


def register():
    from . import operators as _operators
    from . import ui as _ui
    from . import utils as _utils

    for cls in classes:
        bpy.utils.register_class(cls)

    # Add scene property for advanced options toggle
    bpy.types.Scene.bam_show_advanced = BoolProperty(
        name="Show Advanced Options",
        description="Show advanced options and technical details",
        default=False
    )

    _operators.register()
    _ui.register()
    # Schedule an update check if enabled
    try:
        prefs = _utils.get_addon_prefs()
        if getattr(prefs, "auto_check_updates", True):
            _utils.schedule_update_check_once(3.0)
    except Exception:
        pass


def unregister():
    from . import operators as _operators
    from . import ui as _ui

    _ui.unregister()
    _operators.unregister()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # Remove scene property
    if hasattr(bpy.types.Scene, "bam_show_advanced"):
        del bpy.types.Scene.bam_show_advanced


if __name__ == "__main__":
    register()


