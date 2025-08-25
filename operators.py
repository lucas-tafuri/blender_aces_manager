import bpy
from bpy.types import Operator
from bpy.props import BoolProperty, StringProperty, IntProperty
from . import utils
import threading
import time


class BAM_OT_install_aces(Operator):
    bl_idname = "bam.install_aces"
    bl_label = "Install ACES"
    bl_description = "Download and install an ACES OCIO configuration"
    bl_options = {'INTERNAL'}

    # Progress tracking properties
    progress_message: StringProperty(default="Preparing installation...")
    progress_percentage: IntProperty(default=0)
    is_installing: BoolProperty(default=False)
    installation_thread: threading.Thread = None
    installation_complete: BoolProperty(default=False)
    installation_success: BoolProperty(default=False)
    installation_message: StringProperty(default="")

    def execute(self, context):
        if self.is_installing:
            return {'CANCELLED'}
        
        self.is_installing = True
        self.installation_complete = False
        self.installation_success = False
        self.installation_message = ""
        self.progress_percentage = 0
        self.progress_message = "Starting installation..."
        
        # Start installation in background thread
        self.installation_thread = threading.Thread(target=self._install_aces_thread, daemon=True)
        self.installation_thread.start()
        
        # Start modal operator to show progress
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _install_aces_thread(self):
        """Install ACES in background thread."""
        try:
            prefs = utils.get_addon_prefs()
            urls = []
            if prefs.aces_repo_preference.strip():
                urls.append(prefs.aces_repo_preference.strip())
            urls.extend(utils.DEFAULT_ZIP_URLS)

            last_error = None
            for url in urls:
                try:
                    ok, _config_dir, msg = utils.install_aces_from_zip_url(
                        url, 
                        progress_callback=self._progress_callback
                    )
                    if ok:
                        self.installation_success = True
                        self.installation_message = msg
                        break
                    last_error = msg
                except Exception as e:
                    last_error = str(e)
            else:
                self.installation_success = False
                self.installation_message = last_error or "Failed to install ACES"
        except Exception as e:
            self.installation_success = False
            self.installation_message = f"Installation error: {str(e)}"
        finally:
            self.installation_complete = True

    def _progress_callback(self, message: str, current: int, total: int):
        """Update progress from background thread."""
        self.progress_message = message
        self.progress_percentage = current

    def modal(self, context, event):
        if event.type == 'ESC':
            # User cancelled
            self.is_installing = False
            return {'CANCELLED'}
        
        if self.installation_complete:
            if self.installation_success:
                self.report({'INFO'}, self.installation_message)
            else:
                self.report({'ERROR'}, self.installation_message)
            
            self.is_installing = False
            return {'FINISHED'}
        
        # Redraw to update progress
        context.area.tag_redraw()
        return {'PASS_THROUGH'}

    def draw(self, context):
        layout = self.layout
        
        if self.is_installing:
            # Show progress
            col = layout.column(align=True)
            col.label(text=self.progress_message)
            
            # Progress bar
            row = layout.row()
            row.prop(self, "progress_percentage", text="Progress")
            
            # Cancel button
            layout.operator("bam.cancel_install", text="Cancel Installation")
        else:
            # Show completion status
            if self.installation_complete:
                if self.installation_success:
                    layout.label(text="Installation completed successfully!", icon='CHECKMARK')
                else:
                    layout.label(text=f"Installation failed: {self.installation_message}", icon='ERROR')
            else:
                layout.label(text="Ready to install ACES")


class BAM_OT_switch_to_aces(Operator):
    bl_idname = "bam.switch_to_aces"
    bl_label = "Switch to ACES"
    bl_description = "Switch color management to ACES (may restart Blender)"

    auto_restart: BoolProperty(
        name="Auto-Restart",
        default=True,
    )

    def execute(self, context):
        prefs = utils.get_addon_prefs(context)
        ok, msg = utils.switch_to_aces(auto_restart=prefs.auto_restart and self.auto_restart)
        if ok:
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        self.report({'ERROR'}, msg)
        return {'CANCELLED'}


class BAM_OT_switch_to_default(Operator):
    bl_idname = "bam.switch_to_default"
    bl_label = "Switch to Default"
    bl_description = "Switch color management back to Blender default (may restart Blender)"

    auto_restart: BoolProperty(
        name="Auto-Restart",
        default=True,
    )

    def execute(self, context):
        prefs = utils.get_addon_prefs(context)
        ok, msg = utils.switch_to_default(auto_restart=prefs.auto_restart and self.auto_restart)
        if ok:
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        self.report({'ERROR'}, msg)
        return {'CANCELLED'}


