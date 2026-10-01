"""Storage telemetry used by the staff dashboard.

The tracker stores ticket image bytes on Django's MEDIA_ROOT (a Railway Volume in
production) and keeps only image metadata/path references in PostgreSQL.  These
helpers inspect the actual files so the dashboard reflects real disk usage.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from django.conf import settings

from .image_processing import TARGET_STORED_IMAGE_BYTES
from .models import ProblemImage


def _safe_disk_usage(path: Path):
    """Return shutil.disk_usage for the nearest existing path, or None."""
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    try:
        return shutil.disk_usage(candidate)
    except OSError:
        return None


def image_storage_stats() -> dict:
    media_root = Path(settings.MEDIA_ROOT)
    image_root = media_root / 'problem-images'

    files: dict[str, int] = {}
    if image_root.exists():
        for path in image_root.rglob('*'):
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
                relative = path.relative_to(media_root).as_posix()
            except (OSError, ValueError):
                continue
            files[relative] = int(size)

    db_names = {
        str(name).replace('\\', '/') for name in
        ProblemImage.objects.exclude(image='').values_list('image', flat=True)
        if name
    }

    total_image_bytes = sum(files.values())
    file_count = len(files)
    average_image_bytes = round(total_image_bytes / file_count) if file_count else 0
    missing_records = db_names - files.keys()
    orphan_files = files.keys() - db_names

    disk = _safe_disk_usage(media_root)
    if disk:
        volume_total_bytes = int(disk.total)
        volume_used_bytes = int(disk.used)
        volume_free_bytes = int(disk.free)
        volume_used_percent = round((disk.used / disk.total) * 100, 2) if disk.total else 0.0
        image_percent_of_volume = round((total_image_bytes / disk.total) * 100, 2) if disk.total else 0.0
    else:
        volume_total_bytes = None
        volume_used_bytes = None
        volume_free_bytes = None
        volume_used_percent = None
        image_percent_of_volume = None

    estimate_basis_bytes = average_image_bytes or TARGET_STORED_IMAGE_BYTES
    estimated_images_remaining = (
        int(volume_free_bytes // estimate_basis_bytes)
        if volume_free_bytes is not None and estimate_basis_bytes > 0
        else None
    )

    railway_volume = bool(os.getenv('RAILWAY_VOLUME_MOUNT_PATH'))
    return {
        'storage_kind': 'railway_volume' if railway_volume else 'filesystem',
        'persistent_volume_configured': railway_volume,
        'image_file_count': file_count,
        'database_image_records': len(db_names),
        'total_image_bytes': total_image_bytes,
        'average_image_bytes': average_image_bytes,
        'compression_target_bytes': TARGET_STORED_IMAGE_BYTES,
        'missing_image_file_count': len(missing_records),
        'orphan_image_file_count': len(orphan_files),
        'volume_total_bytes': volume_total_bytes,
        'volume_used_bytes': volume_used_bytes,
        'volume_free_bytes': volume_free_bytes,
        'volume_used_percent': volume_used_percent,
        'image_percent_of_volume': image_percent_of_volume,
        'estimated_images_remaining': estimated_images_remaining,
        'estimate_basis': 'current_average' if average_image_bytes else 'compression_target',
        'estimate_basis_bytes': estimate_basis_bytes,
    }
