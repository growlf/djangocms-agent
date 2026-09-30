# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.5.0 - 2026-09-30

### Fixed
- Removed duplicate sections from djangocms-agent SKILL.md (deduplicated ~160 lines)
- Removed invalid settings: `CMS_TOOLBAR_ANONYMOUS_EDIT`, `CMS_TOOLBAR_REQUIRE_SUPERUSER`, `CMS_TOOLBAR_URL__EDIT_ON`, `CMS_TOOLBAR_URL__EDITMODE`
- Removed non-existent setting `CMS_DEFAULT_INTENT` from all docs
- Corrected `{% show_menu %}` guidance to use `cms.context_processors.cms_settings` (not `menus.context_processors.menus`)
- Aligned references and adapters with django-cms 5.x (replaced all 4.x references)
- Replaced `djangocms-text-ckeditor` with `djangocms-text` (correct package for CMS 5.x)
- Removed references to 8 sub-skills that do not exist
- Gated debug toolbar configuration on `DEBUG` flag; removed unsafe "Safe for production" claim

### Verification status
- Proven: nothing yet by render test
- Unverified: menu template, optional plugins, versioning publish API (see improvements.md F12)
