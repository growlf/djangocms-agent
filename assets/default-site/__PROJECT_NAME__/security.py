"""Client IP for login throttling (django-axes).

Axes locks out by username + client IP. The IP must be one the client cannot choose:

* Default (DJANGO_BEHIND_PROXY unset): ``REMOTE_ADDR`` only. A client-sent ``X-Forwarded-For`` is
  IGNORED, so it can neither dodge a lockout nor be used to lock someone else out.
* DJANGO_BEHIND_PROXY=1: the app sits behind your own reverse proxy(ies). ``X-Forwarded-For`` is read
  from the RIGHT: with DJANGO_PROXY_COUNT proxies (default 1) the address your outermost proxy
  appended is used (the entries to its left are client-controlled and are never trusted). A missing,
  too short or malformed header falls back to ``REMOTE_ADDR``. This assumes the proxy APPENDS to (or
  overwrites) X-Forwarded-For, and that nobody can reach the app port except the proxy.
"""
import ipaddress

from django.conf import settings


def _valid(value):
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request):
    remote = request.META.get('REMOTE_ADDR') or ''
    if not getattr(settings, 'BEHIND_PROXY', False):
        return remote
    header = request.META.get('HTTP_X_FORWARDED_FOR', '')
    hops = [h for h in (p.strip() for p in header.split(',')) if h]
    count = max(int(getattr(settings, 'PROXY_COUNT', 1)), 1)
    if len(hops) < count:
        return remote
    return _valid(hops[-count]) or remote


def lockout_response(request, response=None, credentials=None):
    """Friendly 429 page for a locked-out login (AXES_LOCKOUT_CALLABLE); never a stack trace."""
    from django.shortcuts import render

    cool_off = getattr(settings, 'AXES_COOLOFF_TIME', None)
    seconds = int(cool_off.total_seconds()) if cool_off else 0
    resp = render(request, 'axes_lockout.html', {
        'failure_limit': settings.AXES_FAILURE_LIMIT,
        'cooloff_minutes': max(seconds // 60, 1) if seconds else 0,
    }, status=429)
    if seconds:
        resp['Retry-After'] = str(seconds)
    resp['Cache-Control'] = 'no-store'
    return resp