class BAM_OT_validate_config(Operator):
    bl_idname = "bam.validate_config"
    bl_label = "Validate Current Config"
    bl_description = "Validate the current OCIO configuration"

    def execute(self, context):
        current_config = utils.get_ocio_config_override()
        if not current_config:
            self.report({'INFO'}, "No OCIO config override set (using Blender default)")
            return {'FINISHED'}

        # Lightweight validation to avoid heavy parsing/freezes
        is_valid, message = utils.validate_ocio_config(current_config)
        if not is_valid:
            self.report({'ERROR'}, f"Invalid OCIO config: {message}")
            return {'CANCELLED'}

        if utils.is_config_potentially_incompatible(current_config):
            self.report({'WARNING'}, "Config may be incompatible with OCIO v2 (XYZ role/name conflict)")
        else:
            self.report({'INFO'}, f"Looks OK: {current_config}")
        return {'FINISHED'}


class BAM_OT_cancel_install(Operator):
    bl_idname = "bam.cancel_install"
    bl_label = "Cancel Installation"
    bl_description = "Cancel the current ACES installation"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        # Find the install operator and cancel it
        for area in context.screen.areas:
            if area.type == 'PROPERTIES':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        # Try to find the install operator
                        for op in context.window_manager.operators:
                            if op.bl_idname == "bam.install_aces" and op.is_installing:
                                op.is_installing = False
                                op.installation_complete = True
                                op.installation_success = False
                                op.installation_message = "Installation cancelled by user"
                                break
        return {'FINISHED'}


class BAM_OT_check_update(Operator):
    bl_idname = "bam.check_update"
    bl_label = "Check for Updates"
    bl_description = "Check GitHub Releases for a new version of this add-on"

    def execute(self, context):
        try:
            prefs = utils.get_addon_prefs(context)
            repo = getattr(prefs, "update_repo", "lucas-tafuri/blender_aces_manager")
            include_pre = getattr(prefs, "include_prereleases", False)
            result = utils.check_addon_update(repo, include_pre)
            if result.get("update_available"):
                self.report({'INFO'}, f"Update available: {result.get('latest_version')}")
            else:
                self.report({'INFO'}, "You're up to date")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Update check failed: {e}")
            return {'CANCELLED'}


class BAM_OT_update_addon(Operator):
    bl_idname = "bam.update_addon"
    bl_label = "Update Add-on"
    bl_description = "Download and install the latest release of this add-on"

    def execute(self, context):
        try:
            # Ensure we actually need an update
            prefs = utils.get_addon_prefs(context)
            repo = getattr(prefs, "update_repo", "lucas-tafuri/blender_aces_manager")
            include_pre = getattr(prefs, "include_prereleases", False)
            state = utils.check_addon_update(repo, include_pre)
            if not state.get("update_available"):
                self.report({'INFO'}, "Already up to date")
                return {'CANCELLED'}

            asset_url = state.get("asset_url")
            if not asset_url:
                self.report({'ERROR'}, "No downloadable ZIP found in the latest release")
                return {'CANCELLED'}

            ok, msg = utils.install_addon_from_zip(asset_url)
            if ok:
                # Auto-restart and reopen current file
                try:
                    utils.restart_blender_with_same_file()
                except Exception:
                    pass
                self.report({'INFO'}, "Updated and restarting Blender...")
                return {'FINISHED'}
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Update failed: {e}")
            return {'CANCELLED'}


class BAM_OT_uninstall_aces(Operator):
    bl_idname = "bam.uninstall_aces"
    bl_label = "Uninstall ACES"
    bl_description = "Remove the installed ACES configuration"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        try:
            # Check if currently using ACES
            if utils.is_using_aces():
                self.report({'ERROR'}, "Cannot uninstall ACES while it's active. Switch to default first.")
                return {'CANCELLED'}

            # Confirm uninstallation
            ok = self.confirm_uninstall()
            if not ok:
                return {'CANCELLED'}

            # Perform uninstallation
            success, message = utils.uninstall_aces()
            if success:
                self.report({'INFO'}, message)
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, message)
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Uninstall failed: {e}")
            return {'CANCELLED'}

    def confirm_uninstall(self) -> bool:
        """Show confirmation dialog for uninstallation."""
        try:
            import bpy
            return bpy.ops.bam.confirm_uninstall_aces('INVOKE_DEFAULT')
        except Exception:
            # Fallback: assume yes for non-interactive environments
            return True


class BAM_OT_confirm_uninstall_aces(Operator):
    bl_idname = "bam.confirm_uninstall_aces"
    bl_label = "Confirm Uninstall ACES"
    bl_description = "Confirm removal of ACES configuration"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def draw(self, context):
        layout = self.layout
        layout.label(text="This will remove the ACES configuration from:")
        layout.label(text=f"{utils.get_aces_dir()}")
        layout.label(text="")
        layout.label(text="Are you sure you want to continue?")
        layout.label(text="This action cannot be undone.")


classes = (
    BAM_OT_install_aces,
    BAM_OT_switch_to_aces,
    BAM_OT_switch_to_default,
    BAM_OT_validate_config,
    BAM_OT_cancel_install,
    BAM_OT_check_update,
    BAM_OT_update_addon,
    BAM_OT_uninstall_aces,
    BAM_OT_confirm_uninstall_aces,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


