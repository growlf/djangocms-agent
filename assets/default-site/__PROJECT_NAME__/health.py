"""Health endpoint for container healthchecks: GET /health/.

Does not touch the CMS. Runs one trivial query (SELECT 1) so a lost database turns the container
unhealthy: 200 {"status": "ok"} or 503 {"status": "error", "detail": "database"}.
"""
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


@never_cache
@require_safe
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        return JsonResponse({'status': 'error', 'detail': 'database'}, status=503)
    return JsonResponse({'status': 'ok'})
