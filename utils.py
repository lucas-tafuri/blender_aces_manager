import bpy
import os
import sys
import tempfile
import json
import shutil
import zipfile
import urllib.request
import urllib.error
import time
import subprocess
import threading
from typing import Optional, Tuple, Callable


# Default sources for ACES OCIO configurations suitable for Blender (OCIO v2 preferred first)
DEFAULT_ZIP_URLS = [
    # Official ACES OCIO v2 config (CG-config) maintained by ASWF
    "https://github.com/AcademySoftwareFoundation/OpenColorIO-Config-ACES/archive/refs/heads/main.zip",
    # Community configs as fallbacks
    "https://github.com/thezakman/ACES-blender-colour-management/archive/refs/heads/main.zip",
    "https://github.com/thezakman/ACES-blender-colour-management/archive/refs/heads/master.zip",
    "https://github.com/qweryty/Blender-Optimized-ACES/archive/refs/heads/main.zip",
    "https://github.com/qweryty/Blender-Optimized-ACES/archive/refs/heads/master.zip",
]


def get_addon_prefs(context=None):
    if context is None:
        context = bpy.context
    addon_name = __package__ or "blender_aces_manager"
    return context.preferences.addons[addon_name].preferences


def get_data_dir() -> str:
    # Use Blender user config directory for storing our data
    user_config_dir = bpy.utils.user_resource("CONFIG")
    data_dir = os.path.join(user_config_dir, "blender_aces_manager")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_aces_dir() -> str:
    aces_dir = os.path.join(get_data_dir(), "aces")
    os.makedirs(aces_dir, exist_ok=True)
    return aces_dir


def get_backups_dir() -> str:
    backups_dir = os.path.join(get_data_dir(), "backups")
    os.makedirs(backups_dir, exist_ok=True)
    return backups_dir


def get_state_file() -> str:
    return os.path.join(get_data_dir(), "state.json")


def load_state() -> dict:
    path = get_state_file()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    path = get_state_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


class DownloadProgress:
    def __init__(self):
        self.bytes_downloaded = 0
        self.total_size = 0
        self.is_complete = False
        self.error = None
        self.progress_callback = None
        self.last_update_time = 0
    
    def set_progress_callback(self, callback: Callable[[int, int], None]):
        self.progress_callback = callback
    
    def update_progress(self, block_num, block_size, total_size):
        if total_size > 0:
            self.total_size = total_size
            self.bytes_downloaded = block_num * block_size
            
            # Throttle updates to prevent UI spam (update max every 100ms)
            current_time = time.time()
            if self.progress_callback and (current_time - self.last_update_time) > 0.1:
                self.progress_callback(self.bytes_downloaded, total_size)
                self.last_update_time = current_time

