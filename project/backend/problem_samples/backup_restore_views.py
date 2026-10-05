"""Administrator-only manual backup and restore API."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core import signing
from django.http import StreamingHttpResponse
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.views import is_tracker_admin
from .backup_restore import (
    BackupError,
    backup_filename,
    backup_restore_lock,
    backup_status,
    inspect_backup_archive,
    preflight_media_restore,
    restore_database,
    restore_media,
    stream_backup_archive,
)

DOWNLOAD_TOKEN_SALT = 'tracker-manual-backup-download-v1'
DOWNLOAD_TOKEN_MAX_AGE_SECONDS = 300
VALID_KINDS = {'database', 'media', 'full'}
RESTORE_CONFIRMATIONS = {
    'database': 'RESTORE DATABASE',
    'media': 'RESTORE MEDIA',
    'full': 'RESTORE FULL BACKUP',
}


def _admin_required(request):
    return bool(request.user and request.user.is_authenticated and is_tracker_admin(request.user))


class BackupRestoreStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _admin_required(request):
            return Response({'detail': 'Administrator access required.'}, status=403)
        return Response(backup_status())


class BackupPrepareDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _admin_required(request):
            return Response({'detail': 'Administrator access required.'}, status=403)
        kind = str(request.data.get('kind') or '').strip().lower()
        if kind not in VALID_KINDS:
            return Response({'detail': 'Choose database, media, or full backup.'}, status=400)
        token = signing.dumps({'user_id': request.user.pk, 'kind': kind}, salt=DOWNLOAD_TOKEN_SALT, compress=True)
        return Response({'token': token, 'kind': kind, 'expires_in_seconds': DOWNLOAD_TOKEN_MAX_AGE_SECONDS})


class BackupDownloadView(APIView):
    """Token-authorized POST download so the browser can stream to disk natively."""

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [FormParser]

    def post(self, request):
        token = str(request.data.get('token') or '')
        try:
            payload = signing.loads(token, salt=DOWNLOAD_TOKEN_SALT, max_age=DOWNLOAD_TOKEN_MAX_AGE_SECONDS)
        except signing.SignatureExpired:
            return Response({'detail': 'Backup download authorization expired. Start the download again.'}, status=403)
        except signing.BadSignature:
            return Response({'detail': 'Invalid backup download authorization.'}, status=403)
        kind = payload.get('kind')
        if kind not in VALID_KINDS:
            return Response({'detail': 'Invalid backup type.'}, status=400)
        try:
            user = User.objects.get(pk=payload.get('user_id'), is_active=True)
        except (User.DoesNotExist, TypeError, ValueError):
            return Response({'detail': 'Backup download authorization is no longer valid.'}, status=403)
        if not is_tracker_admin(user):
            return Response({'detail': 'Administrator access required.'}, status=403)

        try:
            stream = stream_backup_archive(kind)
        except BackupError as exc:
            return Response({'detail': str(exc)}, status=400)
        response = StreamingHttpResponse(stream, content_type='application/gzip')
        response['Content-Disposition'] = f'attachment; filename="{backup_filename(kind)}"'
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class BackupRestoreView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        if not _admin_required(request):
            return Response({'detail': 'Administrator access required.'}, status=403)
        kind = str(request.data.get('kind') or '').strip().lower()
        if kind not in VALID_KINDS:
            return Response({'detail': 'Choose database, media, or full restore.'}, status=400)
        required = RESTORE_CONFIRMATIONS[kind]
        if request.data.get('confirmation') != required:
            return Response({'detail': f'Type {required} to confirm.'}, status=400)
        uploaded = request.FILES.get('backup')
        if uploaded is None:
            return Response({'detail': 'Choose a tracker backup file.'}, status=400)

        try:
            with backup_restore_lock(exclusive=True, blocking=False):
                return self._restore_locked(request, kind, uploaded)
        except BackupError as exc:
            return Response({'detail': str(exc)}, status=400)

    def _restore_locked(self, request, kind, uploaded):
        try:
            inspected = inspect_backup_archive(uploaded)
            archive_kind = inspected.manifest.get('kind')
            allowed_archive_kinds = {
                'database': {'database', 'full'},
                'media': {'media', 'full'},
                'full': {'full'},
            }[kind]
            if archive_kind not in allowed_archive_kinds:
                return Response({'detail': f'This {archive_kind} backup cannot be used for a {kind} restore.'}, status=400)
            result = {'kind': kind, 'backup_kind': archive_kind, 'backup_created_at': inspected.manifest.get('created_at')}
            if kind == 'database':
                restore_database(uploaded, inspected)
                result.update({'database_restored': True, 'requires_relogin': True})
            elif kind == 'media':
                # Media-only restore is deliberately non-destructive to newer
                # files because the current database may still reference them.
                result.update(restore_media(uploaded, inspected, replace_extras=False))
                result.update({'media_restored': True, 'merge_restore': True, 'requires_relogin': False})
            else:
                # Check storage capacity before making the destructive database
                # change. The archive paths/manifest were already validated.
                preflight_media_restore(inspected)
                restore_database(uploaded, inspected)
                result.update(restore_media(uploaded, inspected, replace_extras=True))
                result.update({'database_restored': True, 'media_restored': True, 'requires_relogin': True})
            return Response(result)
        except BackupError as exc:
            return Response({'detail': str(exc)}, status=400)
