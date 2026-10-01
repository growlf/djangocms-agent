from django.conf import settings


def site(request):
    """Expose the site name (settings.SITE_NAME) to every template as site_name."""
    return {"site_name": settings.SITE_NAME}
