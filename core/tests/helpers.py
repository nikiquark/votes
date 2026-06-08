from django.contrib.auth.models import User
from django.utils import timezone

from core.models import Organization, OrganizationUser


def create_org_user(username="john", email="john@example.com", organization=None, **user_kwargs):
    """Создаёт пользователя, организацию (если не передана) и связку OrganizationUser."""
    user = User.objects.create_user(
        username=username,
        password="testpass123",
        first_name=user_kwargs.pop("first_name", "John"),
        last_name=user_kwargs.pop("last_name", "Doe"),
        email=email,
        **user_kwargs,
    )
    if organization is None:
        organization = Organization.objects.create(
            name=f"Org for {username}",
            paid_until=timezone.localdate() + timezone.timedelta(days=30),
        )
    return OrganizationUser.objects.create(user=user, organization=organization)
