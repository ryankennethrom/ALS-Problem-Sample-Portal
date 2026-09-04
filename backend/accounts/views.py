from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .account_utils import derive_unique_username, generate_temporary_password
from .models import AppSession, UserProfile


def normalize_role(value):
    value = (value or '').strip().lower().replace(' ', '_')
    aliases = {
        'lab_technician': UserProfile.ROLE_LAB_TECHNICIAN,
        'customer_service': UserProfile.ROLE_CUSTOMER_SERVICE,
    }
    return aliases.get(value, '')


def is_tracker_admin(user):
    if not user or not user.is_authenticated:
        return False
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return bool(user.is_superuser or profile.is_admin)


def user_payload(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    admin = bool(user.is_superuser or profile.is_admin)
    full_name = user.get_full_name().strip()
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'name': full_name or user.username,
        'role': profile.role,
        'role_label': profile.get_role_display() if profile.role else '',
        'needs_role': not admin and not bool(profile.role),
        'is_admin': admin,
    }



def get_managed_account(request, user_id):
    try:
        target = User.objects.select_related('tracker_profile').get(pk=user_id)
    except User.DoesNotExist:
        return None, Response(
            {'detail': 'User account not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if target.pk == request.user.pk:
        return None, Response(
            {'detail': 'Administrators cannot use this action on their own account.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return target, None


def clear_group_column_defaults_for_user(user):
    # Group-column assignments are stored as the user's username/email string,
    # not a foreign key. Clear only configured defaults so deleting an account
    # cannot prefill a future problem sample with a user who no longer exists.
    from problem_samples.models import ProblemColumn

    identifiers = {
        str(user.username or '').strip().lower(),
        str(user.email or '').strip().lower(),
    }
    identifiers.discard('')
    if not identifiers:
        return

    for column in ProblemColumn.objects.filter(column_type=ProblemColumn.TYPE_GROUP):
        if str(column.default_value or '').strip().lower() in identifiers:
            column.default_value = None
            column.save(update_fields=['default_value', 'modified_at'])

def account_list_payload(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    admin = bool(user.is_superuser or profile.is_admin)
    return {
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'name': user.get_full_name().strip() or user.username,
        'role': profile.role,
        'role_label': profile.get_role_display() if profile.role else '',
        'is_admin': admin,
        'is_active': user.is_active,
    }


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    username = str(request.data.get('username') or '').strip().lower()
    password = str(request.data.get('password') or '')
    if not username or not password:
        return Response(
            {'detail': 'Username and password are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response(
            {'detail': 'Invalid username or password.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    if not user.is_active:
        return Response(
            {'detail': 'This account is disabled.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    now = timezone.now()
    token = AppSession.new_token()
    AppSession.objects.create(
        user=user,
        token_hash=AppSession.hash_token(token),
        expires_at=now + timedelta(hours=settings.SESSION_EXPIRES_HOURS),
    )
    return Response({'token': token, 'user': user_payload(user)})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def accounts(request):
    if not is_tracker_admin(request.user):
        return Response(
            {'detail': 'Administrator access is required.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == 'GET':
        users = User.objects.all().order_by('first_name', 'last_name', 'username')
        return Response([account_list_payload(user) for user in users])

    first_name = str(request.data.get('first_name') or '').strip()
    last_name = str(request.data.get('last_name') or '').strip()
    if not first_name or not last_name:
        return Response(
            {'detail': 'First Name and Last Name are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(first_name) > 150 or len(last_name) > 150:
        return Response(
            {'detail': 'First Name and Last Name must each be 150 characters or fewer.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            username = derive_unique_username(first_name, last_name)
            generated_password = generate_temporary_password()
            user = User.objects.create_user(
                username=username,
                password=generated_password,
                first_name=first_name,
                last_name=last_name,
                email='',
            )
            UserProfile.objects.get_or_create(user=user)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    result = account_list_payload(user)
    result['generated_password'] = generated_password
    return Response(result, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    current_password = str(request.data.get('current_password') or '')
    new_password = str(request.data.get('new_password') or '')
    confirm_password = str(request.data.get('confirm_password') or '')

    if not current_password or not new_password or not confirm_password:
        return Response(
            {'detail': 'Current password, new password, and password confirmation are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not request.user.check_password(current_password):
        return Response(
            {'detail': 'Current password is incorrect.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if new_password != confirm_password:
        return Response(
            {'detail': 'New password and confirmation do not match.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(new_password) < 12:
        return Response(
            {'detail': 'New password must be at least 12 characters long.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if request.user.check_password(new_password):
        return Response(
            {'detail': 'New password must be different from the current password.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    request.user.set_password(new_password)
    request.user.save(update_fields=['password'])

    # Revoke other active bearer sessions after a password change while
    # preserving the session that performed the change.
    other_sessions = AppSession.objects.filter(
        user=request.user,
        revoked_at__isnull=True,
    )
    if request.auth:
        other_sessions = other_sessions.exclude(pk=request.auth.pk)
    other_sessions.update(revoked_at=timezone.now())

    return Response({'detail': 'Password changed successfully.'})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def me(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == 'PATCH':
        role = normalize_role(request.data.get('role'))
        if role not in {UserProfile.ROLE_LAB_TECHNICIAN, UserProfile.ROLE_CUSTOMER_SERVICE}:
            return Response(
                {'detail': 'Role must be Lab Technician or Customer Service.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile.role = role
        profile.save(update_fields=['role', 'modified_at'])

        # A Group-column default must always point at a user who still belongs
        # to that column's configured group. Keep historical row assignments,
        # but clear stale defaults after a user changes roles.
        from problem_samples.models import ProblemColumn
        identifier = (user.email or user.username or '').strip().lower()
        for column in ProblemColumn.objects.filter(column_type=ProblemColumn.TYPE_GROUP).exclude(group_role=role):
            if str(column.default_value or '').strip().lower() == identifier:
                column.default_value = None
                column.save(update_fields=['default_value', 'modified_at'])

    return Response(user_payload(user))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def users_by_role(request):
    role = normalize_role(request.query_params.get('role'))
    if role not in {UserProfile.ROLE_LAB_TECHNICIAN, UserProfile.ROLE_CUSTOMER_SERVICE}:
        return Response(
            {'detail': 'Role must be Lab Technician or Customer Service.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    profiles = (
        UserProfile.objects.filter(role=role, user__is_active=True)
        .select_related('user')
        .order_by('user__first_name', 'user__last_name', 'user__username')
    )
    return Response([
        {
            'id': profile.user_id,
            # Keep this legacy field for existing Group-column clients. Until
            # Entra adds staff email addresses, the username is the identifier.
            'email': profile.user.email or profile.user.username,
            'username': profile.user.username,
            'name': profile.user.get_full_name().strip() or profile.user.username,
            'role': profile.role,
            'role_label': profile.get_role_display(),
        }
        for profile in profiles
    ])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    if request.auth:
        request.auth.revoked_at = timezone.now()
        request.auth.save(update_fields=['revoked_at'])
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def account_admin_status(request, user_id):
    if not is_tracker_admin(request.user):
        return Response(
            {'detail': 'Administrator access is required.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    target, error_response = get_managed_account(request, user_id)
    if error_response is not None:
        return error_response

    requested_admin = request.data.get('is_admin')
    if not isinstance(requested_admin, bool):
        return Response(
            {'detail': 'is_admin must be true or false.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if target.is_superuser and not requested_admin:
        return Response(
            {'detail': 'A Django superuser cannot be demoted from tracker administration here.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    profile, _ = UserProfile.objects.get_or_create(user=target)
    profile.is_admin = requested_admin
    profile.save(update_fields=['is_admin', 'modified_at'])

    # Force a demoted administrator to sign in again so an already-open admin
    # interface cannot continue to look privileged after the role change.
    if not requested_admin:
        AppSession.objects.filter(user=target, revoked_at__isnull=True).update(revoked_at=timezone.now())

    return Response(account_list_payload(target))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reset_account_password(request, user_id):
    if not is_tracker_admin(request.user):
        return Response(
            {'detail': 'Administrator access is required.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    target, error_response = get_managed_account(request, user_id)
    if error_response is not None:
        return error_response

    generated_password = generate_temporary_password()
    target.set_password(generated_password)
    target.save(update_fields=['password'])
    AppSession.objects.filter(user=target, revoked_at__isnull=True).update(revoked_at=timezone.now())

    result = account_list_payload(target)
    result['generated_password'] = generated_password
    return Response(result)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_account(request, user_id):
    if not is_tracker_admin(request.user):
        return Response(
            {'detail': 'Administrator access is required.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    target, error_response = get_managed_account(request, user_id)
    if error_response is not None:
        return error_response

    clear_group_column_defaults_for_user(target)
    target.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
