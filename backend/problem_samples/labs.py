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


def create_container(lab, *, created_by=None, **fields):
    """Independent serial per lab; atomic for concurrent requests."""
    with transaction.atomic():
        locked = Lab.objects.select_for_update().get(pk=lab.pk)
        number = locked.next_container_number
        locked.next_container_number = number + 1
        locked.save(update_fields=['next_container_number'])
        from .models import ProblemContainer
        return ProblemContainer.objects.create(lab=locked, lab_number=number, created_by=created_by, **fields)
