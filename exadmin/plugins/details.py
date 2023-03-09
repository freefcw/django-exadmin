

from django.utils.translation import ugettext as _
from django.core.urlresolvers import reverse
from django.db import models

from exadmin.sites import site
from exadmin.views import BaseAdminPlugin, ListAdminView

class DetailsPlugin(BaseAdminPlugin):

    show_detail_fields = []
    show_all_rel_details = True

    def result_item(self, item, obj, field_name, row):
        if hasattr(item.field, 'rel') and isinstance(item.field.rel, models.ManyToOneRel) \
                and (self.show_all_rel_details or (field_name in self.show_detail_fields)):
            if rel_obj := getattr(obj, field_name):
                opts = rel_obj._meta
                if item_res_uri := reverse(
                    f'{self.admin_site.app_name}:{opts.app_label}_{opts.module_name}_detail',
                    args=(getattr(rel_obj, opts.pk.attname),),
                ):
                    edit_url = reverse(
                        f'{self.admin_site.app_name}:{opts.app_label}_{opts.module_name}_change',
                        args=(getattr(rel_obj, opts.pk.attname),),
                    )
                    item.btns.append(
                        f"""<a data-res-uri="{item_res_uri}" data-edit-uri="{edit_url}" class="details-handler" rel="tooltip" title="{_(f'Details of {str(rel_obj)}')}"><i class="icon-info-sign"></i></a>"""
                    )
        return item

    # Media
    def get_media(self, media):
        if self.show_all_rel_details or self.show_detail_fields:
            media.add_js([self.static('exadmin/js/details.js')])
            media.add_css({'screen': [self.static('exadmin/css/bootstrap-modal.css'), self.static('exadmin/css/form.css')]})
        return media

site.register_plugin(DetailsPlugin, ListAdminView)


