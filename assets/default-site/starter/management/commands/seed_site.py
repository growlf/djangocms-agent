"""Seed the default site: landing page content, About and Style & Capabilities pages.

Idempotent (pages keyed on PageUrl slug+language), atomic per page, and everything is published
(djangocms-versioning). Requires seed_pages first; run order: seed_pages, seed_site.
"""
import io

from cms.api import add_plugin
from cms.models import CMSPlugin
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from filer.models import File as FilerFile
from filer.models import Folder, Image
from PIL import Image as PILImage
from PIL import ImageDraw

from starter.constants import CONTENT_SLOT
from starter.seeding import LANG, admin_content, ensure_page, get_user, page_for, placeholder, publish

TEXT = "TextPlugin"
HTML = "HtmlBlockPlugin"


def text(body):
    return (TEXT, {"body": body})


def html(markup):
    return (HTML, {"html": markup})


# --------------------------------------------------------------------------- landing page

def landing_specs(style_pk, about_pk):
    btn = lambda label, cls, pk: ("LinkPlugin", {"name": label, "link": {"internal_link": f"cms.page:{pk}"}, "attributes": {"class": cls}})
    return {
        "hero": [
            text("<h1>A DjangoCMS 5 site, ready to edit</h1>"
                 "<p class=\"lead\">Landing and standard templates on Bootstrap 5.3, a working mobile menu, light and dark mode, "
                 "and every installed plugin on one page. Everything you see here is editable in the CMS.</p>"),
            btn("Explore the style guide", "btn btn-light btn-lg", style_pk),
            btn("About this site", "btn btn-outline-light btn-lg", about_pk),
        ],
        "feature_1": [text("<h3>Bootstrap 5 layout</h3><p>Responsive grid, navbar with dropdowns and a hamburger menu, vendored locally so the site works on a LAN with no CDN.</p>")],
        "feature_2": [text("<h3>Light and dark</h3><p>The theme follows your operating system through <code>prefers-color-scheme</code>, using CSS custom properties layered on Bootstrap.</p>")],
        "feature_3": [text("<h3>Draft and publish</h3><p>djangocms-versioning gives every page a draft, a publish step and a history, so editing never breaks the live site.</p>")],
        CONTENT_SLOT: [
            text("<h2>Sample content</h2>"
                 "<p>This section is the <code>content</code> placeholder of the landing template. Add text, images, cards or any other plugin here "
                 "from the CMS toolbar (edit mode, then Structure).</p>"
                 "<ul><li>Hero, three feature columns, this section and a call-to-action band are separate placeholders.</li>"
                 "<li>The footer and navigation are shared by every template.</li>"
                 "<li>Every page in the tree appears in the menu automatically.</li></ul>"),
        ],
        "cta": [
            text("<h2>Ready to look around?</h2><p>The Style &amp; Capabilities page shows every component this site supports.</p>"),
            btn("Open the style guide", "btn btn-light btn-lg", style_pk),
        ],
    }


# --------------------------------------------------------------------------- about

ABOUT = [
    text("<h1>About</h1>"
         "<p>This is the default DjangoCMS 5 site. Replace this text with your own: it is a normal, editable page.</p>"
         "<h2>What is here</h2>"
         "<ul><li>A <strong>landing template</strong> with a hero, feature columns and a call-to-action band.</li>"
         "<li>A <strong>standard template</strong> with a right-hand sidebar that stacks under the content on small screens.</li>"
         "<li>A <strong>Style &amp; Capabilities</strong> page that shows every component and plugin the site supports.</li></ul>"
         "<h2>How it is built</h2>"
         "<p>DjangoCMS 5.1 on Django 5.2, Bootstrap 5.3 served from <code>static/vendor/bootstrap</code>, and the "
         "<code>--site-*</code> CSS custom properties for colour, spacing and type.</p>"),
]
ABOUT_SIDEBAR = [text("<h3>Quick links</h3><ul><li><a href=\"/style-and-capabilities/\">Style &amp; Capabilities</a></li></ul>")]

# --------------------------------------------------------------------------- style guide (raw Bootstrap components)

