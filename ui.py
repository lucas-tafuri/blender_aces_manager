import bpy
from bpy.types import Panel
from . import utils


def _get_current_status_icon() -> str:
    """Get appropriate icon for current ACES status."""
    if utils.is_using_aces():
        return 'CHECKMARK'
    if utils.get_ocio_config_override():
        return 'ERROR'
    return 'DOT'


def _get_current_status_text() -> str:
    """Get user-friendly status text."""
    if utils.is_using_aces():
        return "ACES Active"
    if utils.get_ocio_config_override():
        return "Custom OCIO"
    return "Blender Default"


def _get_version_info() -> dict:
    """Get all version information."""
    # Plugin version - hardcoded since dynamic detection isn't working in Blender
    plugin_ver_str = "1.0.7"

    try:
        # ACES version
        aces_installed = utils.is_aces_installed()
        aces_version = "Not installed"
        if aces_installed:
            aces_ver = utils.get_installed_aces_version()
            if aces_ver and aces_ver != "unknown":
                aces_version = aces_ver
    except Exception:
        aces_installed = False
        aces_version = "Error checking"

    try:
        # Blender version
        blender_version = utils.get_blender_version_info()
    except Exception:
        blender_version = "Unknown"

    return {
        'plugin': plugin_ver_str,
        'aces': aces_version,
        'blender': blender_version,
        'aces_installed': aces_installed
    }


class BAM_PT_main_panel(Panel):
    bl_idname = "BAM_PT_main_panel"
    bl_label = "ACES Manager"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'

    def draw(self, context):
        layout = self.layout
        prefs = utils.get_addon_prefs(context)

        # === STATUS HEADER ===
        box = layout.box()
        header_row = box.row(align=True)

        # Status icon and text with larger, bolder styling
        status_icon = _get_current_status_icon()
        status_text = _get_current_status_text()
        
        # Make the status more prominent
        header_row.label(text="Current color space:", icon='NONE')
        
        # Apply custom styling for ACES Active status
        if status_text == "ACES Active":
            # Make ACES Active text prominent with green checkmark icon
            header_row.label(text="ACES Active", icon='CHECKMARK')  # Green checkmark icon
        elif status_text == "Blender Default":
            # Make Blender Default text prominent with yellow icon
            header_row.label(text=status_text, icon='SOLO_ON')  # Yellow icon
        else:
            # Show normal status text for other states
            header_row.label(text=status_text, icon=status_icon)

        # === VERSION INFORMATION ===
        version_info = _get_version_info()

        # ACES Version
        aces_row = box.row(align=True)
        aces_row.label(text="ACES:", icon='COLOR')
        if version_info['aces_installed']:
            aces_row.label(text=version_info['aces'])
        else:
            aces_row.label(text=version_info['aces'], icon='ERROR')

        # Plugin Version
        plugin_row = box.row(align=True)
        plugin_row.label(text="Plugin:", icon='BLENDER')
        plugin_row.label(text=version_info['plugin'])

        # Blender Version
        blender_row = box.row(align=True)
        blender_row.label(text="Blender:", icon='BLENDER')
        blender_row.label(text=version_info['blender'])

        # === ACTION BUTTONS ===
        layout.separator()

        # Check if ACES installation is in progress
        installing = any(
            op.bl_idname == "bam.install_aces" and op.is_installing
            for op in context.window_manager.operators
        )

        if installing:
            # Show installation progress
            for op in context.window_manager.operators:
                if op.bl_idname == "bam.install_aces" and op.is_installing:
                    col = layout.column(align=True)
                    col.label(text=op.progress_message, icon='TIME')
                    col.prop(op, "progress_percentage", text="Progress")
                    col.operator("bam.cancel_install", text="Cancel", icon='X')
                    break
        # Always show Install ACES button if not installed or if there's an error
        aces_installed = version_info.get('aces_installed', False)
        
        if not aces_installed:
            # ACES not installed - show install button
            col = layout.column(align=True)
            col.operator("bam.install_aces", text="Install ACES", icon='PLUS')
        else:
            # ACES installed - show switch buttons
            row = layout.row(align=True)

            # Smart toggle button that switches between modes
            try:
                if utils.is_using_aces():
                    # Currently using ACES, so button switches to default
                    row.operator("bam.switch_to_default", text="Switch to Default", icon='LOOP_FORWARDS')
                else:
                    # Currently using default, so button switches to ACES
                    row.operator("bam.switch_to_aces", text="Switch to ACES", icon='CHECKMARK')
            except Exception:
                # Fallback if there's an error checking ACES status
                row.operator("bam.switch_to_aces", text="Switch to ACES", icon='CHECKMARK')

        # === ADVANCED OPTIONS ===
        layout.separator()

        # Collapsible advanced section
        advanced_box = layout.box()
        advanced_row = advanced_box.row(align=True)
        advanced_row.prop(context.scene, "bam_show_advanced", text="",
                         icon='TRIA_DOWN' if context.scene.get("bam_show_advanced", False)
                              else 'TRIA_RIGHT', emboss=False)
        advanced_row.label(text="Advanced Options")

        if context.scene.get("bam_show_advanced", False):
            # Debug info section
            debug_box = advanced_box.box()
            debug_box.label(text="Debug Info", icon='INFO')
            debug_col = debug_box.column(align=True)
            debug_col.label(text=f"ACES Installed: {version_info.get('aces_installed', 'Error')}")
            debug_col.label(text=f"ACES Version: {version_info.get('aces', 'Error')}")
            debug_col.label(text=f"Plugin Version: {version_info.get('plugin', 'Error')}")
            debug_col.label(text=f"Blender Version: {version_info.get('blender', 'Error')}")
            
            # Update section
            update_row = advanced_box.row(align=True)
            update_row.operator("bam.check_update", text="Check Updates", icon='FILE_REFRESH')
            update_row.operator("bam.update_addon", text="Update Plugin", icon='IMPORT')

            # Show update status
            state = utils.get_cached_update_state()
            if state:
                current = state.get("current_version", "?")
                latest = state.get("latest_version", "?")
                available = bool(state.get("update_available"))
                status_row = advanced_box.row(align=True)
                status_row.label(text=f"Plugin: {current} → {latest}")
                if available:
                    status_row.label(text="Update available!", icon='ERROR')
                else:
                    status_row.label(text="Up to date", icon='CHECKMARK')

            # ACES Management
            if version_info['aces_installed']:
                aces_manage_row = advanced_box.row(align=True)
                aces_manage_row.operator("bam.uninstall_aces", text="Uninstall ACES", icon='TRASH')
                aces_manage_row.operator("bam.validate_config", text="Validate", icon='VIEWZOOM')

            # Preferences
            pref_row = advanced_box.row()
            pref_row.prop(prefs, "auto_restart")


classes = (
    BAM_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


