from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool

from .models import HtmlBlock


@plugin_pool.register_plugin
class HtmlBlockPlugin(CMSPluginBase):
    model = HtmlBlock
    name = "Raw HTML block (trusted)"
    module = "Site"
    render_template = "starter/plugins/html_block.html"
    text_enabled = False
