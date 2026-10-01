"""Offline tests for the Docker/PostgreSQL support: DB switch, WhiteNoise, health, media flag, container files."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path

from cms.models import Page
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

BASE = Path(__file__).resolve().parent.parent
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


class ContainerFilesTests(SimpleTestCase):
    def test_container_files_present(self):
        for rel in ('Dockerfile', 'docker-compose.yml', 'docker/entrypoint.sh', '.dockerignore',
                    'bin/docker-up.sh', 'bin/docker-down.sh', 'bin/docker-env.sh'):
            self.assertTrue((BASE / rel).is_file(), rel)

    def test_scripts_executable(self):
        for rel in ('docker/entrypoint.sh', 'bin/docker-up.sh', 'bin/docker-down.sh', 'bin/docker-env.sh'):
            self.assertTrue(os.access(BASE / rel, os.X_OK), rel)

    def test_entrypoint_flags(self):
        text = (BASE / 'docker' / 'entrypoint.sh').read_text()
        self.assertIn('--no-control-socket', text)
        self.assertIn('manage.py seed', text)
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
        for needed in ('.env', 'db.sqlite3', 'venv/', 'media/', 'staticfiles/', 'verify-shots/', '.git/'):
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
