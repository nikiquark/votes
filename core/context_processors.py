from django.conf import settings
from .models import OrganizationUser


def organization_context(request):
    """
    Provides current organization and list of organizations for the authenticated user.
    Selection is kept in session under ``current_org_id``.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {
            "SITE_NAME": getattr(settings, "SITE_NAME", ""),
        }

    org_users = list(
        OrganizationUser.objects.select_related("organization")
        .filter(user=user)
        .order_by("organization__name")
    )
    organizations = [ou.organization for ou in org_users]

    current_org_id = request.session.get("current_org_id")
    current_organization = None
    if current_org_id:
        current_organization = next(
            (org for org in organizations if org.id == current_org_id), None
        )
    if not current_organization and organizations:
        current_organization = organizations[0]

    return {
        "user_organizations": organizations,
        "current_organization": current_organization,
        "SITE_NAME": getattr(settings, "SITE_NAME", ""),
    }

