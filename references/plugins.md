### Plugin compatibility on cms 5.1.3 / Django 5.2.17

Built and rendered in a scratch project (the one now shipped as `assets/default-site/`). "Works" means
`manage.py check` and `migrate` pass and the plugin rendered on a seeded page. The pinned set is in
`assets/default-site/requirements.txt`; the matching `INSTALLED_APPS` is in `assets/default-site/settings_fragment.py`.

| Package | Status | Notes |
|---|---|---|
| djangocms-text 1.0.1 | WORKS | The text plugin. Sanitises HTML (nh3): strips forms and `data-*`; allow heading ids with `TEXT_ADDITIONAL_ATTRIBUTES` |
| djangocms-versioning 2.7.1 | WORKS | Draft/publish workflow; see the versioning gotchas in `SKILL.md` |
| djangocms-alias | WORKS | Reusable content |
| djangocms-link | WORKS | |
| djangocms-picture | WORKS | Replaced by the bootstrap5 picture app when that is installed (see below) |
| djangocms-video | WORKS | Embeds need internet access to show a player |
| djangocms-file | WORKS | File and Folder plugins |
| djangocms-style | WORKS | |
| djangocms-googlemap | WORKS | Needs `DJANGOCMS_GOOGLEMAP_API_KEY` (`GOOGLE_MAPS_API_KEY`) and internet; without a key Google overlays an error dialog on the page |
| djangocms-icon | WORKS | Installed as a dependency of bootstrap5 |
| djangocms-bootstrap5 0.1.0 contrib: alerts, badge, card, collapse, content, jumbotron, listgroup, picture, tabs, utilities | WORKS | Add each contrib app to `INSTALLED_APPS` individually |
| djangocms-bootstrap5 base app | check + migrate only | Registers no plugins by itself |
| `bootstrap5_grid` | FAILS | Imports `ungettext`, removed from Django |
| `bootstrap5_link` | FAILS | Needs `djangocms_link.forms`, dropped in djangocms-link 5.x |
| `bootstrap5_carousel` | FAILS | Model fields disagree with its migrations; needs the legacy text-ckeditor |
| djangocms-form | FAILS | Not on PyPI (the name does not exist) |
| djangocms-social 0.4a1 | FAILS | Imports `ugettext_lazy`; crashes Django 5.2. Do not use |
| djangocms-text-ckeditor | DO NOT ENABLE | Only installed because bootstrap5 imports its HTMLField. Keep it OUT of `INSTALLED_APPS`; djangocms-text is its successor |
| djangocms-markdown 1.0.1 | check + migrate only | `bin/package-trial.py`, 2026-10-01 (cms 5.1.3, Django 5.2.17): installs (pulls in `markdown` 3.11), imports, `check` and `migrate` pass, no migration drift, registers `MDTextPlugin`. Not rendered or verified in the CMS |
| djangocms-blog 2.0.10 | FAILS | `bin/package-trial.py`, 2026-10-01: pip cannot install it next to django-cms 5.1.3 (requires `django-cms<4.0`, classifiers stop at Django 4.2, needs legacy text-ckeditor). No CMS 5 compatible alternative has been trialed yet |
| djangocms-snippet | UNSUITABLE | Versioned grouper model; does not fit the versioning workflow |

Without the Grid plugin there is no row/column plugin. Use the Bootstrap grid classes in the page templates (as the default site does) or the Raw HTML block (`starter.HtmlBlock`, trusted editors only).

Behaviours to know about djangocms-bootstrap5 0.1.0 (the only release):
- Its picture app replaces the stock `PicturePlugin` with a subclass (`Bootstrap5PicturePlugin`), so that is the plugin editors get.
- Plugins created through `add_plugin` get no default CSS classes (only the admin form adds them). Pass explicit `attributes={"class": "..."}` in seed code.
- Badge and Jumbotron are Bootstrap 4 relics (Jumbotron no longer exists in Bootstrap 5). The default site's `site.css` supplies a small `.jumbotron` rule.
- Every bootstrap5 contrib app shows migration drift in `manage.py makemigrations --check`. That cannot be fixed without editing site-packages (new migrations would be written there), so do not try. Check your own apps instead: `makemigrations --check <app>`.

Transitive pins the site needed: djangocms-attributes-field, django-filer, django-polymorphic, django-mptt, easy-thumbnails, pillow, lxml, nh3, django-fsm-2 (and docutils for admindocs, django-debug-toolbar for development).

Installing the packages above also installs the legacy `djangocms-text-ckeditor`. Never add `djangocms_text_ckeditor` to `INSTALLED_APPS` next to `djangocms_text`.

Previously proven on cms 5.1.3 by TheNetYeti's own sites: djangocms-text, djangocms-link, djangocms-versioning, django-filer. Not re-verified here: any plugin not listed in the table.

Looking for a package that is not in this table? See `references/django-packages.md` (search Django Packages, evaluation checklist, trial, and how to record a new row here).
