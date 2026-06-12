import os
import shutil
from pathlib import Path


def detect_gpu() -> str:
    """
    Detects the system's primary GPU manufacturer (AMD, Nvidia, Intel, or unknown)
    by scanning the Linux sysfs PCI hardware class devices.
    """
    sys_drm = Path("/sys/class/drm")
    if not sys_drm.exists():
        return "unknown"

    # Hexadecimal PCI Vendor IDs:
    # AMD: 0x1002, Nvidia: 0x10de, Intel: 0x8086
    vendors = {"0x1002": "amd", "0x10de": "nvidia", "0x8086": "intel"}

    try:
        # Check all DRM cards
        for card_path in sys_drm.glob("card*"):
            vendor_file = card_path / "device" / "vendor"
            if vendor_file.exists():
                vendor_id = vendor_file.read_text().strip().lower()
                # Check for standard vendor hex maps
                for vid, name in vendors.items():
                    if vid in vendor_id:
                        return name
    except Exception:
        pass

    # Fallback: check standard lspci if sysfs parsing failed
    try:
        import subprocess

        lspci_out = (
            subprocess.check_output("lspci", shell=True, stderr=subprocess.DEVNULL)
            .decode("utf-8")
            .lower()
        )
        if "nvidia" in lspci_out:
            return "nvidia"
        elif "amd" in lspci_out or "ati" in lspci_out:
            return "amd"
        elif "intel" in lspci_out:
            return "intel"
    except Exception:
        pass

    return "unknown"


def compile_performance_env(
    gpu_type: str, recipe_env: dict[str, str]
) -> dict[str, str]:
    """
    Compiles the final, optimal environment variables dictionary for launching the game.
    Tailors graphics overrides based on the detected GPU and merges them with recipe overrides.
    """
    compiled_env = os.environ.copy()

    # 1. Base CachyOS / Zen Kernel synchronization optimizations
    base_optimizations = {
        "WINEESYNC": "1",
        "WINEMFSYNC": "1",
        "WINE_FULLSCREEN_FSR": "1",
        "WINE_FS_FSR_STRENGTH": "5",
    }

    for k, v in base_optimizations.items():
        compiled_env[k] = v

    # 2. GPU-Specific overrides (Idea 2)
    match gpu_type:
        case "amd":
            # Enable high-speed Vulkan GPL shader pre-compilation (avoids stutters)
            compiled_env["RADV_PERFTEST"] = "gpl"
        case "nvidia":
            # Enable Nvidia shader disk caching and NVAPI (DLSS & RayTracing support)
            compiled_env["__GL_SHADER_DISK_CACHE"] = "1"
            compiled_env["PROTON_ENABLE_NVAPI"] = "1"
            # NVIDIA Hybrid GPU Prime Offload variables
            compiled_env["__NV_PRIME_RENDER_OFFLOAD"] = "1"
            compiled_env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
            compiled_env["__VK_LAYER_NV_optimus"] = "NVIDIA_only"
        case "intel":
            # Intel Vulkan optimizations if applicable
            compiled_env["INTEL_DEBUG"] = "noccs"

    # 3. Merge Recipe-Specific overrides (they override standard defaults)
    for k, v in recipe_env.items():
        compiled_env[k] = str(v)

    return compiled_env


def detect_performance_wrapper() -> list[str]:
    """
    Detects if high-priority game boosters are available in the system PATH
    (gamemoderun or game-performance).
    """
    # Prioritize standard Feral GameMode to avoid hidden sudo/PolicyKit password prompts from hanging launches!
    if shutil.which("gamemoderun"):
        return ["gamemoderun"]
    # Fallback to CachyOS native game-performance governor tool
    elif shutil.which("game-performance"):
        return ["game-performance"]
    return []
