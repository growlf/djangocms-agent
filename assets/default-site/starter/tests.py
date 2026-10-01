import copy
import os
import shutil
import subprocess
import sys
import tempfile
from io import StringIO
from unittest import mock

from cms.models import CMSPlugin, Page, PageUrl
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings
from djangocms_versioning.constants import PUBLISHED
from djangocms_versioning.models import Version

from starter.seeding import ensure_page, get_user, publish

# seeding writes sample files through filer; keep them out of the project's media/
_MEDIA = tempfile.mkdtemp(prefix="default-site-media-")


def tearDownModule():
    shutil.rmtree(_MEDIA, ignore_errors=True)


SLUGS = ["home", "about", "style-and-capabilities"]


def seed():
    for name in ("seed_pages", "seed_site"):
        call_command(name, stdout=StringIO())


@override_settings(MEDIA_ROOT=_MEDIA)
class SeedTests(TestCase):
    def test_seed_is_idempotent(self):
        seed()
        first = (Page.objects.count(), CMSPlugin.objects.count())
        seed()
        self.assertEqual(first, (Page.objects.count(), CMSPlugin.objects.count()))
        for slug in SLUGS:
            self.assertEqual(PageUrl.objects.filter(slug=slug, language="en").count(), 1, slug)

    def test_site_is_named_after_the_project_and_idempotent(self):
        from django.contrib.sites.models import Site
        seed()
        site = Site.objects.get(pk=settings.SITE_ID)
        self.assertEqual(site.name, settings.SITE_NAME[:50])
        self.assertEqual(site.domain, "localhost")
        self.assertNotEqual(site.domain, "example.com")
        seed()
        self.assertEqual(Site.objects.count(), 1)
        self.assertEqual(Site.objects.get(pk=settings.SITE_ID).domain, "localhost")

    def test_site_domain_comes_from_env(self):
        from django.contrib.sites.models import Site
        with mock.patch.dict(os.environ, {"SITE_DOMAIN": "www.example.org"}):
            seed()
        self.assertEqual(Site.objects.get(pk=settings.SITE_ID).domain, "www.example.org")

    def test_everything_is_published(self):
        seed()
        self.assertFalse(Version.objects.exclude(state=PUBLISHED).exists())
        for slug in SLUGS:
            self.assertEqual(self.client.get("/" if slug == "home" else f"/{slug}/").status_code, 200, slug)

    def test_home_is_landing_template_with_all_slots(self):
        seed()
        home = PageUrl.objects.get(slug="home").page
        self.assertTrue(home.is_home)
        self.assertEqual(home.get_template("en"), "landing.html")
        slots = {p.slot for p in home.get_placeholders("en")}
        self.assertTrue({"hero", "feature_1", "feature_2", "feature_3", "content", "cta"} <= slots)

    def test_reset_refills_without_duplicating(self):
        seed()
        before = CMSPlugin.objects.count()
        call_command("seed_site", "--reset", stdout=StringIO())
        self.assertEqual(before, CMSPlugin.objects.count())

    def test_get_user_returns_real_user_when_no_superuser(self):
        user = get_user()
        self.assertIsNotNone(user.pk)
        self.assertFalse(user.is_active)