def download_zip(url: str, dest_zip_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
    """Download a zip file with progress indication."""
    # Download to a temporary file then move into place
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(tmp_fd)
    
    try:
        progress = DownloadProgress()
        if progress_callback:
            progress.set_progress_callback(progress_callback)
        
        urllib.request.urlretrieve(url, tmp_path, progress.update_progress)
        shutil.move(tmp_path, dest_zip_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

def download_zip_async(url: str, dest_zip_path: str, progress_callback: Optional[Callable[[int, int], None]] = None, 
                       completion_callback: Optional[Callable[[bool, str], None]] = None) -> None:
    """Download a zip file asynchronously in a background thread."""
    def download_thread():
        try:
            download_zip(url, dest_zip_path, progress_callback)
            if completion_callback:
                completion_callback(True, "Download completed successfully")
        except Exception as e:
            if completion_callback:
                completion_callback(False, str(e))
    
    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()


def _get_addon_module_and_version() -> Tuple[str, Tuple[int, int, int]]:
    """Return (module_name, version_tuple) for this add-on.
    Safely imports the package root to read bl_info.
    """
    try:
        # Local import to avoid circulars at module import time
        from . import __init__ as _addon_root
        module_name = __package__ or "blender_aces_manager"
        version = _addon_root.bl_info.get("version", (0, 0, 0))
        # Normalize to 3-tuple
        if isinstance(version, (list, tuple)):
            version_tuple = tuple(int(v) for v in version)[:3]
            while len(version_tuple) < 3:
                version_tuple = (*version_tuple, 0)
        else:
            version_tuple = (0, 0, 0)
        return module_name, version_tuple
    except Exception:
        return ("blender_aces_manager", (0, 0, 0))


def _parse_version_string(version_str: str) -> Tuple[int, int, int]:
    """Parse versions like '1.2.3' or 'v1.2.3' to a tuple."""
    try:
        v = version_str.strip()
        if v.startswith('v') or v.startswith('V'):
            v = v[1:]
        parts = [int(p) for p in v.split('.') if p.isdigit() or (p and p[0].isdigit())]
        parts = parts[:3]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)  # type: ignore[return-value]
    except Exception:
        return (0, 0, 0)


def _http_get_json(url: str, timeout: float = 10.0) -> Optional[dict]:
    """GET JSON helper with GitHub-friendly headers."""
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "blender-aces-manager-updater"
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode('utf-8', errors='ignore')
            return json.loads(data)
    except Exception:
        return None


def get_latest_release_info(repo: str = "lucas-tafuri/blender_aces_manager", include_prereleases: bool = False) -> Optional[dict]:
    """Query GitHub Releases for the latest release.

    Returns a dict with keys: tag, version, name, is_prerelease, asset_url, html_url
    or None on failure.
    """
    # Try the standard latest endpoint first (skips prereleases)
    if not include_prereleases:
        data = _http_get_json(f"https://api.github.com/repos/{repo}/releases/latest")
        if data and isinstance(data, dict) and not data.get("draft", False):
            assets = data.get("assets") or []
            asset_url = None
            for a in assets:
                name = a.get("name", "") or ""
                # Prefer a zip asset that looks like an add-on package
                if name.lower().endswith('.zip'):
                    asset_url = a.get("browser_download_url")
                    break
            # If no explicit asset, fallback to tag source zip
            if not asset_url and data.get("tag_name"):
                tag = data["tag_name"]
                asset_url = f"https://github.com/{repo}/archive/refs/tags/{tag}.zip"
            return {
                "tag": data.get("tag_name") or "",
                "version": data.get("tag_name") or "",
                "name": data.get("name") or "",
                "is_prerelease": bool(data.get("prerelease", False)),
                "asset_url": asset_url,
                "html_url": data.get("html_url") or ""
            }

    # Otherwise fetch the release list and pick newest by created_at
    releases = _http_get_json(f"https://api.github.com/repos/{repo}/releases") or []
    if not isinstance(releases, list):
        return None
    filtered = [r for r in releases if not r.get("draft", False) and (include_prereleases or not r.get("prerelease", False))]
    if not filtered:
        return None
    # Sort by created_at descending
    filtered.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    data = filtered[0]
    assets = data.get("assets") or []
    asset_url = None
    for a in assets:
        name = a.get("name", "") or ""
        if name.lower().endswith('.zip'):
            asset_url = a.get("browser_download_url")
            break
    # Fallback to tag source ZIP if no explicit assets; repack will fix top-level folder name
    if not asset_url and data.get("tag_name"):
        tag = data["tag_name"]
        asset_url = f"https://github.com/{repo}/archive/refs/tags/{tag}.zip"
    return {
        "tag": data.get("tag_name") or "",
        "version": data.get("tag_name") or "",
        "name": data.get("name") or "",
        "is_prerelease": bool(data.get("prerelease", False)),
        "asset_url": asset_url,
        "html_url": data.get("html_url") or ""
    }


def check_addon_update(repo: str, include_prereleases: bool = False) -> dict:
    """Check whether an update is available. Stores result in state and returns it.

    Returns dict with: current_version, latest_version, update_available, asset_url, html_url, checked_at
    """
    _module, current_version = _get_addon_module_and_version()
    info = get_latest_release_info(repo, include_prereleases)
    result = {
        "current_version": f"{current_version[0]}.{current_version[1]}.{current_version[2]}",
        "latest_version": "",
        "update_available": False,
        "asset_url": None,
        "html_url": None,
        "checked_at": int(time.time()),
    }
    if not info:
        # Persist failure time only
        state = load_state()
        state["update"] = result
        save_state(state)
        return result

    latest_tuple = _parse_version_string(info.get("version") or "0.0.0")
    result["latest_version"] = f"{latest_tuple[0]}.{latest_tuple[1]}.{latest_tuple[2]}"
    result["update_available"] = latest_tuple > current_version
    result["asset_url"] = info.get("asset_url")
    result["html_url"] = info.get("html_url")

    state = load_state()
    state["update"] = result
    save_state(state)
    return result


def get_cached_update_state() -> dict:
    state = load_state()
    return state.get("update", {})


def schedule_update_check_once(delay_seconds: float = 3.0) -> None:
    """Schedule a one-time update check a few seconds after register."""
    try:
        def _do_check():
            try:
                prefs = get_addon_prefs()
                repo = getattr(prefs, "update_repo", "lucas-tafuri/blender_aces_manager")
                include_pre = getattr(prefs, "include_prereleases", False)
                # Run in background thread to avoid blocking UI
                def _bg():
                    try:
                        check_addon_update(repo, include_pre)
                    except Exception:
                        pass
                t = threading.Thread(target=_bg, daemon=True)
                t.start()
            except Exception:
                pass
            # Do not repeat
            return None

        # Defer import to runtime to avoid issues when running outside Blender
        import bpy as _bpy  # noqa: F401
        _bpy.app.timers.register(_do_check, first_interval=delay_seconds)
    except Exception:
        pass


def install_addon_from_zip(zip_url: str, module_name: Optional[str] = None) -> Tuple[bool, str]:
    """Download a ZIP and install/enable this add-on from it.
    Returns (ok, message).
    """
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip")
        os.close(tmp_fd)
        try:
            # Stream download
            req = urllib.request.Request(zip_url, headers={"User-Agent": "blender-aces-manager-updater"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_path, "wb") as out:
                shutil.copyfileobj(resp, out)
        except Exception as e:
            return False, f"Download failed: {e}"

        # Ensure the zip has a valid top-level folder named blender_aces_manager,
        # and detect if this is a Blender Extension (blender_manifest.toml).
        zip_for_install = tmp_path
        is_extension_package = False
        try:
            with zipfile.ZipFile(tmp_path, 'r') as zf:
                names = zf.namelist()
                # Detect extension manifest
                for n in names:
                    base = n.rsplit('/', 1)[-1]
                    if base == 'blender_manifest.toml':
                        is_extension_package = True
                        break
                # Determine top-level entries
                top_levels = set()
                for n in names:
                    if not n or n.startswith("__MACOSX/"):
                        continue
                    parts = n.split('/')
                    if parts:
                        top_levels.add(parts[0])
                # If there is exactly one top-level and it's not the desired folder, repack
                if len(top_levels) == 1:
                    top = next(iter(top_levels))
                    desired = 'blender_aces_manager'
                    if top != desired:
                        # Extract then re-zip under the desired folder name
                        work_dir = tempfile.mkdtemp(prefix="bam_repack_")
                        extract_dir = os.path.join(work_dir, "extract")
                        out_dir = os.path.join(work_dir, desired)
                        os.makedirs(extract_dir, exist_ok=True)
                        zf.extractall(extract_dir)
                        # Move contents from the single top folder into out_dir
                        src_root = os.path.join(extract_dir, top)
                        shutil.copytree(src_root, out_dir)
                        repacked = os.path.join(work_dir, "repacked.zip")
                        with zipfile.ZipFile(repacked, 'w', zipfile.ZIP_DEFLATED) as zout:
                            for root, _dirs, files in os.walk(out_dir):
                                for f in files:
                                    full = os.path.join(root, f)
                                    arc = os.path.relpath(full, work_dir)
                                    zout.write(full, arcname=arc)
                        zip_for_install = repacked
        except Exception:
            # If inspection/repack fails, proceed with original zip and hope it's valid
            pass

        try:
            # Install and enable
            import bpy as _bpy
            enable_ok = False
            # Choose installer based on presence of extension manifest and operator availability
            used_extension_ops = False
            try:
                if is_extension_package and hasattr(_bpy.ops.preferences, 'extension_install'):
                    _bpy.ops.preferences.extension_install(filepath=zip_for_install, overwrite=True)
                    used_extension_ops = True
                else:
                    _bpy.ops.preferences.addon_install(filepath=zip_for_install, overwrite=True, target='DEFAULT')
            except Exception:
                # Fallback to addon_install if extension_install failed or is unavailable
                try:
                    _bpy.ops.preferences.addon_install(filepath=zip_for_install, overwrite=True, target='DEFAULT')
                except Exception as e:
                    return False, f"Install failed: {e}"

            # Try enabling using the appropriate operator(s)
            if module_name is None:
                module_name, _v = _get_addon_module_and_version()
            # 1) Try as legacy add-on module
            try:
                _bpy.ops.preferences.addon_enable(module=module_name)
                enable_ok = True
            except Exception:
                pass
            # 2) Try extension enable if available
            if not enable_ok and hasattr(_bpy.ops.preferences, 'extension_enable'):
                try:
                    # Try both plain name and the qualified bl_ext path
                    _bpy.ops.preferences.extension_enable(module=module_name)
                    enable_ok = True
                except Exception:
                    try:
                        qualified = f"bl_ext.user_default.{module_name}"
                        _bpy.ops.preferences.extension_enable(module=qualified)
                        enable_ok = True
                    except Exception:
                        pass
            # 3) Last resort: scan known addons and extensions keys
            if not enable_ok:
                base = module_name.split('.')[0]
                # Legacy add-ons
                try:
                    for mod_name in list(_bpy.context.preferences.addons.keys()):
                        if mod_name == base or mod_name.startswith(base):
                            try:
                                _bpy.ops.preferences.addon_enable(module=mod_name)
                                enable_ok = True
                                break
                            except Exception:
                                pass
                except Exception:
                    pass
                # Extensions also show as modules under bl_ext.*; try enabling by qualified name
                if not enable_ok and hasattr(_bpy.ops.preferences, 'extension_enable'):
                    try:
                        _bpy.ops.preferences.extension_enable(module=f"bl_ext.user_default.{base}")
                        enable_ok = True
                    except Exception:
                        pass

            try:
                _bpy.ops.wm.save_userpref()
            except Exception:
                pass
            if not enable_ok:
                return False, "Installed, but could not enable the add-on automatically. Please enable it in Preferences/Extensions."
        except Exception as e:
            return False, f"Enable failed: {e}"
        finally:
            try:
                if zip_for_install != tmp_path and os.path.exists(zip_for_install):
                    os.remove(zip_for_install)
            except Exception:
                pass
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return True, "Add-on updated"
    except Exception as e:
        return False, f"Unexpected error: {e}"

def find_config_ocio(root_dir: str) -> Optional[str]:
    # Return directory path that contains a config.ocio
    for current_root, _dirs, files in os.walk(root_dir):
        if "config.ocio" in files:
            return current_root
    return None


def is_config_potentially_incompatible(config_path: str) -> bool:
    """Heuristic to detect configs that may conflict with OCIO v2/Blender 4.x.
    Example: a colorspace named 'XYZ' alongside a role 'XYZ' triggers errors.
    """
    try:
        with open(config_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        has_role_xyz = False
        has_colorspace_named_xyz = False
        # Very rough checks to avoid heavy parsing
        if "roles:" in content and "XYZ:" in content:
            has_role_xyz = True
        # Look for a colorspace definition with name: XYZ
        if "name:" in content and "name: XYZ" in content:
            has_colorspace_named_xyz = True
        return has_role_xyz and has_colorspace_named_xyz
    except Exception:
        return False


def install_aces_from_zip_url(zip_url: str, progress_callback: Optional[Callable[[str, int, int], None]] = None) -> Tuple[bool, Optional[str], str]:
    """
    Download and extract an ACES OCIO configuration zip, normalize so that
    get_aces_config_path() points to aces/config.ocio.

    Returns (success, config_dir, message)
    """
    aces_dir = get_aces_dir()
    os.makedirs(aces_dir, exist_ok=True)

    if progress_callback:
        try:
            progress_callback("Cleaning previous installation...", 0, 100)
        except:
            pass

    # Clean aces dir first to avoid stale data
    for item in os.listdir(aces_dir):
        item_path = os.path.join(aces_dir, item)
        try:
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)
        except Exception:
            pass

    if progress_callback:
        try:
            progress_callback("Downloading ACES configuration...", 10, 100)
        except:
            pass

    # Download
    zip_dest = os.path.join(aces_dir, "aces_config.zip")
    try:
        def download_progress(downloaded, total):
            if progress_callback and total > 0:
                try:
                    message = f"Downloading... {downloaded//1024//1024}MB / {total//1024//1024}MB"
                    percentage = 10 + int(70 * downloaded / total)
                    progress_callback(message, percentage, 100)
                except:
                    pass
        
        download_zip(zip_url, zip_dest, download_progress)
    except Exception as exc:
        return False, None, f"Download failed: {exc}"

    if progress_callback:
        try:
            progress_callback("Extracting files...", 80, 100)
        except:
            pass

    # Extract
    extract_root = os.path.join(aces_dir, "_extract")
    os.makedirs(extract_root, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_dest, "r") as zf:
            zf.extractall(extract_root)
    except Exception as exc:
        return False, None, f"Extraction failed: {exc}"

    if progress_callback:
        try:
            progress_callback("Locating configuration...", 85, 100)
        except:
            pass

    # Locate config.ocio
    config_dir = find_config_ocio(extract_root)
    if not config_dir:
        return False, None, "Could not find config.ocio in the downloaded archive"

    # Quick compatibility check
    config_file = os.path.join(config_dir, "config.ocio")
    if is_config_potentially_incompatible(config_file):
        return False, None, "Downloaded config appears incompatible with OCIO v2 (XYZ role/name conflict)"

    if progress_callback:
        try:
            progress_callback("Installing configuration...", 90, 100)
        except:
            pass

    # Normalize: copy the entire directory containing config.ocio into aces_dir as 'config'
    final_config_dir = os.path.join(aces_dir, "config")
    try:
        if os.path.exists(final_config_dir):
            shutil.rmtree(final_config_dir)
        shutil.copytree(config_dir, final_config_dir)
    except Exception as exc:
        return False, None, f"Failed to stage ACES config: {exc}"
    finally:
        # Cleanup extraction and zip
        try:
            os.remove(zip_dest)
        except Exception:
            pass
        try:
            shutil.rmtree(extract_root)
        except Exception:
            pass

    if progress_callback:
        try:
            progress_callback("Installation complete!", 100, 100)
        except:
            pass

    return True, final_config_dir, "ACES configuration installed"


def get_aces_config_path() -> str:
    return os.path.join(get_aces_dir(), "config", "config.ocio")


def is_aces_installed() -> bool:
    return os.path.isfile(get_aces_config_path())


def get_blender_version_info() -> str:
    """Get Blender version as a string for display purposes."""
    version = bpy.app.version
    return f"{version[0]}.{version[1]}.{version[2]}"

def get_ocio_config_override() -> str:
    """Get the current OCIO config override path, compatible with different Blender versions.
    
    Blender version changes:
    - 2.93 and earlier: bpy.context.preferences.system.ocio_config
    - 3.0 to 3.5: bpy.context.preferences.system.ocio_config  
    - 3.6 to 3.6.5: bpy.context.preferences.system.color_management.ocio_config_override
    - 4.0+: bpy.context.preferences.system.ocio_config_override
    """
    try:
        # Blender 4.0+ (4.0, 4.1, 4.2, etc.)
        if bpy.app.version >= (4, 0, 0):
            if hasattr(bpy.context.preferences.system, 'ocio_config_override'):
                return bpy.context.preferences.system.ocio_config_override
            # Fallback: use environment variable
            return os.environ.get('OCIO', "")
        # Blender 3.6 to 3.6.5
        elif (3, 6, 0) <= bpy.app.version < (4, 0, 0):
            if hasattr(bpy.context.preferences.system, 'color_management'):
                return bpy.context.preferences.system.color_management.ocio_config_override
        # Blender 3.0 to 3.5
        elif (3, 0, 0) <= bpy.app.version < (3, 6, 0):
            if hasattr(bpy.context.preferences.system, 'ocio_config'):
                return bpy.context.preferences.system.ocio_config
        # Blender 2.93 and earlier
        else:
            if hasattr(bpy.context.preferences.system, 'ocio_config'):
                return bpy.context.preferences.system.ocio_config

        # Last resort: env var if set
        return os.environ.get('OCIO', "")
    except Exception as e:
        print(f"Error getting OCIO config override: {e}")
        return ""

def set_ocio_config_override(path: str) -> None:
    """Set the OCIO config override path, compatible with different Blender versions.
    
    Blender version changes:
    - 2.93 and earlier: bpy.context.preferences.system.ocio_config
    - 3.0 to 3.5: bpy.context.preferences.system.ocio_config  
    - 3.6 to 3.6.5: bpy.context.preferences.system.color_management.ocio_config_override
    - 4.0+: bpy.context.preferences.system.ocio_config_override
    """
    try:
        # Blender 4.0+ (4.0, 4.1, 4.2, etc.)
        if bpy.app.version >= (4, 0, 0):
            if hasattr(bpy.context.preferences.system, 'ocio_config_override'):
                bpy.context.preferences.system.ocio_config_override = path
                print(f"Set OCIO config override to: {path} (Blender 4.0+ path)")
                return
            # Fallback to environment variable
            os.environ['OCIO'] = path
            print(f"Set OCIO via environment variable for this session: {path}")
            # Persist on Windows so restarts launched outside the add-on still inherit
            try:
                if os.name == 'nt':
                    set_user_env_var_windows('OCIO', path)
            except Exception as persist_exc:
                print(f"Warning: could not persist OCIO user env var: {persist_exc}")
            return
        # Blender 3.6 to 3.6.5
        elif (3, 6, 0) <= bpy.app.version < (4, 0, 0):
            if hasattr(bpy.context.preferences.system, 'color_management'):
                bpy.context.preferences.system.color_management.ocio_config_override = path
                print(f"Set OCIO config override to: {path} (Blender 3.6+ path)")
                return
        # Blender 3.0 to 3.5
        elif (3, 0, 0) <= bpy.app.version < (3, 6, 0):
            if hasattr(bpy.context.preferences.system, 'ocio_config'):
                bpy.context.preferences.system.ocio_config = path
                print(f"Set OCIO config override to: {path} (Blender 3.0-3.5 path)")
                return
        # Blender 2.93 and earlier
        else:
            if hasattr(bpy.context.preferences.system, 'ocio_config'):
                bpy.context.preferences.system.ocio_config = path
                print(f"Set OCIO config override to: {path} (Blender 2.93- path)")
                return

        # As generic fallback use environment variable
        os.environ['OCIO'] = path
        print(f"Fallback: Set OCIO via environment variable for this session: {path}")
        try:
            if os.name == 'nt':
                set_user_env_var_windows('OCIO', path)
        except Exception as persist_exc:
            print(f"Warning: could not persist OCIO user env var: {persist_exc}")
    except Exception as e:
        print(f"Error setting OCIO config override: {e}")

def is_using_aces() -> bool:
    override = get_ocio_config_override()
    aces_config = get_aces_config_path()
    try:
        return os.path.normcase(os.path.abspath(override)) == os.path.normcase(os.path.abspath(aces_config))
    except Exception as e:
        print(f"Error checking if using ACES: {e}")
        return False

def validate_ocio_config(config_path: str) -> Tuple[bool, str]:
    """Validate that an OCIO config path is valid and contains required files."""
    if not config_path:
        return False, "No config path provided"
    
    if not os.path.exists(config_path):
        return False, f"Config path does not exist: {config_path}"
    
    if not os.path.isfile(config_path):
        return False, f"Config path is not a file: {config_path}"
    
    if not config_path.endswith('.ocio'):
        return False, f"Config path does not end with .ocio: {config_path}"
    
    # Check if the config file can be read
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            if not first_line.startswith('ocio_profile_version'):
                return False, f"Config file does not appear to be a valid OCIO config: {config_path}"
    except Exception as e:
        return False, f"Error reading config file: {e}"
    
    return True, "Valid OCIO config"


def backup_current_override_if_any() -> Optional[str]:
    override_path = get_ocio_config_override()
    if not override_path:
        return None

    if not os.path.isfile(override_path):
        return None

    # Copy parent directory to backups
    src_dir = os.path.dirname(os.path.abspath(override_path))
    if not os.path.isdir(src_dir):
        return None

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = os.path.join(get_backups_dir(), f"backup_{timestamp}")
    try:
        shutil.copytree(src_dir, backup_dir)
    except Exception:
        return None

    # Log backup in state
    state = load_state()
    state.setdefault("backups", []).append({
        "time": timestamp,
        "src_dir": src_dir,
        "backup_dir": backup_dir,
    })
    save_state(state)

    return backup_dir


def save_user_prefs() -> None:
    try:
        bpy.ops.wm.save_userpref()
    except Exception:
        pass


def backup_default_config_if_possible() -> Optional[str]:
    """Attempt to locate Blender's bundled default OCIO config and back it up.
    Returns backup directory path if succeeded, else None.
    """
    # Search near Blender binary for a directory containing 'datafiles/colormanagement/config.ocio'
    blender_exe = bpy.app.binary_path
    if not blender_exe:
        return None

    search_roots = [
        os.path.dirname(blender_exe),  # Blender install root
        os.path.abspath(os.path.join(os.path.dirname(blender_exe), os.pardir)),  # One level up
    ]

    found_config_dir = None
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for current_root, dirs, files in os.walk(root):
            # Speed up: prune hidden or very large dirs
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            if "config.ocio" in files and os.path.basename(current_root).lower() == "colormanagement":
                found_config_dir = current_root
                break
        if found_config_dir:
            break

    if not found_config_dir:
        return None

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = os.path.join(get_backups_dir(), f"default_backup_{timestamp}")
    try:
        shutil.copytree(found_config_dir, backup_dir)
    except Exception:
        return None

    state = load_state()
    state.setdefault("backups", []).append({
        "time": timestamp,
        "src_dir": found_config_dir,
        "backup_dir": backup_dir,
        "type": "default",
    })
    save_state(state)

    return backup_dir


def switch_to_aces(auto_restart: bool = True) -> Tuple[bool, str]:
    # Ensure ACES is installed
    if not is_aces_installed():
        prefs = get_addon_prefs()
        urls = []
        if prefs.aces_repo_preference.strip():
            urls.append(prefs.aces_repo_preference.strip())
        urls.extend(DEFAULT_ZIP_URLS)

        last_error = None
        for url in urls:
            ok, _config_dir, msg = install_aces_from_zip_url(url)
            if ok:
                break
            last_error = msg
        else:
            return False, last_error or "Failed to install ACES configuration"

    # Backup if switching from a different override
    current_override = get_ocio_config_override()
    aces_config_path = get_aces_config_path()
    if current_override:
        if os.path.normcase(os.path.abspath(current_override)) != os.path.normcase(os.path.abspath(aces_config_path)):
            backup_current_override_if_any()
    else:
        # We are switching from default, attempt to back up default config
        backup_default_config_if_possible()

    # Apply override and prepare environment
    set_ocio_config_override(aces_config_path)
    save_user_prefs()

    # Restart if desired
    if auto_restart:
        # Ensure child Blender sees OCIO even if preference API is unavailable
        restart_blender_with_same_file(extra_env={"OCIO": aces_config_path})
        return True, "Switched to ACES and restarting Blender"

    return True, "Switched to ACES; restart Blender to apply fully"


def switch_to_default(auto_restart: bool = True) -> Tuple[bool, str]:
    current_override = get_ocio_config_override()
    if current_override:
        # Backup the current override before removing
        backup_current_override_if_any()

    # Clear preference if available, otherwise clear env var
    cleared = False
    try:
        if bpy.app.version >= (4, 0, 0):
            if hasattr(bpy.context.preferences.system, 'ocio_config_override'):
                bpy.context.preferences.system.ocio_config_override = ""
                cleared = True
        elif (3, 6, 0) <= bpy.app.version < (4, 0, 0):
            if hasattr(bpy.context.preferences.system, 'color_management'):
                bpy.context.preferences.system.color_management.ocio_config_override = ""
                cleared = True
        elif (3, 0, 0) <= bpy.app.version < (3, 6, 0):
            if hasattr(bpy.context.preferences.system, 'ocio_config'):
                bpy.context.preferences.system.ocio_config = ""
                cleared = True
        else:
            if hasattr(bpy.context.preferences.system, 'ocio_config'):
                bpy.context.preferences.system.ocio_config = ""
                cleared = True
    except Exception:
        pass

    # Also clear environment variable for current and child processes
    if 'OCIO' in os.environ:
        try:
            del os.environ['OCIO']
        except Exception:
            pass
    # Also remove persisted user env on Windows
    try:
        if os.name == 'nt':
            delete_user_env_var_windows('OCIO')
    except Exception as persist_exc:
        print(f"Warning: could not remove persisted OCIO env var: {persist_exc}")
    save_user_prefs()

    if auto_restart:
        restart_blender_with_same_file(clear_ocio=True)
        return True, "Switched to Blender default and restarting Blender"

    return True, "Switched to Blender default; restart Blender to apply"


def restart_blender_with_same_file(extra_env: Optional[dict] = None, clear_ocio: bool = False) -> None:
    # Determine binary and current file path
    blender_exe = bpy.app.binary_path
    current_filepath = bpy.data.filepath

    # Ensure file is saved; if not saved, write to a temporary location
    if not current_filepath:
        tmp_dir = tempfile.gettempdir()
        current_filepath = os.path.join(tmp_dir, "autosave_blender_aces_manager.blend")
        try:
            bpy.ops.wm.save_as_mainfile(filepath=current_filepath, copy=False)
        except Exception:
            # If saving fails, restart without opening a file
            current_filepath = None
    else:
        # Save current file to not lose progress
        try:
            bpy.ops.wm.save_mainfile()
        except Exception:
            pass

    # Launch new Blender process with explicit environment
    args = [blender_exe]
    if current_filepath:
        args.append(current_filepath)

    # Build environment
    env = os.environ.copy()
    if clear_ocio and 'OCIO' in env:
        env.pop('OCIO', None)
    if extra_env:
        env.update(extra_env)

    try:
        subprocess.Popen(args, env=env)
    except Exception:
        pass

    # Quit current Blender instance
    try:
        bpy.ops.wm.quit_blender()
    except Exception:
        # As a fallback, force exit
        try:
            sys.exit(0)
        except SystemExit:
            pass


def set_user_env_var_windows(name: str, value: str) -> None:
    """Persist a per-user environment variable on Windows.
    Requires no elevation. New processes will inherit updated env.
    """
    # Use setx which writes to HKCU\Environment
    subprocess.run(["setx", name, value], shell=True, check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def delete_user_env_var_windows(name: str) -> None:
    """Delete a per-user environment variable on Windows (HKCU\\Environment)."""
    # Use reg delete with /F to avoid prompt
    subprocess.run(["reg", "delete", "HKCU\\Environment", "/V", name, "/F"],
                   shell=True, check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


