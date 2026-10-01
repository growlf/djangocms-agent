# Default site template (Bootstrap 5.3, django CMS 5.1)

A complete, copyable DjangoCMS 5 site: landing and standard page templates, a Bootstrap navbar with a
working hamburger and dropdowns, light/dark mode, a seeded "Style & Capabilities" page that renders every
verified plugin, and idempotent seed commands that publish through djangocms-versioning.
It was built and verified in a scratch project (django-cms 5.1.3, Django 5.2.17) and ported here.

## Placeholders

`bin/new-site.py` (see `references/new-site.md`) is that scaffold: it copies this directory into a new project and substitutes two tokens:

| Token | Meaning | Where |
|---|---|---|
| `__PROJECT_NAME__` | Python package with `settings.py`/`urls.py`; also the name of the `__PROJECT_NAME__/` directory | `settings_fragment.py`, `manage.py`, `__PROJECT_NAME__/` |
| `__SITE_NAME__` | Human-readable name shown in navbar, title and footer | `settings_fragment.py` (`SITE_NAME`) |

## Layout

| Path | Copy to | Notes |
|---|---|---|
| `templates/` | `templates/` | `base.html` (shell), `landing.html`, `standard.html`, `menu/menu.html`, `menu/footer_menu.html` |
| `static/` | `static/` | `css/site.css`, `js/theme.js`, vendored `vendor/bootstrap/` (5.3.3 CSS + bundle JS, MIT `LICENSE` included; no CDN) |
| `starter/` | `starter/` | app: `HtmlBlock` plugin, `seeding.py` helpers, `seed_pages`, `seed_site`, tests |
| `__PROJECT_NAME__/context_processors.py` | `<project>/context_processors.py` | exposes `SITE_NAME` as `site_name` |
| `settings_fragment.py` | `<project>/settings.py` | the complete settings module (or merge sections) |
| `urls_fragment.py` | `<project>/urls.py` | admindocs, admin, debug toolbar (DEBUG only), cms.urls last |
| `manage.py` | `manage.py` | standard, points at `__PROJECT_NAME__.settings` |
| `requirements.txt` | `requirements.txt` | pinned, verified set |
| `env.example.template`, `gitignore.template` | `.env.example`, `.gitignore` | environment variables; ignore rules |

`wsgi.py`, `asgi.py` and `__init__.py` for the project package are the unmodified `django-admin startproject` output (`WSGI_APPLICATION` refers to `wsgi.py`); the scaffold must create them.

`settings_fragment.py` and `urls_fragment.py` are named so they are not mistaken for importable modules of
this repo; they are plain Python and compile as-is.

## Running the result

    pip install -r requirements.txt
    python manage.py migrate
    python manage.py createsuperuser
    DJANGO_DEBUG=1 python manage.py seed_pages     # Home (landing template), set as homepage
    DJANGO_DEBUG=1 python manage.py seed_site      # landing content, About, Style & Capabilities
    DJANGO_DEBUG=1 DJANGO_SECRET_KEY=dev python manage.py runserver 8005
    DJANGO_DEBUG=1 DJANGO_SECRET_KEY=dev python manage.py test starter

`seed_site --reset` clears and refills the placeholders that command owns.

## Seed command rules

- Idempotent: pages are looked up by `PageUrl(slug, language)`, never by title; placeholders are only
  filled when empty.
- Atomic: each page's create / plugin / homepage work is one `transaction.atomic()`.
- Versioning: `create_page` makes a DRAFT, so `starter/seeding.py` works through
  `PageContent.admin_manager` (the default manager only sees published content) and publishes with a
  real user object (`get_user()`; the string `"python-api"` cannot publish, so an inactive system user
  is created when no superuser exists).
- Content created before djangocms-versioning was installed has no `Version` rows and renders as
  missing. Either rely on `publish()` (it creates the Version), or run once:
  `python manage.py create_versions --state published --username <superuser>`.
- Language is `LANG = "en"` in `starter/seeding.py`; it must match `LANGUAGES`.

## HtmlBlock plugin: trusted editors only

`starter.HtmlBlock` ("Raw HTML block (trusted)") renders its `html` field with `|safe`. djangocms-text
sanitises its HTML (strips forms and `data-*` attributes), so Bootstrap components that need them go
through this plugin. Anyone allowed to add it can inject arbitrary HTML and script into every visitor's
browser (stored XSS by design). Grant it only to editors you trust as much as developers; restrict it
with `CMS_PLACEHOLDER_CONF[...]['plugins']` allow-lists or Django permissions if untrusted users can edit.

## Known upstream limits (do not try to fix in the project)

- `makemigrations --check` reports pending changes inside the installed `djangocms_bootstrap5.contrib.*`
  packages; fixing it would mean editing site-packages. `makemigrations --check starter` is clean.
- Plugins created through `add_plugin` get no default CSS classes (only the admin form adds them), so
  `seed_site` passes explicit `attributes` classes.
- Google Map needs `GOOGLE_MAPS_API_KEY` (and internet); the seed adds the sample map only when it is set.
- Video embeds need internet access to show their player.
- `references/plugins.md` lists which plugin packages work and which fail on this stack.
