
import urllib
from django.template import loader
from django.core.cache import cache
from django.utils import simplejson
from django.utils.translation import ugettext as _

from exadmin.sites import site
from exadmin.models import UserSettings
from exadmin.views import BaseAdminPlugin, BaseAdminView
from exadmin.util import static

THEME_CACHE_KEY = 'exadmin_themes'

class ThemePlugin(BaseAdminPlugin):

    enable_themes = True
    # {'name': 'Blank Theme', 'description': '...', 'css': 'http://...', 'thumbnail': '...'}
    user_themes = None
    default_theme = static('exadmin/css/bootstrap-exadmin.css')

    def init_request(self, *args, **kwargs):
        return self.enable_themes

    def _get_theme(self):
        if self.user:
            try:
                return UserSettings.objects.get(user=self.user, key="site-theme").value
            except Exception:
                pass
        return self.default_theme

    def get_context(self, context):
        context['site_theme'] = self._get_theme()
        return context

    # Media
    def get_media(self, media):
        media.add_js([self.static('exadmin/js/themes.js')])
        return media

    # Block Views
    def block_top_nav_btn(self, context, nodes):

        themes = [{'name': _(u"Default"), 'description': _(u"default bootstrap theme"), 'css': self.default_theme}]
        select_css = context.get('site_theme', self.default_theme)

        if self.user_themes:
            themes.extend(self.user_themes)

        if ex_themes := cache.get(THEME_CACHE_KEY):
            themes.extend(simplejson.loads(ex_themes))
        else:
            ex_themes = []
            try:
                watch_themes = simplejson.loads(urllib.urlopen('http://api.bootswatch.com/').read())['themes']
                ex_themes.extend([\
                        {'name': t['name'], 'description': t['description'], 'css': t['css-min'], 'thumbnail': t['thumbnail']} \
                        for t in watch_themes])
            except Exception:
                pass

            cache.set(THEME_CACHE_KEY, simplejson.dumps(ex_themes), 24*3600)
            themes.extend(ex_themes)

        nodes.append(loader.render_to_string('admin/blocks/toptheme.html', {'themes': themes, 'select_css': select_css}))


site.register_plugin(ThemePlugin, BaseAdminView)


