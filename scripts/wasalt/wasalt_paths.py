"""Current repository paths and the historical paths present in Wasalt evidence."""

from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data" / "wasalt"
MANUAL_EXPORTS = REPO_ROOT / "archive" / "2026-11-18" / "manual-wasalt"


def resolve_data_path(value, data_root=None):
    """Resolve recorded dataset paths without changing the historical record."""
    root = Path(data_root) if data_root is not None else DATA_ROOT
    text = str(value)
    if not text or "://" in text or "\\" in text:
        raise ValueError(f"Unsupported dataset path: {text!r}")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or (path.parts and ":" in path.parts[0]):
        raise ValueError(f"Absolute or escaping dataset path: {text!r}")
    parts = path.parts
    if parts[:1] == ("wasalt_data",):
        parts = parts[1:]
    elif parts[:2] == ("data", "wasalt"):
        parts = parts[2:]
    candidate = root.joinpath(*parts)
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Dataset path escapes through a symlink: {text!r}")
    return candidate
