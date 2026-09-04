from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import LoginLink, AppSession, UserProfile


def normalize_email(value):
    return (value or '').strip().lower()


def allowed_email(email):
    if '@' not in email:
        return False
    local, domain=email.rsplit('@',1)
    if not local or domain != settings.AUTH_ALLOWED_DOMAIN:
        return False
    return not settings.AUTH_ALLOWED_EMAILS or email in settings.AUTH_ALLOWED_EMAILS


def normalize_role(value):
    value = (value or '').strip().lower().replace(' ', '_')
    aliases = {
        'lab_technician': UserProfile.ROLE_LAB_TECHNICIAN,
        'customer_service': UserProfile.ROLE_CUSTOMER_SERVICE,
    }
    return aliases.get(value, '')


def user_payload(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return {
        'id': user.id,
        'email': user.email,
        'name': user.get_full_name() or user.email,
        'role': profile.role,
        'role_label': profile.get_role_display() if profile.role else '',
        'needs_role': not bool(profile.role),
    }


@api_view(['POST'])
@permission_classes([AllowAny])
def request_login_link(request):
    email = normalize_email(request.data.get('email'))
    if not allowed_email(email):
        return Response({'detail':'This email address is not authorized.'}, status=status.HTTP_403_FORBIDDEN)

    now = timezone.now()
    # Only the newest login link for an address may remain usable.
    LoginLink.objects.filter(email=email, used_at__isnull=True).update(used_at=now)

    raw_token = LoginLink.new_token()
    LoginLink.objects.create(
        email=email,
        token_hash=LoginLink.hash_token(raw_token),
        expires_at=now + timedelta(minutes=settings.LOGIN_LINK_EXPIRES_MINUTES),
    )

    frontend = str(settings.FRONTEND_URL or '').rstrip('/')
    verification_url = f'{frontend}/login/verify?token={raw_token}'
    send_mail(
        subject='Edmonton Problem Sample Tracker sign-in link',
        message=(
            'Use the secure link below to sign in to the Edmonton Problem Sample Tracker:\n\n'
            f'{verification_url}\n\n'
            f'This link expires in {settings.LOGIN_LINK_EXPIRES_MINUTES} minutes and can only be used once. '
            'If you did not request this sign-in link, you can ignore this email.'
        ),
        from_email=None,
        recipient_list=[email],
        fail_silently=False,
    )

    # Django's console email backend prints the raw MIME message. Its
    # quoted-printable representation can make a perfectly valid URL look
    # different (for example `?token=` appears as `?token=3D` and long lines
    # may contain soft line breaks ending in `=`). Mail clients decode that
    # automatically, but developers copying directly from the terminal do not.
    # Print the original URL separately so local sign-in testing is unambiguous.
    if str(getattr(settings, 'EMAIL_BACKEND', '')).endswith('console.EmailBackend'):
        print('\n' + '=' * 78, flush=True)
        print('LOCAL DEVELOPMENT SIGN-IN LINK (copy/open this exact URL):', flush=True)
        print(verification_url, flush=True)
        print('=' * 78 + '\n', flush=True)

    return Response({'detail':'Sign-in link sent.'})


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_login_link(request):
    raw_token = str(request.data.get('token') or '').strip()
    if not raw_token:
        return Response({'detail':'Sign-in link is missing or invalid.'}, status=status.HTTP_400_BAD_REQUEST)

    token_hash = LoginLink.hash_token(raw_token)
    now = timezone.now()

    with transaction.atomic():
        try:
            login = LoginLink.objects.select_for_update().get(token_hash=token_hash)
        except LoginLink.DoesNotExist:
            return Response({'detail':'This sign-in link is invalid.'}, status=status.HTTP_400_BAD_REQUEST)

        if login.used_at is not None:
            return Response({'detail':'This sign-in link has already been used.'}, status=status.HTTP_400_BAD_REQUEST)
        if login.expires_at <= now:
            login.used_at = now
            login.save(update_fields=['used_at'])
            return Response({'detail':'This sign-in link has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        # Consume before creating the app session so this URL can never be exchanged twice.
        login.used_at = now
        login.save(update_fields=['used_at'])

        email = normalize_email(login.email)
        user, _ = User.objects.get_or_create(username=email, defaults={'email':email})
        if user.email != email:
            user.email=email
            user.save(update_fields=['email'])
        UserProfile.objects.get_or_create(user=user)

        token=AppSession.new_token()
        AppSession.objects.create(
            user=user,
            token_hash=AppSession.hash_token(token),
            expires_at=now+timedelta(hours=settings.SESSION_EXPIRES_HOURS),
        )

    return Response({'token':token,'user':user_payload(user)})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def me(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == 'PATCH':
        role = normalize_role(request.data.get('role'))
        if role not in {UserProfile.ROLE_LAB_TECHNICIAN, UserProfile.ROLE_CUSTOMER_SERVICE}:
            return Response({'detail':'Role must be Lab Technician or Customer Service.'}, status=status.HTTP_400_BAD_REQUEST)
        profile.role = role
        profile.save(update_fields=['role', 'modified_at'])

        # A Group-column default must always point at a user who still belongs
        # to that column's configured group. Keep historical row assignments,
        # but clear stale defaults after a user changes roles.
        from problem_samples.models import ProblemColumn
        email = (user.email or user.username or '').strip().lower()
        for column in ProblemColumn.objects.filter(column_type=ProblemColumn.TYPE_GROUP).exclude(group_role=role):
            if str(column.default_value or '').strip().lower() == email:
                column.default_value = None
                column.save(update_fields=['default_value', 'modified_at'])

    return Response(user_payload(user))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def users_by_role(request):
    role = normalize_role(request.query_params.get('role'))
    if role not in {UserProfile.ROLE_LAB_TECHNICIAN, UserProfile.ROLE_CUSTOMER_SERVICE}:
        return Response({'detail':'Role must be Lab Technician or Customer Service.'}, status=status.HTTP_400_BAD_REQUEST)
    profiles = (UserProfile.objects.filter(role=role, user__is_active=True)
                .select_related('user').order_by('user__email'))
    return Response([
        {
            'id': profile.user_id,
            'email': profile.user.email or profile.user.username,
            'name': profile.user.get_full_name() or profile.user.email or profile.user.username,
            'role': profile.role,
            'role_label': profile.get_role_display(),
        }
        for profile in profiles
    ])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    if request.auth:
        request.auth.revoked_at=timezone.now()
        request.auth.save(update_fields=['revoked_at'])
    return Response(status=status.HTTP_204_NO_CONTENT)