BUTTONS = """<h2 id="buttons">Buttons</h2>
<p class="d-flex flex-wrap gap-2">
<button type="button" class="btn btn-primary">Primary</button>
<button type="button" class="btn btn-secondary">Secondary</button>
<button type="button" class="btn btn-success">Success</button>
<button type="button" class="btn btn-danger">Danger</button>
<button type="button" class="btn btn-outline-primary">Outline</button>
<button type="button" class="btn btn-link">Link</button>
<button type="button" class="btn btn-primary" disabled>Disabled</button></p>"""

ALERTS = """<h2 id="alerts">Alerts</h2>
<div class="alert alert-success" role="alert">Success: the operation completed.</div>
<div class="alert alert-warning" role="alert">Warning: check this before continuing.</div>
<div class="alert alert-danger alert-dismissible fade show" role="alert">Danger: something failed. This one can be dismissed.
<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button></div>"""

CARDS = """<h2 id="cards">Cards</h2>
<div class="row g-3">
<div class="col-md-6"><div class="card h-100"><div class="card-body"><h3 class="h5 card-title">Card title</h3>
<p class="card-text">Cards hold a header, body and actions, and adapt to light and dark mode.</p><a href="#cards" class="btn btn-primary">Go somewhere</a></div></div></div>
<div class="col-md-6"><div class="card h-100"><div class="card-header">Featured</div><ul class="list-group list-group-flush">
<li class="list-group-item">First item</li><li class="list-group-item">Second item</li><li class="list-group-item">Third item</li></ul></div></div>
</div>"""

FORMS = """<h2 id="forms">Forms</h2>
<form class="row g-3" onsubmit="return false">
<div class="col-md-6"><label for="sg-name" class="form-label">Name</label><input type="text" class="form-control" id="sg-name" autocomplete="off"></div>
<div class="col-md-6"><label for="sg-email" class="form-label">Email</label><input type="email" class="form-control" id="sg-email" autocomplete="off"></div>
<div class="col-md-6"><label for="sg-select" class="form-label">Choice</label><select id="sg-select" class="form-select"><option>One</option><option>Two</option></select></div>
<div class="col-md-6"><label for="sg-range" class="form-label">Range</label><input type="range" class="form-range" id="sg-range"></div>
<div class="col-12"><label for="sg-msg" class="form-label">Message</label><textarea class="form-control" id="sg-msg" rows="3"></textarea></div>
<div class="col-12"><div class="form-check"><input class="form-check-input" type="checkbox" id="sg-check"><label class="form-check-label" for="sg-check">Remember me</label></div></div>
<div class="col-12"><button type="submit" class="btn btn-primary">Submit (demo only)</button></div>
</form>"""

ACCORDION = """<h2 id="accordion">Accordion</h2>
<div class="accordion" id="sg-accordion">
<div class="accordion-item"><h3 class="accordion-header"><button class="accordion-button" type="button" data-bs-toggle="collapse" data-bs-target="#sg-a1" aria-expanded="true" aria-controls="sg-a1">First section</button></h3>
<div id="sg-a1" class="accordion-collapse collapse show" data-bs-parent="#sg-accordion"><div class="accordion-body">Open by default. Only one section is open at a time.</div></div></div>
<div class="accordion-item"><h3 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#sg-a2" aria-expanded="false" aria-controls="sg-a2">Second section</button></h3>
<div id="sg-a2" class="accordion-collapse collapse" data-bs-parent="#sg-accordion"><div class="accordion-body">Keyboard accessible: focus a header and press Enter or Space.</div></div></div>
</div>"""

