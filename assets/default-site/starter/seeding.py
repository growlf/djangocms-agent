"""Shared helpers for the seed_* management commands.

djangocms-versioning is installed, so create_page() produces a DRAFT. Every helper here works on
the admin (draft-aware) manager and publishes at the end, so seeding stays idempotent:
a page is looked up by PageUrl(slug, language), not by title.

Versioning is respected: published content is never edited in place. When something has to change
on a page that is already published (a template re-point, a refilled placeholder), a new draft is
created first (editable_content), changed, and then published. Pages that need no change get no new
version, so a repeated run adds nothing.
"""
from cms.api import add_plugin, create_page
from cms.models import Page, PageContent, PageUrl, Placeholder
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from djangocms_versioning import constants as vc
from djangocms_versioning.models import Version

LANG = "en"


def ensure_site():
    """Point the django Site (SITE_ID) at this project: name = SITE_NAME, domain = $SITE_DOMAIN (default
    localhost). Without it the admin and CMS toolbar keep showing the stock 'example.com'. Idempotent."""
    import os

    from django.conf import settings
    from django.contrib.sites.models import Site

    domain = os.environ.get("SITE_DOMAIN", "").strip() or "localhost"
    site, _ = Site.objects.update_or_create(
        pk=settings.SITE_ID, defaults={"name": settings.SITE_NAME[:50], "domain": domain[:100]})
    return site


def get_user():
    """A superuser if there is one, else a system user (publishing needs a real user object)."""
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).order_by("pk").first()
    if user is None:
        user, _ = User.objects.get_or_create(username="python-api", defaults={"is_active": False})
    return user


def page_for(slug):
    url = PageUrl.objects.filter(slug=slug, language=LANG).select_related("page").first()
    return url.page if url else None


def admin_content(page):
    return PageContent.admin_manager.current_content().get(page=page, language=LANG)


def editable_content(page, user):
    """The page's DRAFT content, creating one first when the current content is published
    (or has no version yet). Never returns published content for editing."""
    content = admin_content(page)
    version = content.versions.first()
    if version is None:  # content that predates djangocms-versioning
        Version.objects.create(content=content, created_by=user)
        return content
    if version.state == vc.DRAFT:
        return content
    return version.copy(user).content


def slot_is_empty(page, slot):
    """True when the slot has no plugins (a slot that does not exist yet counts as empty)."""
    ph = Placeholder.objects.get_for_obj(admin_content(page)).filter(slot=slot).first()
    return ph is None or not ph.get_plugins(LANG).exists()


def placeholder(page, slot):
    content = admin_content(page)
    content.rescan_placeholders()  # creates slots that are new to the template
    try:
        return Placeholder.objects.get_for_obj(content).get(slot=slot)
    except Placeholder.DoesNotExist:
        raise CommandError(f"Page '{page}' has no placeholder slot '{slot}'; check CMS_TEMPLATES and the template.")


def ensure_page(slug, title, template, user, parent=None, apphook=None, apphook_namespace=None,
                after=None, menu_title=None, in_navigation=True, reverse_id=None):
    """Create the page when missing; re-point its template when it changed. Returns (page, created)."""
    page = page_for(slug)
    if page is not None:
        if reverse_id and not page.reverse_id and not Page.objects.filter(reverse_id=reverse_id, node__site=page.node.site).exists():
            page.reverse_id = reverse_id  # lets templates link with {% page_url "reverse_id" %} instead of a hard-coded path
            page.save(update_fields=["reverse_id"])
        if admin_content(page).template != template:
            content = editable_content(page, user)
            content.template = template
            content.save(update_fields=["template"])
        return page, False
    page = create_page(
        title, template, LANG, slug=slug, menu_title=menu_title, parent=parent, in_navigation=in_navigation,
        apphook=apphook, apphook_namespace=apphook_namespace, created_by=user, reverse_id=reverse_id,
    )
    if after is not None:
        page.move_page(after, position="right")
    return page, True


def fill(ph, specs):
    """Add plugins only when the placeholder is empty. spec = (plugin_type, data_dict)."""
    if ph.get_plugins(LANG).exists():
        return False
    for plugin_type, data in specs:
        add_plugin(ph, plugin_type, LANG, **data)
    return True


def publish(page, user):
    """Publish the page's content if it is a draft (or has no version yet). Safe to repeat."""
    content = admin_content(page)
    version = content.versions.first()
    if version is None:  # content that predates djangocms-versioning
        version = Version.objects.create(content=content, created_by=user)
    if version.state == vc.DRAFT:
        version.publish(user)
