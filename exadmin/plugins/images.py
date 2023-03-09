from django.db import models
from django import forms
from django.utils.translation import ugettext as _
from django.utils.safestring import mark_safe
from exadmin.sites import site
from exadmin.views import BaseAdminPlugin, ModelFormAdminView, DetailAdminView

class AdminImageField(forms.ImageField):
        
    def widget_attrs(self, widget):
        return {'label': self.label}

class AdminImageWidget(forms.FileInput):
    """
    A ImageField Widget that shows its current value if it has one.
    """
    def __init__(self, attrs={}):
        super(AdminImageWidget, self).__init__(attrs)

    def render(self, name, value, attrs=None):
        output = []
        if value and hasattr(value, "url"):
            label=self.attrs.get('label', name)
            output.append(
                f"""<a href="{value.url}" target="_blank" title="{label}" rel="gallery"><img src="{value.url}" class="field_img"/></a><br/>{_('Change:')} """
            )
        output.append(super(AdminImageWidget, self).render(name, value, attrs))
        return mark_safe(u''.join(output))

class ModelDetailPlugin(BaseAdminPlugin):

    def __init__(self, admin_view):
        super(ModelDetailPlugin, self).__init__(admin_view)
        self.include_image = False

    def get_field_attrs(self, attrs, db_field, **kwargs):
        if isinstance(db_field, models.ImageField):
            attrs['widget'] = AdminImageWidget
            attrs['form_class'] = AdminImageField
            self.include_image = True
        return attrs

    def get_field_result(self, result, field_name):
        if isinstance(result.field, models.ImageField) and result.value:
            img = getattr(result.obj, field_name)
            result.text = mark_safe(
                f'<a href="{img.url}" target="_blank" title="{result.label}" rel="gallery"><img src="{img.url}" class="field_img"/></a>'
            )
            self.include_image = True
        return result

    # Media
    def get_media(self, media):
        if self.include_image:
            media.add_js([self.static('exadmin/js/load-image.min.js'), self.static('exadmin/js/bootstrap-image-gallery.min.js')])
            media.add_css({'screen': [self.static('exadmin/css/bootstrap-image-gallery.min.css')]})
        return media

    def block_before_fieldsets(self, context, node):
        if self.include_image:
            return """
              <div id="gallery" data-toggle="modal-gallery" data-target="#modal-gallery">
                <!-- modal-gallery is the modal dialog used for the image gallery -->
                <div id="modal-gallery" class="modal modal-gallery hide fade" tabindex="-1">
                    <div class="modal-header">
                        <a class="close" data-dismiss="modal">&times;</a>
                        <h3 class="modal-title"></h3>
                    </div>
                    <div class="modal-body"><div class="modal-image"></div></div>
                    <div class="modal-footer">
                        <a class="btn btn-primary modal-next">Next <i class="icon-arrow-right icon-white"></i></a>
                        <a class="btn btn-info modal-prev"><i class="icon-arrow-left icon-white"></i> Previous</a>
                        <a class="btn btn-success modal-play modal-slideshow" data-slideshow="5000"><i class="icon-play icon-white"></i> Slideshow</a>
                        <a class="btn modal-download" target="_blank"><i class="icon-download"></i> Download</a>
                    </div>
                </div>
            """

    def block_after_fieldsets(self, context, node):
        if self.include_image:
            return "</div>"

site.register_plugin(ModelDetailPlugin, DetailAdminView)
site.register_plugin(ModelDetailPlugin, ModelFormAdminView)