TYPOGRAPHY = """<h1>Style &amp; Capabilities</h1>
<p class="lead">A reference of the building blocks this site offers: plain HTML, Bootstrap components, and every installed plugin.</p>
<h2 id="typography">Typography</h2>
<h2>Heading 2</h2><h3>Heading 3</h3><h4>Heading 4</h4>
<p>Body text uses the system font stack. <strong>Bold</strong>, <em>emphasis</em>, <a href="#typography">a link</a> and <code>inline code</code> all inherit the theme colours.</p>
<blockquote><p>Blockquotes carry a muted colour and a left rule.</p></blockquote>
<h3>Lists</h3>
<ul><li>Unordered item</li><li>Another item<ul><li>Nested item</li></ul></li></ul>
<ol><li>First</li><li>Second</li></ol>
<h3>Table</h3>
<table><thead><tr><th>Plugin</th><th>Package</th><th>Status</th></tr></thead>
<tbody><tr><td>Text</td><td>djangocms-text</td><td>installed</td></tr><tr><td>Link</td><td>djangocms-link</td><td>installed</td></tr>
<tr><td>Picture</td><td>djangocms-picture</td><td>installed</td></tr></tbody></table>
<h3>Code</h3>
<pre><code>def hello(name):
    return f"Hello, {name}!"</code></pre>"""

STYLE_SIDEBAR = ("<h3>On this page</h3><ul>"
                 "<li><a href=\"#typography\">Typography</a></li><li><a href=\"#buttons\">Buttons</a></li>"
                 "<li><a href=\"#alerts\">Alerts</a></li><li><a href=\"#cards\">Cards</a></li><li><a href=\"#forms\">Forms</a></li>"
                 "<li><a href=\"#accordion\">Accordion</a></li><li><a href=\"#bootstrap5\">Bootstrap 5 plugins</a></li>"
                 "<li><a href=\"#plugins\">Content plugins</a></li></ul>")


def sample_image(user):
    """A generated PNG in filer (idempotent by original filename)."""
    img = Image.objects.filter(original_filename="style-sample.png").first()
    if img is None:
        pil = PILImage.new("RGB", (1200, 600), "#1d4ed8")
        d = ImageDraw.Draw(pil)
        for i in range(0, 1200, 60):
            d.line([(i, 0), (i + 300, 600)], fill="#3b82f6", width=18)
        d.text((40, 40), "Sample image (generated)", fill="#ffffff")
        buf = io.BytesIO()
        pil.save(buf, "PNG")
        img = Image.objects.create(file=ContentFile(buf.getvalue(), name="style-sample.png"),
                                   original_filename="style-sample.png", name="Style sample", owner=user,
                                   default_alt_text="Blue diagonal stripes, a generated sample image")
    return img


def sample_folder(user):
    folder, _ = Folder.objects.get_or_create(name="Sample downloads", defaults={"owner": user})
    for fname, body in [("readme.txt", b"Sample download.\n"), ("notes.txt", b"More notes.\n")]:
        if not FilerFile.objects.filter(folder=folder, original_filename=fname).exists():
            FilerFile.objects.create(file=ContentFile(body, name=fname), original_filename=fname,
                                     name=fname, folder=folder, owner=user)
    return folder


def sample_alias(user):
    """A reusable alias with one text plugin, published. Returns the Alias."""
    from djangocms_alias.models import Alias, AliasContent, Category
    existing = AliasContent.admin_manager.latest_content(name="Site notice", language=LANG).first()
    if existing is not None:
        return existing.alias
    category = Category.objects.filter(translations__name="Site").first() or Category.objects.create(name="Site")
    alias = Alias.objects.create(category=category)
    content = AliasContent.objects.with_user(user).create(alias=alias, name="Site notice", language=LANG)
    add_plugin(content.placeholder, TEXT, LANG,
               body="<p><strong>Alias content:</strong> this notice is a reusable alias; edit it once and every page that uses it updates.</p>")
    content.versions.first().publish(user)
    return alias


