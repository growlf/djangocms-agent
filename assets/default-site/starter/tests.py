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
from djangocms_versioning.constants import DRAFT, PUBLISHED
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
        self.assertFalse(Version.objects.filter(state=DRAFT).exists())  # older versions are archived, nothing stays a draft
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
        from cms.models import PageContent, Placeholder

        def live_plugins():  # plugins on the PUBLISHED content (archived versions keep their own copies)
            return sum(ph.get_plugins("en").count() for c in PageContent.objects.all()
                       for ph in Placeholder.objects.get_for_obj(c))
        seed()
        before = live_plugins()
        call_command("seed_site", "--reset", stdout=StringIO())
        self.assertEqual(before, live_plugins())
        self.assertFalse(Version.objects.filter(state=DRAFT).exists())

    def test_get_user_returns_real_user_when_no_superuser(self):
        user = get_user()
        self.assertIsNotNone(user.pk)
        self.assertFalse(user.is_active)


@override_settings(MEDIA_ROOT=_MEDIA)
class SampleImageTests(TestCase):
    """D4: the style page's Picture sample must be legible (large, high-contrast text), not tiny default-font text."""

    def test_sample_image_is_deterministic_small_and_high_contrast(self):
        from PIL import Image as PILImage
        from starter.management.commands.seed_site import sample_image_bytes
        data = sample_image_bytes()
        self.assertEqual(data, sample_image_bytes())
        self.assertLess(len(data), 100_000)
        img = PILImage.open(__import__("io").BytesIO(data)).convert("RGB")
        self.assertEqual(img.size, (1200, 600))
        panel = img.getpixel((200, 300))  # inside the text panel, away from the glyphs
        self.assertLess(sum(panel), 90)  # near-black
        # big glyphs: plenty of near-white pixels in the title band (default 10px text gave a few hundred)
        band = img.crop((250, 220, 950, 320))
        white = sum(1 for px in band.getdata() if min(px) > 235)
        self.assertGreater(white, 4000)

    @override_settings(MEDIA_ROOT=_MEDIA)
    def test_seeded_style_page_uses_the_new_sample(self):
        from filer.models import Image
        seed()
        self.assertTrue(Image.objects.filter(original_filename="style-sample-v2.png").exists())
        self.assertFalse(Image.objects.filter(original_filename="style-sample.png").exists())


class SeedVersioningTests(TestCase):
    """Seeding goes through djangocms-versioning: published content is never edited in place."""

    def versions(self, slug):
        from cms.models import PageContent
        page = PageUrl.objects.get(slug=slug, language="en").page
        contents = PageContent.admin_manager.filter(page=page, language="en")
        return sorted(((v.pk, v.state, v.content) for c in contents for v in c.versions.all()), key=lambda t: t[0])

    def plugin_count(self, content):
        from cms.models import Placeholder
        return sum(ph.get_plugins("en").count() for ph in Placeholder.objects.get_for_obj(content))

    def test_plugins_are_added_to_a_draft_and_published_once(self):
        seed()
        for slug in SLUGS:
            states = [(state, self.plugin_count(content)) for _pk, state, content in self.versions(slug)]
            self.assertEqual([s for s, _ in states].count(PUBLISHED), 1, slug)
            self.assertNotIn(DRAFT, [s for s, _ in states], slug)
            self.assertGreater(states[-1][1], 0, slug)
        # seed_pages published the empty home page first; seed_site filled a NEW draft, so the first
        # (now archived) version stays empty: nothing was added to published content.
        home = [(state, self.plugin_count(content)) for _pk, state, content in self.versions("home")]
        self.assertEqual(home[0][1], 0)
        self.assertEqual(home[-1][0], PUBLISHED)

    def test_second_run_adds_no_versions(self):
        seed()
        before = Version.objects.count()
        seed()
        self.assertEqual(before, Version.objects.count())

    def test_refill_after_editor_emptied_slot_uses_a_new_draft(self):
        from cms.models import Placeholder
        seed()
        pub = [c for _pk, st, c in self.versions("about") if st == PUBLISHED][0]
        draft = pub.versions.first().copy(get_user()).content  # what an editor does
        for ph in Placeholder.objects.get_for_obj(draft):
            ph.clear("en")
        draft.versions.first().publish(get_user())
        n = Version.objects.count()
        call_command("seed_site", stdout=StringIO())
        self.assertEqual(Version.objects.count(), n + 1)
        edited = [c for _pk, st, c in self.versions("about") if c.pk == draft.pk][0]
        self.assertEqual(self.plugin_count(edited), 0)  # the editor's version was not touched
        self.assertGreater(self.plugin_count([c for _pk, st, c in self.versions("about") if st == PUBLISHED][0]), 0)

    def test_template_change_on_published_page_goes_through_a_draft(self):
        seed()
        user = get_user()
        page = PageUrl.objects.get(slug="about", language="en").page
        ensure_page("about", "About", "landing.html", user)
        states = {st: c.template for _pk, st, c in self.versions("about")}
        self.assertEqual(states[DRAFT], "landing.html")
        self.assertEqual(states[PUBLISHED], "standard.html")  # live content untouched until published
        publish(page, user)
        self.assertEqual(self.client.get("/about/").status_code, 200)

    def test_seed_first_run_only(self):
        out = StringIO()
        call_command("seed", "--first-run-only", stdout=out)
        self.assertEqual(Page.objects.count(), len(SLUGS))
        n = Version.objects.count()
        out = StringIO()
        call_command("seed", "--first-run-only", stdout=out)
        self.assertIn("not seeding", out.getvalue())
        self.assertEqual(n, Version.objects.count())

    def test_first_run_only_does_not_refill_a_slot_the_editor_emptied(self):
        from cms.models import Placeholder
        call_command("seed", "--first-run-only", stdout=StringIO())
        pub = [c for _pk, st, c in self.versions("about") if st == PUBLISHED][0]
        draft = pub.versions.first().copy(get_user()).content
        for ph in Placeholder.objects.get_for_obj(draft):
            ph.clear("en")
        draft.versions.first().publish(get_user())
        n = Version.objects.count()
        call_command("seed", "--first-run-only", stdout=StringIO())
        self.assertEqual(Version.objects.count(), n)

    def test_pages_get_reverse_ids(self):
        seed()
        self.assertEqual(set(Page.objects.exclude(reverse_id=None).values_list("reverse_id", flat=True)), set(SLUGS))


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

    def test_theme_toggle_button_on_every_page(self):
        for path in ("/", "/about/", "/style-and-capabilities/"):
            r = self.client.get(path)
            self.assertContains(r, "data-theme-toggle", msg_prefix=path)
            self.assertContains(r, 'aria-label="Dark mode"', msg_prefix=path)
            self.assertContains(r, 'aria-pressed="false"', msg_prefix=path)
            html = r.content.decode()
            self.assertLess(html.index("data-theme-toggle"), html.index('class="collapse navbar-collapse"'))  # outside the hamburger
            self.assertLess(html.index("js/theme.js"), html.index("</head>"))  # applied before first paint

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
        self.assertContains(r, '<button type="button" class="nav-link dropdown-toggle', count=1)  # a real button: Space/Enter
        self.assertNotContains(r, 'role="button"')
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
