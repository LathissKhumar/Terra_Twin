"""Unit tests for path traversal security checks."""

import pytest

from app.core.security import PathSecurityError, sanitize_and_resolve_data_path


def test_valid_data_path_resolution():
    """Verify safe paths within data directories resolve correctly."""
    resolved = sanitize_and_resolve_data_path("test_dem.tif", subfolder="raw")
    assert resolved.name == "test_dem.tif"
    assert "raw" in str(resolved)


def test_directory_traversal_blocked():
    """Verify directory traversal attempts raise PathSecurityError."""
    with pytest.raises(PathSecurityError, match="attempts traversal"):
        sanitize_and_resolve_data_path("../../../etc/passwd", subfolder="raw")


def test_sibling_path_with_shared_prefix_is_blocked():
    """A sibling directory name must not pass a string-prefix containment check."""
    with pytest.raises(PathSecurityError, match="attempts traversal"):
        sanitize_and_resolve_data_path("../raw_backup/secret.tif", subfolder="raw")


def test_disallowed_extension_blocked():
    """Verify forbidden file types raise PathSecurityError."""
    with pytest.raises(PathSecurityError, match="is not permitted"):
        sanitize_and_resolve_data_path("malicious.sh", subfolder="raw")