def bootstrap5_specs():
    """(plugin_type, data, [children]) tree for the Bootstrap 5 plugin section."""
    return [
        ("Bootstrap5AlertsPlugin", {"alert_context": "info"}, [(TEXT, {"body": "<p>Bootstrap 5 <strong>Alerts</strong> plugin.</p>"}, [])]),
        ("Bootstrap5BadgePlugin", {"badge_text": "New", "badge_context": "success", "badge_pills": True, "attributes": {"class": "badge rounded-pill text-bg-success"}}, []),
        ("Bootstrap5BlockquotePlugin", {"quote_content": "Simplicity is prerequisite for reliability.", "quote_origin": "Edsger W. Dijkstra", "attributes": {"class": "blockquote"}}, []),
        ("Bootstrap5CodePlugin", {"code_content": "print('Bootstrap5CodePlugin')"}, []),
        ("Bootstrap5JumbotronPlugin", {"attributes": {"class": "jumbotron"}}, [(TEXT, {"body": "<h3>Jumbotron plugin</h3><p>A large call-out block.</p>"}, [])]),
        ("Bootstrap5ListGroupPlugin", {}, [
            ("Bootstrap5ListGroupItemPlugin", {}, [(TEXT, {"body": "<p>List group item one</p>"}, [])]),
            ("Bootstrap5ListGroupItemPlugin", {"list_context": "success"}, [(TEXT, {"body": "<p>List group item two (success)</p>"}, [])]),
        ]),
        ("Bootstrap5CardPlugin", {}, [
            ("Bootstrap5CardInnerPlugin", {"inner_type": "card-header"}, [(TEXT, {"body": "Card plugin header"}, [])]),
            ("Bootstrap5CardInnerPlugin", {"inner_type": "card-body"}, [(TEXT, {"body": "<p>Card plugin body.</p>"}, [])]),
        ]),
        ("Bootstrap5SpacingPlugin", {"space_property": "p", "space_sides": "", "space_size": "3", "attributes": {"class": "p-3 border rounded"}}, [(TEXT, {"body": "<p>Inside a spacing plugin (padding 3).</p>"}, [])]),
        ("Bootstrap5CollapsePlugin", {"siblings": ".collapse"}, [
            ("Bootstrap5CollapseTriggerPlugin", {"identifier": "sg-collapse", "tag_type": "button", "attributes": {"class": "btn btn-outline-primary mb-2", "type": "button"}},
             [(TEXT, {"body": "Collapse plugin: show or hide details"}, [])]),
            ("Bootstrap5CollapseContainerPlugin", {"identifier": "sg-collapse", "attributes": {"class": "collapse"}},
             [(TEXT, {"body": "<p>Hidden until the trigger above is activated.</p>"}, [])]),
        ]),
        ("Bootstrap5TabPlugin", {"tab_index": 1}, [
            ("Bootstrap5TabItemPlugin", {"tab_title": "First tab"}, [(TEXT, {"body": "<p>First tab content.</p>"}, [])]),
            ("Bootstrap5TabItemPlugin", {"tab_title": "Second tab"}, [(TEXT, {"body": "<p>Second tab content.</p>"}, [])]),
        ]),
    ]


def add_tree(ph, specs, target=None):
    for plugin_type, data, children in specs:
        kwargs = {"target": target} if target is not None else {}
        plugin = add_plugin(ph, plugin_type, LANG, **kwargs, **data)
        add_tree(ph, children, plugin)


def googlemap_specs():
    """Without an API key Google shows an error dialog over the page, so the sample map needs GOOGLE_MAPS_API_KEY."""
    if getattr(settings, "DJANGOCMS_GOOGLEMAP_API_KEY", ""):
        return [(TEXT, {"body": "<h3>Google Map</h3>"}, []),
                ("GoogleMapPlugin", {"title": "Sample map", "lat": 47.6062, "lng": -122.3321, "zoom": 10, "height": "300px"}, [])]
    return [(TEXT, {"body": "<h3>Google Map</h3><p>The djangocms-googlemap plugin is installed. It needs a Google Maps API key and internet access, "
                            "so no sample is placed here until <code>GOOGLE_MAPS_API_KEY</code> is set and <code>seed_site --reset</code> is run.</p>"}, [])]


