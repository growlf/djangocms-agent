"""Offline tests for the Docker/PostgreSQL support: DB switch, WhiteNoise, health, media flag, container files."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from cms.models import Page
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

BASE = Path(__file__).resolve().parent.parent
# A site created with --no-docker has no container files: checks on them skip themselves.
docker_only = unittest.skipUnless((BASE / 'Dockerfile').exists(), 'site was created with --no-docker: no container files to check')
_MEDIA = tempfile.mkdtemp(prefix="default-site-media-")


def tearDownModule():
    shutil.rmtree(_MEDIA, ignore_errors=True)


def settings_in_subprocess(env_extra, expr):
    """Evaluate `expr` (with `s` = django.conf.settings) in a fresh interpreter with a clean DB_*/DJANGO_* env."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DB_', 'DJANGO_'))}
    env.update({'DJANGO_SECRET_KEY': 'x', 'DJANGO_ALLOWED_HOSTS': 'localhost',
                'DJANGO_SETTINGS_MODULE': '__PROJECT_NAME__.settings'}, **env_extra)
    code = f"from django.conf import settings as s; import json; print(json.dumps({expr}))"
    out = subprocess.run([sys.executable, '-c', code], env=env, cwd=BASE, capture_output=True,
                         text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


class DatabaseSwitchTests(SimpleTestCase):
    def test_unset_is_sqlite(self):
        engine = settings_in_subprocess({}, "s.DATABASES['default']['ENGINE']")
        self.assertEqual(engine, 'django.db.backends.sqlite3')

    def test_other_value_is_sqlite(self):
        engine = settings_in_subprocess({'DB_ENGINE': 'sqlite'}, "s.DATABASES['default']['ENGINE']")
        self.assertEqual(engine, 'django.db.backends.sqlite3')

    def test_postgres_from_env(self):
        db = settings_in_subprocess(
            {'DB_ENGINE': 'postgres', 'DB_HOST': 'h', 'DB_PORT': '6543', 'DB_NAME': 'n',
             'DB_USER': 'u', 'DB_PASSWORD': 'p'},
            "{k: v for k, v in s.DATABASES['default'].items() if k != 'CONN_MAX_AGE'}")
        self.assertEqual(db, {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'n', 'USER': 'u',
                              'PASSWORD': 'p', 'HOST': 'h', 'PORT': '6543'})

    def test_postgres_defaults_match_compose(self):
        db = settings_in_subprocess({'DB_ENGINE': 'postgres'}, "s.DATABASES['default']")
        self.assertEqual((db['NAME'], db['USER'], db['HOST'], db['PORT']),
                         ('__PROJECT_NAME__', '__PROJECT_NAME__', 'db', '5432'))


class MiddlewareAndStaticTests(SimpleTestCase):
    def test_middleware_order_and_toolbar_off(self):
        mw = settings_in_subprocess({'DJANGO_DEBUG': '0'}, "s.MIDDLEWARE")
        self.assertEqual(mw[0], 'cms.middleware.utils.ApphookReloadMiddleware')
        self.assertEqual(mw[1], 'django.middleware.security.SecurityMiddleware')
        self.assertEqual(mw[2], 'whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertFalse(any('debug_toolbar' in m for m in mw))

    def test_toolbar_keeps_apphook_reload_first_and_whitenoise_after_security(self):
        mw = settings_in_subprocess({'DJANGO_DEBUG': '1'}, "s.MIDDLEWARE")
        self.assertEqual(mw[0], 'cms.middleware.utils.ApphookReloadMiddleware')
        self.assertEqual(mw[1], 'debug_toolbar.middleware.DebugToolbarMiddleware')
        self.assertEqual(mw.index('whitenoise.middleware.WhiteNoiseMiddleware'),
                         mw.index('django.middleware.security.SecurityMiddleware') + 1)
        off = settings_in_subprocess({'DJANGO_DEBUG': '1', 'DJANGO_DEBUG_TOOLBAR': '0'}, "s.MIDDLEWARE")
        self.assertFalse(any('debug_toolbar' in m for m in off))

    def test_static_storage_is_whitenoise_and_root_exists(self):
        got = settings_in_subprocess({}, "[s.STORAGES['staticfiles']['BACKEND'], str(s.STATIC_ROOT)]")
        self.assertEqual(got[0], 'whitenoise.storage.CompressedStaticFilesStorage')
        self.assertTrue(Path(got[1]).is_dir())  # settings create it, so WhiteNoise does not warn

    def test_csrf_origins_from_env(self):
        o = settings_in_subprocess({'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://a.example, https://b.example'},
                                   "s.CSRF_TRUSTED_ORIGINS")
        self.assertEqual(o, ['https://a.example', 'https://b.example'])

    def test_proxy_header_only_when_flagged(self):
        expr = "list(getattr(s, 'SECURE_PROXY_SSL_HEADER', None) or [])"
        self.assertEqual(settings_in_subprocess({}, expr), [])
        self.assertEqual(settings_in_subprocess({'DJANGO_BEHIND_PROXY': '1'}, expr),
                         ['HTTP_X_FORWARDED_PROTO', 'https'])


class HealthTests(TestCase):
    def test_health_ok(self):
        r = self.client.get('/health/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'status': 'ok'})

    def test_health_rejects_post(self):
        self.assertEqual(self.client.post('/health/').status_code, 405)


@override_settings(MEDIA_ROOT=_MEDIA)
class SeedCommandTests(TestCase):
    def test_seed_runs_both_and_is_idempotent(self):
        call_command('seed', stdout=StringIO())
        first = Page.objects.count()
        self.assertGreaterEqual(first, 3)  # home, about, style-and-capabilities
        call_command('seed', stdout=StringIO())
        self.assertEqual(Page.objects.count(), first)


@docker_only
class ContainerFilesTests(SimpleTestCase):
    def test_container_files_present(self):
        for rel in ('Dockerfile', 'docker-compose.yml', 'docker-compose.dev.yml', 'docker/entrypoint.sh',
                    'docker/dev-entrypoint.sh', '.dockerignore', 'bin/docker-up.sh', 'bin/docker-down.sh',
                    'bin/docker-env.sh', 'bin/docker-backup.sh', 'bin/docker-restore.sh', 'bin/dev-up.sh',
                    'bin/dev-down.sh', 'bin/pin-images.sh', 'bin/pin_images.py'):
            self.assertTrue((BASE / rel).is_file(), rel)

    def test_scripts_executable(self):
        for rel in ('docker/entrypoint.sh', 'docker/dev-entrypoint.sh', 'bin/docker-up.sh', 'bin/docker-down.sh',
                    'bin/docker-env.sh', 'bin/docker-backup.sh', 'bin/docker-restore.sh', 'bin/dev-up.sh',
                    'bin/dev-down.sh', 'bin/pin-images.sh', 'bin/release.sh'):
            self.assertTrue(os.access(BASE / rel, os.X_OK), rel)

    def test_entrypoint_flags(self):
        text = (BASE / 'docker' / 'entrypoint.sh').read_text()
        self.assertIn('--no-control-socket', text)
        self.assertIn('manage.py seed --first-run-only', text)
        self.assertIn('SEED_ON_START', text)
        self.assertIn('__PROJECT_NAME__.wsgi:application', text)

    def test_compose_wiring(self):
        text = (BASE / 'docker-compose.yml').read_text()
        for needed in ('DB_ENGINE: postgres', 'DJANGO_SERVE_MEDIA', 'DJANGO_CSRF_TRUSTED_ORIGINS',
                       '${APP_PORT:-8889}', '/health/', 'service_healthy'):
            self.assertIn(needed, text)
        self.assertNotIn('5432:5432', text)  # PostgreSQL is not published

    def test_dockerignore_excludes_secrets(self):
        lines = (BASE / '.dockerignore').read_text().split()
        for needed in ('.env', 'db.sqlite3', 'venv/', 'media/', 'staticfiles/', 'verify-shots/', '.git/', 'backups/'):
            self.assertIn(needed, lines)


class ServeMediaTests(SimpleTestCase):
    EXPR = ("(__import__('django').setup(), [str(p.pattern) for p in "
            "__import__('django.urls', fromlist=['x']).get_resolver().url_patterns])[1]")

    def test_flag_adds_media_route_when_debug_off(self):
        on = settings_in_subprocess({'DJANGO_SERVE_MEDIA': '1'}, self.EXPR)
        off = settings_in_subprocess({}, self.EXPR)
        self.assertIn('^media/(?P<path>.*)$', on)
        self.assertNotIn('^media/(?P<path>.*)$', off)
        self.assertEqual(on[-1], '')  # the cms.urls include stays last


class CacheSwitchTests(SimpleTestCase):
    EXPR = "s.CACHES['default']"

    def test_sqlite_default_is_locmem(self):
        c = settings_in_subprocess({}, self.EXPR)
        self.assertEqual(c['BACKEND'], 'django.core.cache.backends.locmem.LocMemCache')

    def test_postgres_default_is_shared_database_cache(self):
        c = settings_in_subprocess({'DB_ENGINE': 'postgres'}, self.EXPR)
        self.assertEqual(c, {'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
                             'LOCATION': 'django_cache'})

    def test_explicit_override_both_ways(self):
        c = settings_in_subprocess({'DB_ENGINE': 'postgres', 'DJANGO_CACHE': 'locmem'}, self.EXPR)
        self.assertIn('locmem', c['BACKEND'])
        c = settings_in_subprocess({'DJANGO_CACHE': 'db'}, self.EXPR)
        self.assertIn('db.DatabaseCache', c['BACKEND'])

    def test_bad_value_refused(self):
        with self.assertRaises(subprocess.CalledProcessError):
            settings_in_subprocess({'DJANGO_CACHE': 'redis'}, self.EXPR)

    @docker_only
    def test_entrypoint_creates_cache_table_before_gunicorn(self):
        text = (BASE / 'docker' / 'entrypoint.sh').read_text()
        self.assertIn('manage.py createcachetable', text)
        self.assertLess(text.index('createcachetable'), text.index('exec gunicorn'))

    @docker_only
    def test_dev_entrypoint_creates_cache_table(self):
        self.assertIn('createcachetable', (BASE / 'docker' / 'dev-entrypoint.sh').read_text())


class CmsCacheInDebugTests(SimpleTestCase):
    EXPR = "[getattr(s, 'CMS_PAGE_CACHE', True), getattr(s, 'CMS_PLACEHOLDER_CACHE', True), getattr(s, 'CMS_PLUGIN_CACHE', True)]"

    def test_caches_are_on_in_production_and_off_in_debug(self):
        self.assertEqual(settings_in_subprocess({'DJANGO_DEBUG': '0'}, self.EXPR), [True, True, True])
        self.assertEqual(settings_in_subprocess({'DJANGO_DEBUG': '1'}, self.EXPR), [False, False, False])
        self.assertEqual(settings_in_subprocess({'DJANGO_DEBUG': '1', 'DJANGO_CMS_CACHE': '1'}, self.EXPR), [True, True, True])


class ProxySecurityTests(SimpleTestCase):
    EXPR = ("{'lang': s.LANGUAGE_COOKIE_SECURE, 'sess': s.SESSION_COOKIE_SECURE, 'csrf': s.CSRF_COOKIE_SECURE, 'hsts': s.SECURE_HSTS_SECONDS,"
            " 'redir': s.SECURE_SSL_REDIRECT, 'hdr': s.SECURE_PROXY_SSL_HEADER, 'exempt': s.SECURE_REDIRECT_EXEMPT}")

    def test_lan_http_keeps_plain_cookies(self):
        r = settings_in_subprocess({}, "{'sess': s.SESSION_COOKIE_SECURE, 'csrf': s.CSRF_COOKIE_SECURE, "
                                       "'hsts': s.SECURE_HSTS_SECONDS, 'redir': s.SECURE_SSL_REDIRECT, 'hdr': s.SECURE_PROXY_SSL_HEADER}")
        self.assertEqual((r['sess'], r['csrf'], r['hsts'], r['redir'], r['hdr']), (False, False, 0, False, None))

    def test_proxy_makes_cookies_secure(self):
        r = settings_in_subprocess({'DJANGO_BEHIND_PROXY': '1'}, self.EXPR)
        self.assertTrue(r['sess'] and r['csrf'] and r['lang'])
        self.assertEqual(r['hsts'], 0)
        self.assertFalse(r['redir'])
        self.assertEqual(r['hdr'], ['HTTP_X_FORWARDED_PROTO', 'https'])

    def test_hsts_and_redirect_opt_in_and_health_exempt(self):
        r = settings_in_subprocess({'DJANGO_BEHIND_PROXY': '1', 'DJANGO_HSTS_SECONDS': '3600',
                                    'DJANGO_SSL_REDIRECT': '1'}, self.EXPR)
        self.assertEqual(r['hsts'], 3600)
        self.assertTrue(r['redir'])
        self.assertEqual(r['exempt'], ['^health/$'])

    def test_hsts_include_subdomains_opt_in(self):
        expr = "s.SECURE_HSTS_INCLUDE_SUBDOMAINS"
        self.assertFalse(settings_in_subprocess({'DJANGO_BEHIND_PROXY': '1'}, expr))
        self.assertTrue(settings_in_subprocess({'DJANGO_BEHIND_PROXY': '1', 'DJANGO_HSTS_INCLUDE_SUBDOMAINS': '1'}, expr))

    def test_hsts_ignored_without_proxy(self):
        r = settings_in_subprocess({'DJANGO_HSTS_SECONDS': '3600'}, "s.SECURE_HSTS_SECONDS")
        self.assertEqual(r, 0)


class HealthRedirectExemptTests(TestCase):
    """With the proxy settings and SSL redirect on, /health/ still answers over plain http (the container
    healthcheck talks to gunicorn directly) while other URLs redirect to https. Runs in-process on the test
    database, so it needs no migrated development database."""

    def test_health_is_exempt_from_the_https_redirect(self):
        from django.test import Client
        exempt = settings_in_subprocess({'DJANGO_BEHIND_PROXY': '1', 'DJANGO_SSL_REDIRECT': '1'}, "s.SECURE_REDIRECT_EXEMPT")
        with override_settings(SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=exempt):
            client = Client()  # built after the override: the middleware reads the settings when it is loaded
            self.assertEqual(client.get('/health/').status_code, 200)
            r = client.get('/admin/login/')
            self.assertEqual(r.status_code, 301)
            self.assertTrue(r['Location'].startswith('https://'))


class AllowedHostsTests(SimpleTestCase):
    def test_loopback_is_always_allowed_so_the_healthcheck_passes(self):
        hosts = settings_in_subprocess({'DJANGO_ALLOWED_HOSTS': 'example.org'}, "s.ALLOWED_HOSTS")
        self.assertEqual(hosts, ['example.org', 'localhost', '127.0.0.1'])

    def test_no_duplicates_and_empty_env(self):
        self.assertEqual(settings_in_subprocess({'DJANGO_ALLOWED_HOSTS': 'localhost,a.example'}, "s.ALLOWED_HOSTS"),
                         ['localhost', 'a.example', '127.0.0.1'])
        self.assertEqual(settings_in_subprocess({}, "s.ALLOWED_HOSTS"), ['localhost', '127.0.0.1'])

    def test_env_example_lists_loopback(self):
        ex = (BASE / '.env.example').read_text()
        self.assertIn('DJANGO_ALLOWED_HOSTS=example.org,localhost,127.0.0.1', ex)


@docker_only
class ComposeWiringTests(SimpleTestCase):
    def setUp(self):
        self.compose = (BASE / 'docker-compose.yml').read_text()

    def test_create_versions_passed_to_container(self):
        self.assertIn('CREATE_VERSIONS: ${CREATE_VERSIONS:-0}', self.compose)
        self.assertIn('CREATE_VERSIONS_USER: ${CREATE_VERSIONS_USER:-}', self.compose)

    def test_documented_env_vars_are_passed(self):
        for name in ('DJANGO_BEHIND_PROXY', 'DJANGO_CACHE', 'DJANGO_HSTS_SECONDS', 'DJANGO_HSTS_INCLUDE_SUBDOMAINS',
                     'DJANGO_SSL_REDIRECT', 'SEED_ON_START', 'GUNICORN_WORKERS', 'GOOGLE_MAPS_API_KEY',
                     'DJANGO_PROXY_COUNT', 'DJANGO_LOGIN_FAILURE_LIMIT', 'DJANGO_LOGIN_COOLOFF_MINUTES',
                     'DJANGO_LOGIN_LOCKOUT_BY'):
            self.assertIn(f'{name}: ${{{name}', self.compose)

    def test_env_example_documents_create_versions(self):
        ex = (BASE / '.env.example').read_text()
        self.assertIn('CREATE_VERSIONS', ex)
        self.assertIn('CREATE_VERSIONS_USER', ex)


@docker_only
class DockerEnvScriptTests(SimpleTestCase):
    """bin/docker-env.sh must never leave an .env with empty secrets."""

    def run_script(self, path_dirs):
        bash = shutil.which('bash')
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'bin').mkdir()
            shutil.copy(BASE / 'bin' / 'docker-env.sh', Path(tmp) / 'bin')
            tools = Path(tmp) / 'tools'
            tools.mkdir()
            for name in ('dirname', 'mktemp', 'mv', 'chmod', 'rm', 'tr', 'cut') + path_dirs:
                src = shutil.which(name)
                if src:
                    (tools / name).symlink_to(src)
            res = subprocess.run([bash, 'bin/docker-env.sh'], cwd=tmp, env={'PATH': str(tools)}, capture_output=True, text=True)
            env_file = Path(tmp) / '.env'
            mode = env_file.stat().st_mode & 0o777 if env_file.exists() else None
            return res, (env_file.read_text() if env_file.exists() else None), sorted(p.name for p in Path(tmp).iterdir()), mode

    def test_without_python_and_openssl_it_fails_and_writes_nothing(self):
        res, env, listing, _mode = self.run_script(())
        self.assertEqual(res.returncode, 1)
        self.assertIsNone(env)
        self.assertEqual([n for n in listing if n.startswith('.env')], [])  # no .env and no temp file left behind
        self.assertIn('No .env was written', res.stderr)

    def test_with_python_it_writes_filled_secrets_mode_600(self):
        res, env, _listing, mode = self.run_script(('python3',))
        self.assertEqual(res.returncode, 0, res.stderr)
        values = dict(line.split('=', 1) for line in env.splitlines() if '=' in line)
        self.assertGreaterEqual(len(values['DJANGO_SECRET_KEY']), 50)
        self.assertGreaterEqual(len(values['DB_PASSWORD']), 32)
        self.assertEqual(mode, 0o600)

    @unittest.skipUnless(shutil.which('openssl'), 'openssl not installed')
    def test_openssl_fallback_when_python_is_missing(self):
        res, env, _listing, mode = self.run_script(('openssl',))
        self.assertEqual(res.returncode, 0, res.stderr)
        values = dict(line.split('=', 1) for line in env.splitlines() if '=' in line)
        self.assertGreaterEqual(len(values['DJANGO_SECRET_KEY']), 50)
        self.assertGreaterEqual(len(values['DB_PASSWORD']), 32)
        self.assertEqual(mode, 0o600)

    def test_existing_env_is_never_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'bin').mkdir()
            shutil.copy(BASE / 'bin' / 'docker-env.sh', Path(tmp) / 'bin')
            (Path(tmp) / '.env').write_text('KEEP=1\n')
            subprocess.run(['bash', 'bin/docker-env.sh'], cwd=tmp, check=True, capture_output=True)
            self.assertEqual((Path(tmp) / '.env').read_text(), 'KEEP=1\n')


class PrivateMediaTests(SimpleTestCase):
    def test_filer_private_storage_is_inside_media_root(self):
        # the EFFECTIVE filer settings (filer ignores a user entry that lacks ENGINE), not just ours
        expr = ("(__import__('django').setup(), [str(s.MEDIA_ROOT), __import__('filer.settings', fromlist=['x']).FILER_STORAGES['private']['main']['OPTIONS']['location'], "
                "__import__('filer.settings', fromlist=['x']).FILER_STORAGES['private']['thumbnails']['OPTIONS']['location']])[1]")
        media, main, thumbs = settings_in_subprocess({}, expr)
        self.assertTrue(main.startswith(media + '/'), main)
        self.assertTrue(thumbs.startswith(media + '/'), thumbs)

    def test_media_view_refuses_private_paths(self):
        from django.http import Http404
        from django.test import RequestFactory

        from __PROJECT_NAME__.urls import serve_media
        with self.assertRaises(Http404):
            serve_media(RequestFactory().get('/media/filer_private/ab/cd/x.pdf'), 'filer_private/ab/cd/x.pdf')
        with self.assertRaises(Http404):
            serve_media(RequestFactory().get('/media/x'), 'filer_private_thumbnails/x.png')


class DevPackagesTests(SimpleTestCase):
    def test_debug_toolbar_is_a_dev_only_requirement(self):
        prod = (BASE / 'requirements.txt').read_text()
        dev = (BASE / 'requirements-dev.txt').read_text()
        self.assertNotIn('debug-toolbar', prod)
        self.assertIn('django-debug-toolbar==', dev)
        self.assertIn('-r requirements.txt', dev)
        self.assertIn('docutils==', prod)  # /admin/docs/ is enabled in production, so docutils is a production dependency

    def test_debug_run_without_the_toolbar_package_does_not_fail(self):
        expr = "[s.USE_DEBUG_TOOLBAR, 'debug_toolbar' in s.INSTALLED_APPS, any('debug_toolbar' in m for m in s.MIDDLEWARE)]"
        code = ("import sys; sys.modules['debug_toolbar'] = None; "  # simulates the package not being installed
                "import django; django.setup(); from django.conf import settings as s; import json; print(json.dumps(" + expr + "))")
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DB_', 'DJANGO_'))}
        env.update({'DJANGO_SECRET_KEY': 'x', 'DJANGO_DEBUG': '1', 'DJANGO_SETTINGS_MODULE': '__PROJECT_NAME__.settings'})
        out = subprocess.run([sys.executable, '-c', code], env=env, cwd=BASE, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout.strip().splitlines()[-1]), [False, False, False])
        code2 = "import sys; sys.modules['debug_toolbar'] = None; import django; django.setup(); import __PROJECT_NAME__.urls"
        out = subprocess.run([sys.executable, '-c', code2], env=env, cwd=BASE, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)


