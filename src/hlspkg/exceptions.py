"""Exception hierarchy for the HLS packaging pipeline."""


class HlsPkgError(Exception):
    """Base exception for all hlspkg errors."""


class PreflightError(HlsPkgError):
    """Error during input probing or encoding plan generation."""


class TranscodeError(HlsPkgError):
    """Error during video/audio transcoding."""


class PackageError(HlsPkgError):
    """Error during CMAF HLS packaging."""


class PublishError(HlsPkgError):
    """Error during output publishing."""


class StorageError(HlsPkgError):
    """Error during storage operations (download/upload)."""
