"""CloudDesk support API."""

from importlib.metadata import PackageNotFoundError, version

SERVICE_NAME = "clouddesk"
__version__ = "0.1.0"


def distribution_version() -> str:
    """Package version when installed, otherwise the in-repo fallback."""
    try:
        return version(SERVICE_NAME)
    except PackageNotFoundError:
        return __version__
