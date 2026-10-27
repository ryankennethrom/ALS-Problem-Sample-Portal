"""Centralize selection and validation; NEVER accept arbitrary client labs for nonadmins."""
from rest_framework.exceptions import PermissionDenied, ValidationError
from accounts.models import Lab, UserProfile
from django.db import transaction


def admin_user(user):
    return bool(user.is_authenticated and (user.is_superuser or
        UserProfile.objects.filter(user=user, is_admin=True).exists()))


def active_lab(request, *, require_specific=False):
    if not request.user.is_authenticated:
        raise PermissionDenied('Sign in first.')
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if not profile.lab_id:
        raise PermissionDenied('A lab must be assigned to this account before using the tracker.')
    choice = str(request.headers.get('X-Active-Lab') or '').strip().upper()
    if not admin_user(request.user):
        if choice and choice not in {profile.lab.code, str(profile.lab_id)}:
            raise PermissionDenied('You cannot access another lab.')
        return profile.lab
    if choice == 'ALL':
        if require_specific:
            raise ValidationError({'lab': 'Select an individual lab before creating or editing tickets.'})
        return None
    if choice:
        selected = Lab.objects.filter(code=choice).first()
        if selected is None:
            raise ValidationError({'lab': 'Choose a valid lab.'})
        return selected
    return profile.lab


def scope_tickets(request, queryset):
    lab = active_lab(request)
    return queryset.filter(lab=lab) if lab else queryset


def scope_containers(request, queryset):
    lab = active_lab(request)
    return queryset.filter(lab=lab) if lab else queryset


def require_lab_matches(request, lab):
    selected = active_lab(request, require_specific=True)
    if not lab or lab.pk != selected.pk:
        raise PermissionDenied('This record belongs to a different lab.')
    return selected


def first_available_number(assigned_numbers):
    """Find the smallest positive unused number from an ordered PC number list.

    An existing container, even if empty or disposed, still owns its number.
    Old DC records are not included in this PC-only allocation.
    """
    candidate = 1
    for number in assigned_numbers:
        if number is None or number < candidate:
            continue
        if number > candidate:
            break
        candidate += 1
    return candidate


def archive_legacy_empty_disposal(container, *, reopened_at, reopened_by_id=None, reason=''):
    """Clear an empty PC's old disposal stamp without losing its audit data."""
    snapshot = dict(container.disposal_snapshot or {})
    events = list(snapshot.get('_legacy_reactivation_events') or [])
    events.append({
        'disposed_at': container.disposed_at.isoformat() if container.disposed_at else None,
        'disposed_by_id': container.disposed_by_id,
        'reactivated_at': reopened_at.isoformat(),
        'reactivated_by_id': reopened_by_id,
        'reason': reason,
    })
    snapshot['_legacy_reactivation_events'] = events
    container.disposal_snapshot = snapshot
    container.disposed_at = None
    container.disposed_by = None
    container.save(update_fields=['disposal_snapshot', 'disposed_at', 'disposed_by'])


def create_container(lab, *, created_by=None, **fields):
    """Allocate a per-lab PC gap first; DC audit numbers remain monotonic.

    A Lab row lock makes this atomic across concurrent allocations for a lab.
    Only missing numbers can be assigned to new containers. Disposed/empty
    physical containers keep their IDs until they are explicitly reactivated.
    """
    with transaction.atomic():
        locked = Lab.objects.select_for_update().get(pk=lab.pk)
        from .models import ProblemContainer
        if fields.get('is_dumping'):
            counter = 'next_dumping_container_number'
            number = locked.next_dumping_container_number
            locked.next_dumping_container_number = number + 1
            locked.save(update_fields=[counter])
        else:
            numbers = (ProblemContainer.objects.filter(lab=locked, is_dumping=False)
                       .exclude(lab_number__isnull=True)
                       .order_by('lab_number')
                       .values_list('lab_number', flat=True))
            number = first_available_number(numbers)
            # Preserve the high-water mark; it may be well beyond the gaps.
            if number >= locked.next_container_number:
                locked.next_container_number = number + 1
                locked.save(update_fields=['next_container_number'])
        return ProblemContainer.objects.create(lab=locked, lab_number=number, created_by=created_by, **fields)
