import bpy
from bpy.types import Panel
from . import utils


def _status_text() -> str:
    if utils.is_using_aces():
        return "Current Mode: ACES"
    if utils.get_ocio_config_override():
        return "Current Mode: Custom OCIO (non-ACES)"
    return "Current Mode: Blender Default"

def _get_debug_info() -> str:
    """Get debug information for troubleshooting."""
    blender_version = utils.get_blender_version_info()
    ocio_path = utils.get_ocio_config_override()
    aces_installed = utils.is_aces_installed()
    
    info = f"Blender Version: {blender_version}"
    if ocio_path:
        info += f" | OCIO: {ocio_path}"
    info += f" | ACES Installed: {'Yes' if aces_installed else 'No'}"
    
    return info


class BAM_PT_main_panel(Panel):
    bl_idname = "BAM_PT_main_panel"
    bl_label = "ACES Switcher"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'

    def draw(self, context):
        layout = self.layout
        prefs = utils.get_addon_prefs(context)

        # Status section
        col = layout.column(align=True)
        col.label(text=_status_text())
        
        # Debug info (collapsible)
        box = layout.box()
        box.label(text="Debug Info", icon='INFO')
        debug_col = box.column(align=True)
        debug_col.label(text=_get_debug_info())
        
        # ACES installation status
        if not utils.is_aces_installed():
            # Check if installation is in progress
            installing = False
            for op in context.window_manager.operators:
                if op.bl_idname == "bam.install_aces" and op.is_installing:
                    installing = True
                    break
            
            if installing:
                # Show progress
                for op in context.window_manager.operators:
                    if op.bl_idname == "bam.install_aces" and op.is_installing:
                        col.label(text=op.progress_message)
                        col.prop(op, "progress_percentage", text="Progress")
                        col.operator("bam.cancel_install", text="Cancel")
                        break
            else:
                col.operator("bam.install_aces")
        else:
            col.label(text="ACES config installed")

        # Control buttons
        row = layout.row(align=True)
        row.operator("bam.switch_to_aces")
        row.operator("bam.switch_to_default")
        
        # Validation button
        layout.operator("bam.validate_config")

        # Preferences section
        prefs_box = layout.box()
        prefs_box.label(text="Preferences")
        prefs_box.prop(prefs, "auto_restart")
        prefs_box.prop(prefs, "aces_repo_preference")

        # Updates section
        upd_box = layout.box()
        upd_box.label(text="Add-on Updates")
        row = upd_box.row(align=True)
        row.operator("bam.check_update", text="Check for Updates", icon='FILE_REFRESH')
        row.operator("bam.update_addon", text="Update Now", icon='IMPORT')
        upd_box.prop(prefs, "auto_check_updates")
        upd_box.prop(prefs, "include_prereleases")
        upd_box.prop(prefs, "update_repo")

        # Show current update status
        state = utils.get_cached_update_state()
        if state:
            status_col = upd_box.column(align=True)
            current = state.get("current_version", "?")
            latest = state.get("latest_version", "?")
            available = bool(state.get("update_available"))
            status_col.label(text=f"Current: {current}  Latest: {latest}")
            status_col.label(text=("Update available" if available else "Up to date"))


classes = (
    BAM_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