def style_specs(user, page_pk):
    image = sample_image(user)
    folder = sample_folder(user)
    alias = sample_alias(user)
    plain = lambda t, d: (t, d, [])
    specs = [
        plain(TEXT, {"body": TYPOGRAPHY}),
        plain(HTML, {"html": BUTTONS}), plain(HTML, {"html": ALERTS}), plain(HTML, {"html": CARDS}),
        plain(HTML, {"html": FORMS}), plain(HTML, {"html": ACCORDION}),
        plain(TEXT, {"body": "<h2 id=\"bootstrap5\">Bootstrap 5 plugins</h2><p>Components from djangocms-bootstrap5, added through the CMS structure board.</p>"}),
        *bootstrap5_specs(),
        plain(TEXT, {"body": "<h2 id=\"plugins\">Content plugins</h2><p>Each of these is a separate installed plugin, rendered live.</p><h3>Link</h3>"}),
        plain("LinkPlugin", {"name": "A djangocms-link plugin pointing to the About page", "link": {"internal_link": f"cms.page:{page_pk}"}}),
        plain(TEXT, {"body": "<h3>Picture</h3><p>djangocms-bootstrap5's picture app replaces the stock <code>PicturePlugin</code> with a subclass, so this is the one editors get.</p>"}),
        plain("Bootstrap5PicturePlugin", {"picture": image, "picture_rounded": True, "caption_text": "A djangocms-picture plugin (Bootstrap5PicturePlugin subclass; filer image)."}),
        plain(TEXT, {"body": "<h3>Video</h3><p>An embed needs internet access to show its player; on a LAN-only network the frame stays blank.</p>"}),
        ("VideoPlayerPlugin", {"embed_link": "https://www.youtube-nocookie.com/embed/aqz-KE-bpKQ", "label": "Sample video"}, []),
        plain(TEXT, {"body": "<h3>File and folder</h3>"}),
        plain("FilePlugin", {"file_src": FilerFile.objects.filter(folder=folder).first(), "file_name": "Download the sample file", "show_file_size": True}),
        plain("FolderPlugin", {"folder_src": folder, "show_file_size": True}),
        plain(TEXT, {"body": "<h3>Style</h3>"}),
        ("StylePlugin", {"class_name": "container", "additional_classes": "border rounded p-3 bg-body-tertiary"},
         [(TEXT, {"body": "<p>Content wrapped by a djangocms-style plugin (class <code>container</code> plus utility classes).</p>"}, [])]),
        plain(TEXT, {"body": "<h3>Alias</h3>"}),
        plain("Alias", {"alias": alias}),
        *googlemap_specs(),
        plain(TEXT, {"body": "<h3>Project plugins</h3>"}),
        plain(HTML, {"html": "<p class=\"text-body-secondary\">This paragraph is a Raw HTML block (trusted) plugin.</p>"}),
    ]
    return specs


class Command(BaseCommand):
    help = "Seed the default site: landing content, About, Style & Capabilities (idempotent, atomic, published)"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Clear and refill the placeholders of the pages this command owns (About, Style & Capabilities, Home)")

    def handle(self, *args, reset=False, **kwargs):
        self.reset = reset
        user = get_user()
        home = page_for("home")
        if home is None:
            raise CommandError("Run seed_pages first.")

        with transaction.atomic():
            about, _ = ensure_page("about", "About", "standard.html", user, after=home)
            self._fill(about, {CONTENT_SLOT: [plain_spec(*s) for s in ABOUT], "sidebar": [plain_spec(*s) for s in ABOUT_SIDEBAR]})
            publish(about, user)

        with transaction.atomic():
            style, _ = ensure_page("style-and-capabilities", "Style & Capabilities", "standard.html", user, after=page_for("about"))
            self._fill(style, {CONTENT_SLOT: style_specs(user, about.pk), "sidebar": [plain_spec(TEXT, {"body": STYLE_SIDEBAR})]})
            publish(style, user)

        with transaction.atomic():
            content = admin_content(home)
            if content.template != "landing.html":
                content.template = "landing.html"
                content.save(update_fields=["template"])
            self._fill(home, {slot: [plain_spec(*s) for s in specs] for slot, specs in landing_specs(style.pk, about.pk).items()})
            publish(home, user)

        self.stdout.write("seeded site")

    def _fill(self, page, slots):
        """Fill each empty slot (idempotent; --reset clears first). Specs are (type, data, children) tuples."""
        for slot, specs in slots.items():
            ph = placeholder(page, slot)
            if self.reset:
                ph.clear(LANG)
            if not ph.get_plugins(LANG).exists():
                add_tree(ph, specs)


def plain_spec(plugin_type, data, children=None):
    return (plugin_type, data, children or [])