class GoogleMapFailSafeTests(SimpleTestCase):
    EXPR = "(s.CMS_PLACEHOLDER_CONF.get(None) or {}).get('excluded_plugins', [])"

    def test_map_plugins_are_not_offered_without_an_api_key(self):
        self.assertEqual(settings_in_subprocess({}, self.EXPR),
                         ['GoogleMapPlugin', 'GoogleMapMarkerPlugin', 'GoogleMapRoutePlugin'])

    def test_map_plugins_are_offered_with_an_api_key(self):
        self.assertEqual(settings_in_subprocess({'GOOGLE_MAPS_API_KEY': 'k'}, self.EXPR), [])

    def test_exclusion_really_hides_the_plugins_from_the_editor_plugin_list(self):
        expr = ("(__import__('django').setup(), [p.__name__ for p in __import__('cms.plugin_pool', fromlist=['x'])"
                ".plugin_pool.get_all_plugins('content', page=None, root_plugin=True) if p.__name__.startswith('GoogleMap')])[1]")
        self.assertEqual(settings_in_subprocess({}, expr), [])
        self.assertEqual(settings_in_subprocess({'GOOGLE_MAPS_API_KEY': 'k'}, expr), ['GoogleMapPlugin'])

    def test_existing_map_renders_a_notice_not_google_scripts_without_a_key(self):
        from django.template.loader import render_to_string
        html = render_to_string('djangocms_googlemap/default/map.html',
                                {'googlemap_key': '', 'instance': type('I', (), {'title': 'Find us'})()})
        self.assertIn('Map not available', html)
        self.assertIn('Find us', html)
        self.assertNotIn('maps.googleapis.com', html)

    def test_guard_script_is_shipped_and_loads_the_plugin_only_after_google(self):
        js = (BASE / 'static' / 'js' / 'googlemap-guard.js').read_text()
        self.assertIn('site_gmap_ready', js)
        self.assertIn('gm_authFailure', js)
        tpl = (BASE / 'templates' / 'djangocms_googlemap' / 'default' / 'map.html').read_text()
        self.assertIn('js/googlemap-guard.js', tpl)
        self.assertIn('callback=site_gmap_ready', tpl)

    def test_video_embed_keeps_a_text_link(self):
        from django.template.loader import render_to_string
        inst = type('I', (), {'embed_link': 'https://example.org/embed/x', 'embed_link_with_parameters': 'https://example.org/embed/x',
                              'attributes_str': '', 'label': 'Intro', 'child_plugin_instances': []})()
        html = render_to_string('djangocms_video/default/video_player.html', {'instance': inst})
        self.assertIn('site-video-fallback', html)
        self.assertIn('Intro', html)
