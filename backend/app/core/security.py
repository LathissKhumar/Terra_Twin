"""Security utilities and filesystem path restriction helpers."""

from pathlib import Path

from app.core.config import settings
from app.core.exceptions import TerraTwinError


class PathSecurityError(TerraTwinError):
    """Raised when a file path violates security boundary checks."""

    pass


ALLOWED_EXTENSIONS: set[str] = {
    ".tif",
    ".tiff",
    ".geotiff",
    ".img",
    ".pds",
    ".lbl",
    ".obj",
    ".glb",
    ".json",
    ".pdf",
}


def sanitize_and_resolve_data_path(relative_or_name: str, subfolder: str = "raw") -> Path:
    """
    Safely resolve a file within the designated data folder.
    Guarantees no directory traversal (e.g. '../' attacks) and ensures the path
    resides strictly within the allowed data directories.
    """
    base_target = (settings.DATA_DIR / subfolder).resolve()

    # Strip dangerous characters and resolve path
    candidate = (base_target / relative_or_name).resolve()

    # Verify containment within base_target
    if not str(candidate).startswith(str(base_target)):
        msg = f"Access denied: path '{relative_or_name}' attempts traversal outside data boundary."
        raise PathSecurityError(msg)

    # Validate file extension if file has a suffix
    if candidate.suffix and candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise PathSecurityError(
            f"File extension '{candidate.suffix}' is not permitted. Allowed: {ALLOWED_EXTENSIONS}"
        )

    return candidate