"""Login throttling (django-axes): lockout, unlock, client-IP safety, env knobs. Offline; SQLite or PostgreSQL."""
import logging
from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import HttpRequest
from django.test import SimpleTestCase, TestCase, override_settings

from __PROJECT_NAME__.security import client_ip
from .tests_docker import settings_in_subprocess

_axes_log = logging.getLogger('axes')
_axes_level = _axes_log.level


def setUpModule():  # axes logs every failure at WARNING (wanted in production); keep the test output readable
    _axes_log.setLevel(logging.CRITICAL)


def tearDownModule():
    _axes_log.setLevel(_axes_level)


GOOD = 'correct-horse-battery-staple-9'
LOGIN = '/admin/login/'


def attempt(client, password='wrong', username='alice', **extra):
    return client.post(LOGIN, {'username': username, 'password': password, 'next': '/admin/'}, **extra)


class ThrottleBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser('alice', 'alice@example.org', GOOD)
        get_user_model().objects.create_superuser('bob', 'bob@example.org', GOOD)

    def fail_n(self, n, **extra):
        for _ in range(n):
            self.assertEqual(attempt(self.client, **extra).status_code, 200)  # the form again, no lockout yet


class LockoutTests(ThrottleBase):
    def test_defaults(self):
        self.assertTrue(settings.AXES_ENABLED)
        self.assertEqual(settings.AXES_FAILURE_LIMIT, 5)
        self.assertEqual(settings.AXES_COOLOFF_TIME, timedelta(hours=1))
        self.assertEqual(settings.AUTHENTICATION_BACKENDS[0], 'axes.backends.AxesStandaloneBackend')
        self.assertEqual(settings.MIDDLEWARE[-1], 'axes.middleware.AxesMiddleware')

    def test_locks_after_limit_even_for_the_right_password(self):
        self.fail_n(settings.AXES_FAILURE_LIMIT - 1)
        r = attempt(self.client)  # the limit-th failure locks and already answers with the lockout page
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, 'Too many failed login attempts', status_code=429)
        self.assertNotContains(r, 'Traceback', status_code=429)
        self.assertEqual(r['Retry-After'], '3600')
        r = attempt(self.client, password=GOOD)
        self.assertEqual(r.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_below_the_limit_the_right_password_logs_in(self):
        self.fail_n(settings.AXES_FAILURE_LIMIT - 1)
        r = attempt(self.client, password=GOOD)
        self.assertEqual(r.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

    def test_success_resets_the_counter(self):
        self.fail_n(settings.AXES_FAILURE_LIMIT - 1)
        self.assertEqual(attempt(self.client, password=GOOD).status_code, 302)
        self.client.logout()
        self.fail_n(settings.AXES_FAILURE_LIMIT - 1)  # would have locked without the reset

    def test_axes_reset_unlocks(self):
        self.fail_n(settings.AXES_FAILURE_LIMIT - 1)
        attempt(self.client)
        self.assertEqual(attempt(self.client, password=GOOD).status_code, 429)
        call_command('axes_reset', stdout=StringIO())
        self.assertEqual(attempt(self.client, password=GOOD).status_code, 302)

    def test_other_username_is_not_locked(self):
        self.fail_n(settings.AXES_FAILURE_LIMIT - 1)
        attempt(self.client)
        self.assertEqual(attempt(self.client, password=GOOD, username='bob').status_code, 302)

    def test_normal_pages_are_unaffected_while_locked(self):
        self.fail_n(settings.AXES_FAILURE_LIMIT - 1)
        attempt(self.client)
        self.assertEqual(self.client.get('/health/').status_code, 200)
        self.assertEqual(self.client.get(LOGIN).status_code, 200)  # the form itself still loads
        self.assertNotEqual(self.client.get('/').status_code, 429)

    @override_settings(AXES_COOLOFF_TIME=None)
    def test_zero_cooloff_says_ask_the_administrator(self):
        self.fail_n(settings.AXES_FAILURE_LIMIT - 1)
        r = attempt(self.client)
        self.assertContains(r, 'administrator', status_code=429)
        self.assertNotIn('Retry-After', r)

    @override_settings(AXES_ENABLED=False)
    def test_can_be_disabled(self):
        self.fail_n(settings.AXES_FAILURE_LIMIT + 3)
        self.assertEqual(attempt(self.client, password=GOOD).status_code, 302)


class ClientIpTests(ThrottleBase):
    def test_forwarded_for_is_ignored_without_the_proxy_flag(self):
        self.assertFalse(settings.BEHIND_PROXY)
        for i in range(settings.AXES_FAILURE_LIMIT - 1):  # attacker rotates a forged header to dodge the limit
            attempt(self.client, REMOTE_ADDR='198.51.100.7', HTTP_X_FORWARDED_FOR=f'203.0.113.{i}')
        r = attempt(self.client, REMOTE_ADDR='198.51.100.7', HTTP_X_FORWARDED_FOR='203.0.113.99')
        self.assertEqual(r.status_code, 429)

    def test_forged_header_cannot_lock_out_someone_else(self):
        for _ in range(settings.AXES_FAILURE_LIMIT):  # attacker claims to be the victim's address
            attempt(self.client, REMOTE_ADDR='198.51.100.7', HTTP_X_FORWARDED_FOR='192.0.2.55')
        r = attempt(self.client, password=GOOD, REMOTE_ADDR='192.0.2.55')
        self.assertEqual(r.status_code, 302)

    @override_settings(BEHIND_PROXY=True)
    def test_forwarded_for_is_used_behind_a_proxy_from_the_right(self):
        proxy = '10.0.0.2'
        for i in range(settings.AXES_FAILURE_LIMIT - 1):  # forged left entries must not dodge the limit
            attempt(self.client, REMOTE_ADDR=proxy, HTTP_X_FORWARDED_FOR=f'6.6.6.{i}, 203.0.113.9')
        r = attempt(self.client, REMOTE_ADDR=proxy, HTTP_X_FORWARDED_FOR='7.7.7.7, 203.0.113.9')
        self.assertEqual(r.status_code, 429)
        # a different real client behind the same proxy is not locked
        r = attempt(self.client, password=GOOD, REMOTE_ADDR=proxy, HTTP_X_FORWARDED_FOR='6.6.6.0, 203.0.113.10')
        self.assertEqual(r.status_code, 302)

    def req(self, remote='10.0.0.2', xff=None):
        r = HttpRequest()
        r.META['REMOTE_ADDR'] = remote
        if xff is not None:
            r.META['HTTP_X_FORWARDED_FOR'] = xff
        return r

    def test_client_ip_unit(self):
        self.assertEqual(client_ip(self.req(xff='1.2.3.4')), '10.0.0.2')
        with override_settings(BEHIND_PROXY=True):
            self.assertEqual(client_ip(self.req(xff='9.9.9.9, 1.2.3.4')), '1.2.3.4')
            self.assertEqual(client_ip(self.req(xff='1.2.3.4')), '1.2.3.4')
            self.assertEqual(client_ip(self.req()), '10.0.0.2')  # header absent
            self.assertEqual(client_ip(self.req(xff='not-an-ip')), '10.0.0.2')  # malformed
            self.assertEqual(client_ip(self.req(xff='2001:db8::1')), '2001:db8::1')
        with override_settings(BEHIND_PROXY=True, PROXY_COUNT=2):
            self.assertEqual(client_ip(self.req(xff='9.9.9.9, 1.2.3.4, 10.1.1.1')), '1.2.3.4')
            self.assertEqual(client_ip(self.req(xff='10.1.1.1')), '10.0.0.2')  # fewer hops than proxies


class EnvKnobTests(SimpleTestCase):
    def test_limit_zero_disables(self):
        self.assertFalse(settings_in_subprocess({'DJANGO_LOGIN_FAILURE_LIMIT': '0'}, 's.AXES_ENABLED'))

    def test_limit_and_cooloff_from_env(self):
        r = settings_in_subprocess({'DJANGO_LOGIN_FAILURE_LIMIT': '3', 'DJANGO_LOGIN_COOLOFF_MINUTES': '15'},
                                   "[s.AXES_FAILURE_LIMIT, s.AXES_COOLOFF_TIME.total_seconds()]")
        self.assertEqual(r, [3, 900])

    def test_zero_cooloff_means_until_reset(self):
        self.assertIsNone(settings_in_subprocess({'DJANGO_LOGIN_COOLOFF_MINUTES': '0'}, 's.AXES_COOLOFF_TIME'))

    def test_lockout_by_ip(self):
        self.assertEqual(settings_in_subprocess({'DJANGO_LOGIN_LOCKOUT_BY': 'ip'}, 's.AXES_LOCKOUT_PARAMETERS'),
                         ['ip_address'])
        self.assertEqual(settings_in_subprocess({}, 's.AXES_LOCKOUT_PARAMETERS'), [['username', 'ip_address']])

    def test_proxy_flag_and_count(self):
        self.assertEqual(settings_in_subprocess({}, '[s.BEHIND_PROXY, s.PROXY_COUNT]'), [False, 1])
        self.assertEqual(settings_in_subprocess({'DJANGO_BEHIND_PROXY': '1', 'DJANGO_PROXY_COUNT': '2'},
                                                '[s.BEHIND_PROXY, s.PROXY_COUNT]'), [True, 2])

    def test_bad_values_fail_loudly(self):
        for env in ({'DJANGO_LOGIN_FAILURE_LIMIT': 'five'}, {'DJANGO_LOGIN_COOLOFF_MINUTES': '-1'},
                    {'DJANGO_LOGIN_LOCKOUT_BY': 'user'}):
            with self.assertRaises(Exception, msg=env):
                settings_in_subprocess(env, 's.AXES_ENABLED')
