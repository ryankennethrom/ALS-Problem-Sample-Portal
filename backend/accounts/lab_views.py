import re
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Lab, UserProfile
from .views import user_payload, is_tracker_admin
from problem_samples.labs import active_lab


def _payload(lab):
    return {'id': lab.pk, 'name': lab.name, 'code': lab.code,
        'lab_notification_mode': lab.lab_notification_mode,
        'lab_notification_emails': lab.lab_notification_emails,
        'customer_service_notification_mode': lab.customer_service_notification_mode,
        'customer_service_notification_emails': lab.customer_service_notification_emails}

def _reference_counts(lab):
    """Count every ORM reverse relation, including CASCADE and nullable FKs.

    Checking only protected relations is unsafe: template rows, for example,
    use CASCADE and must not be silently deleted along with a lab.
    """
    labels = {
        'staff_profiles': 'Staff accounts',
        'tickets': 'Tickets',
        'containers': 'Containers',
        'prepared_tickets': 'Prepared tickets',
        'ticket_creation_timings': 'Ticket creation timings',
        'system_emails': 'System emails',
        'email_templates': 'Email templates',
    }
    counts = {}
    for relation in Lab._meta.related_objects:
        field = relation.field
        if not hasattr(field, 'attname'):
            continue
        count = relation.related_model._base_manager.filter(**{field.attname: lab.pk}).count()
        if count:
            label = labels.get(relation.get_accessor_name(), str(relation.related_model._meta.verbose_name_plural).capitalize())
            counts[label] = count
    return counts


def _management_payload(lab):
    data = _payload(lab)
    data['references'] = _reference_counts(lab)
    data['can_delete'] = not data['references'] and Lab.objects.count() > 1
    return data


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def lab_detail(request, lab_id):
    if not is_tracker_admin(request.user):
        return Response({'detail': 'Administrator only.'}, status=403)
    with transaction.atomic():
        lab = Lab.objects.select_for_update().filter(pk=lab_id).first()
        if lab is None:
            return Response({'detail': 'Lab not found.'}, status=404)

        if request.method == 'PATCH':
            # Codes are immutable: changing one could invalidate container IDs,
            # existing bookmarks, and saved client-side selections.
            if set(request.data.keys()) != {'name'}:
                return Response({'detail': 'Only the lab name can be changed. Lab codes cannot be edited.'}, status=400)
            name = request.data.get('name')
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
                return Response({'detail': 'Lab name must be 1–100 characters.'}, status=400)
            name = name.strip()
            if Lab.objects.filter(name__iexact=name).exclude(pk=lab.pk).exists():
                return Response({'detail': 'Another lab already uses that name.'}, status=400)
            lab.name = name
            try:
                lab.save(update_fields=['name'])
            except IntegrityError:
                return Response({'detail': 'Another lab already uses that name.'}, status=400)
            return Response(_management_payload(lab))

        # Hold a row lock during the reference check and deletion. PostgreSQL
        # FK inserts take a key-share lock and cannot race this operation.
        references = _reference_counts(lab)
        if references:
            return Response({'detail': 'Cannot delete this lab while it is referenced.', 'references': references}, status=409)
        if Lab.objects.count() <= 1:
            return Response({'detail': 'Cannot delete the last lab. The app needs at least one lab.'}, status=409)
        try:
            lab.delete()
        except (ProtectedError, IntegrityError):
            return Response({'detail': 'Cannot delete this lab because it is still referenced.'}, status=409)
        return Response(status=204)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def labs(request):
    if request.method == 'GET':
        if is_tracker_admin(request.user):
            return Response([_management_payload(x) for x in Lab.objects.all()])
        profile = getattr(request.user, 'tracker_profile', None)
        return Response([_payload(profile.lab)] if profile and profile.lab_id else [])
    if not is_tracker_admin(request.user):
        return Response({'detail': 'Administrator only.'}, status=403)
    name = str(request.data.get('name') or '').strip()
    code = str(request.data.get('code') or '').strip().upper()
    if not name or not re.fullmatch(r'[A-Z0-9]{2,12}', code):
        return Response({'detail': 'Provide a lab name and 2–12-character alphanumeric code.'}, status=400)
    if len(name) > 100:
        return Response({'detail': 'Lab name cannot exceed 100 characters.'}, status=400)
    if Lab.objects.filter(code__iexact=code).exists():
        return Response({'detail': 'Lab code already exists.'}, status=400)
    if Lab.objects.filter(name__iexact=name).exists():
        return Response({'detail': 'Lab name already exists.'}, status=400)
    try:
        lab = Lab.objects.create(name=name, code=code)
    except IntegrityError:
        return Response({'detail': 'Lab name or code already exists.'}, status=400)
    return Response(_management_payload(lab), status=201)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def my_lab(request):
    if not is_tracker_admin(request.user):
        return Response({'detail': 'Only administrators can set their own lab.'}, status=403)
    lab = Lab.objects.filter(pk=request.data.get('lab_id')).first()
    if lab is None:
        return Response({'detail': 'Select a valid lab.'}, status=400)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.lab = lab
    profile.save(update_fields=['lab', 'modified_at'])
    return Response(user_payload(request.user))

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def lab_notifications(request):
    lab = active_lab(request, require_specific=True)
    if request.method == 'PUT':
        if not is_tracker_admin(request.user):
            return Response({'detail': 'Administrator only.'}, status=403)
        updates = {}
        for prefix in ('lab', 'customer_service'):
            mode = request.data.get(f'{prefix}_notification_mode')
            addresses = request.data.get(f'{prefix}_notification_emails')
            if mode not in ('staff', 'addresses') or not isinstance(addresses, list):
                return Response({'detail': f'Invalid {prefix} notification configuration.'}, status=400)
            if len(addresses) > 50:
                return Response({'detail': 'Maximum 50 addresses per role.'}, status=400)
            cleaned = []
            for email in addresses:
                try:
                    validate_email(email)
                except (DjangoValidationError, TypeError, ValueError):
                    return Response({'detail': f'Invalid notification email: {email}'}, status=400)
                if email.strip().lower() not in [v.lower() for v in cleaned]:
                    cleaned.append(email.strip())
            updates[f'{prefix}_notification_mode'] = mode
            updates[f'{prefix}_notification_emails'] = cleaned
        for field, value in updates.items():
            setattr(lab, field, value)
        lab.save(update_fields=list(updates))
    return Response(_payload(lab))