@override_settings(MEDIA_ROOT=_MEDIA)
class ThemeTests(TestCase):
    def setUp(self):
        seed()

    def test_stylesheet_served(self):
        from django.contrib.staticfiles import finders
        path = finders.find("css/site.css")
        self.assertIsNotNone(path)
        with open(path) as fh:
            self.assertIn("--site-color-bg", fh.read())

    def test_base_renders_site_name_nav_and_assets(self):
        r = self.client.get("/")
        self.assertContains(r, f'class="navbar-brand site-logo fw-bold" href="/">{settings.SITE_NAME}<')
        self.assertContains(r, 'href="/static/css/site.css"')
        self.assertContains(r, 'href="/static/vendor/bootstrap/css/bootstrap.min.css"')
        self.assertContains(r, 'src="/static/vendor/bootstrap/js/bootstrap.bundle.min.js"')
        self.assertNotContains(r, "cdn.jsdelivr")
        self.assertContains(r, 'aria-label="Main navigation"')
        self.assertContains(r, 'aria-current="page"')
        self.assertContains(r, f"<title>Home | {settings.SITE_NAME}</title>", html=True)

    def test_sidebar_only_on_standard_template(self):
        self.assertNotContains(self.client.get("/"), "sidebar")
        standard = self.client.get("/about/")
        self.assertContains(standard, 'class="col-lg-4 sidebar"')
        self.assertContains(standard, "layout-standard")

    def test_hero_only_on_landing(self):
        landing = self.client.get("/")
        self.assertContains(landing, 'class="hero ')
        self.assertContains(landing, "cta-band")
        for path in ("/about/", "/style-and-capabilities/"):
            self.assertNotContains(self.client.get(path), 'class="hero ', msg_prefix=path)

    def test_templates_registered(self):
        self.assertEqual([t[0] for t in settings.CMS_TEMPLATES], ["landing.html", "standard.html"])

    def test_hamburger_markup(self):
        r = self.client.get("/")
        for needle in ('class="navbar-toggler"', 'data-bs-toggle="collapse"', 'data-bs-target="#site-nav"',
                       'aria-controls="site-nav"', 'aria-label="Toggle navigation"', 'id="site-nav"', "navbar-expand-lg"):
            self.assertContains(r, needle)

    def test_theme_script_and_skip_link(self):
        r = self.client.get("/")
        self.assertContains(r, "js/theme.js")
        self.assertContains(r, 'href="#main"')
        self.assertContains(r, 'id="main"')

    def test_style_page_components(self):
        style = self.client.get("/style-and-capabilities/")
        for needle in ("accordion-item", "<table", "<pre", "form-control", "btn btn-primary", "Alias content", "<form"):
            self.assertContains(style, needle)

    def test_nested_menu_levels(self):
        """A three-level tree gives one dropdown (level 0) with flat, indented descendants."""
        user = get_user()
        with transaction.atomic():
            parent, _ = ensure_page("section", "Section", "standard.html", user)
            publish(parent, user)
            child, _ = ensure_page("child", "Child", "standard.html", user, parent=parent)
            publish(child, user)
            grandchild, _ = ensure_page("grandchild", "Grandchild", "standard.html", user, parent=child)
            publish(grandchild, user)
        r = self.client.get("/")
        self.assertContains(r, 'data-bs-toggle="dropdown"', count=1)
        self.assertContains(r, 'class="dropdown-menu"', count=1)
        self.assertContains(r, "Grandchild")
        self.assertContains(r, "ps-4")

    def test_no_unresolved_template_variables(self):
        opts = copy.deepcopy(settings.TEMPLATES)
        opts[0]["OPTIONS"]["string_if_invalid"] = "UNRESOLVED:%s"
        with override_settings(TEMPLATES=opts):
            for p in ("/", "/about/", "/style-and-capabilities/"):
                self.assertNotContains(self.client.get(p), "UNRESOLVED:", msg_prefix=p)


class SettingsTests(TestCase):
    def test_toolbar_and_clickjacking(self):
        self.assertFalse(settings.CMS_TOOLBAR_ANONYMOUS_ON)
        self.assertEqual(settings.X_FRAME_OPTIONS, "SAMEORIGIN")
        self.assertIn("django.contrib.admindocs", settings.INSTALLED_APPS)
        self.assertIn("djangocms_versioning", settings.INSTALLED_APPS)
        self.assertEqual(settings.MIDDLEWARE[0], "cms.middleware.utils.ApphookReloadMiddleware")

    def test_template_loaders_are_explicit_without_app_dirs(self):
        t = settings.TEMPLATES[0]
        self.assertIn("django.template.loaders.app_directories.Loader", t["OPTIONS"]["loaders"])
        self.assertFalse(t.get("APP_DIRS", False))

    def test_admindocs_available_to_staff(self):
        user = get_user_model().objects.create_superuser("docs", "d@example.com", "x")
        self.client.force_login(user)
        r = self.client.get("/admin/docs/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Documentation")

    def test_anonymous_gets_no_toolbar(self):
        seed_ctx = override_settings(MEDIA_ROOT=_MEDIA)
        with seed_ctx:
            seed()
        r = self.client.get("/?toolbar_on")
        self.assertNotContains(r, "cms-toolbar-login")
        self.assertNotContains(r, 'class="cms-toolbar')

    def test_debug_toolbar_only_with_debug_and_never_before_apphook_reload(self):
        code = ("import django; django.setup(); from django.conf import settings as s; "
                "print('debug_toolbar' in s.INSTALLED_APPS, "
                "any('debug_toolbar' in m for m in s.MIDDLEWARE), bool(getattr(s, 'INTERNAL_IPS', [])), "
                "s.MIDDLEWARE[0].endswith('ApphookReloadMiddleware'))")

        def run(debug):
            env = {"PATH": os.environ.get("PATH", "/usr/bin"), "DJANGO_SETTINGS_MODULE": os.environ["DJANGO_SETTINGS_MODULE"],
                   "DJANGO_SECRET_KEY": "x" * 50}
            if debug:
                env["DJANGO_DEBUG"] = "1"
            out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=settings.BASE_DIR)
            self.assertEqual(out.returncode, 0, out.stderr)
            return out.stdout.strip()

        self.assertEqual(run(debug=False), "False False False True")
        self.assertEqual(run(debug=True), "True True True True")
