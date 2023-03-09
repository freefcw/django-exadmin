import copy

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.db import models
from django.forms.models import modelform_factory
from django.http import Http404
from django.template import loader
from django.template.response import TemplateResponse
from django.utils.encoding import force_unicode, smart_unicode
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext as _
from django.utils.html import conditional_escape
from exadmin.layout import FormHelper, Layout, Fieldset, Container, Column, Field
from exadmin.util import unquote, lookup_field, display_for_field, boolean_icon, label_for_field

from base import ModelAdminView, filter_hook, csrf_protect_m


class ShowField(Field):
    template = "admin/layout/field_value.html"

    def __init__(self, callback, *args, **kwargs):
        super(ShowField, self).__init__(*args, **kwargs)
        self.results = [(field, callback(field)) for field in self.fields]

    def render(self, form, form_style, context):
        return ''.join(
            loader.render_to_string(
                self.template, {'field': form[field], 'result': result}
            )
            for field, result in self.results
            if form.fields[field].widget != forms.HiddenInput
        )

class ResultField(object):

    def __init__(self, obj, field_name, admin_view=None):
        self.text = '&nbsp;'
        self.wraps = []
        self.allow_tags = False
        self.obj = obj
        self.admin_view = admin_view
        self.field_name = field_name
        self.field = None
        self.attr = None
        self.label = None
        self.value = None

        self.init()

    def init(self):
        self.label = label_for_field(self.field_name, self.obj.__class__,
            model_admin = self.admin_view,
            return_attr = False
        )
        try:
            f, attr, value = lookup_field(self.field_name, self.obj, self.admin_view)
        except (AttributeError, ObjectDoesNotExist):
            self.text
        else:
            if f is None:
                self.allow_tags = getattr(attr, 'allow_tags', False)
                boolean = getattr(attr, 'boolean', False)
                if boolean:
                    self.allow_tags = True
                    self.text = boolean_icon(value)
                else:
                    self.text = smart_unicode(value)
            elif isinstance(f.rel, models.ManyToOneRel):
                self.text = getattr(self.obj, f.name)
            else:
                self.text = display_for_field(value, f)
            self.field = f
            self.attr = attr
            self.value = value

    @property
    def val(self):
        text = mark_safe(self.text) if self.allow_tags else conditional_escape(self.text)
        if force_unicode(text) == '':
            text = mark_safe(f"""<span class="muted">{_('Null')}</span>""")
        for wrap in self.wraps:
            text = mark_safe(wrap % text)
        return text

def replace_field_to_value(layout, cb):
    for i, lo in enumerate(layout.fields):
        if isinstance(lo, Field) or issubclass(lo.__class__, Field):
            layout.fields[i] = ShowField(cb, *lo.fields, **lo.attrs)
        elif isinstance(lo, basestring):
            layout.fields[i] = ShowField(cb, lo)
        elif hasattr(lo, 'get_field_names'):
            replace_field_to_value(lo, cb)

class DetailAdminView(ModelAdminView):

    form = forms.ModelForm
    detail_layout = None
    detail_show_all = True
    detail_template = None
    form_layout = None

    def init_request(self, object_id, *args, **kwargs):
        self.obj = self.get_object(unquote(object_id))

        if not self.has_change_permission(self.obj):
            raise PermissionDenied

        if self.obj is None:
            raise Http404(_('%(name)s object with primary key %(key)r does not exist.') % \
                {'name': force_unicode(self.opts.verbose_name), 'key': escape(object_id)})
        self.org_obj = self.obj

    @filter_hook
    def get_form_layout(self):
        layout = copy.deepcopy(self.detail_layout or self.form_layout)

        if layout is None:
            layout = Layout(Container(
                    Fieldset("", *self.form_obj.fields.keys(), css_class="unsort no_title"), css_class="form-horizontal"
                    ))
        elif type(layout) in (list, tuple) and len(layout) > 0:
            if isinstance(layout[0], Column):
                layout = Layout(Container(*layout))
            elif isinstance(layout[0], Fieldset):
                layout = Layout(Container(*layout, css_class="form-horizontal"))
            else:
                layout = Layout(Container(Fieldset("", *layout, css_class="unsort no_title"), css_class="form-horizontal"))

            if self.detail_show_all:
                rendered_fields = [i[1] for i in layout.get_field_names()]
                container = layout[0].fields
                other_fieldset = Fieldset(_(u'Other Fields'), *[f for f in self.form_obj.fields.keys() if f not in rendered_fields])

                if len(other_fieldset.fields):
                    if len(container) and isinstance(container[0], Column):
                        container[0].fields.append(other_fieldset)
                    else:
                        container.append(other_fieldset)

        return layout

    @filter_hook
    def get_model_form(self, **kwargs):
        """
        Returns a Form class for use in the admin add view. This is used by
        add_view and change_view.
        """
        exclude = [] if self.exclude is None else list(self.exclude)
        if self.exclude is None and hasattr(self.form, '_meta') and self.form._meta.exclude:
            # Take the custom ModelForm's Meta.exclude into account only if the
            # ModelAdmin doesn't define its own.
            exclude.extend(self.form._meta.exclude)
        # if exclude is an empty list we pass None to be consistant with the
        # default on modelform_factory
        exclude = exclude or None
        defaults = {
            "form": self.form,
            "exclude": exclude,
        } | kwargs
        return modelform_factory(self.model, **defaults)

    @filter_hook
    def get_form_helper(self):
        helper = FormHelper()
        helper.form_tag = False
        layout = self.get_form_layout()
        replace_field_to_value(layout, self.get_field_result)
        helper.add_layout(layout)
        helper.filter(basestring, max_level=20).wrap(ShowField, admin_view=self)
        return helper

    @csrf_protect_m
    @filter_hook
    def get(self, request, *args, **kwargs):
        form = self.get_model_form()
        self.form_obj = form(instance=self.obj)
        if helper := self.get_form_helper():
            self.form_obj.helper = helper

        return self.get_response()

    @filter_hook
    def get_context(self):
        form = self.form_obj

        media = self.media + form.media
        ordered_objects = self.opts.get_ordered_objects()

        new_context = {
            'form': form,
            'media': media,
            'object': self.obj,
            'show_delete': self.obj is not None,
            'add': self.obj is None,
            'change': self.obj is not None,
            'app_label': self.opts.app_label,
            'has_add_permission': self.has_add_permission(),
            'has_change_permission': self.has_change_permission(self.obj),
            'has_delete_permission': self.has_delete_permission(self.obj),
            'has_file_field': True, # FIXME - this should check if form or formsets have a FileField,
            'ordered_objects': ordered_objects,
            'form_url': '',
            'opts': self.opts,
            'content_type_id': ContentType.objects.get_for_model(self.model).id,
            'title': _('%s Detail') % force_unicode(self.opts.verbose_name),
            'object_id': str(self.obj.pk),
        }

        context = super(DetailAdminView, self).get_context()
        context.update(new_context)
        return context

    @filter_hook
    def get_media(self):
        media = super(DetailAdminView, self).get_media()
        media.add_css({'screen': [self.static('exadmin/css/form.css')]})
        return media

    @filter_hook
    def get_field_result(self, field_name):
        return ResultField(self.obj, field_name, self)

    @filter_hook
    def get_response(self, *args, **kwargs):
        context = self.get_context()
        context.update(kwargs or {})

        return TemplateResponse(
            self.request,
            self.detail_template
            or [
                f"admin/{self.opts.app_label}/{self.opts.object_name.lower()}/detail.html",
                f"admin/{self.opts.app_label}/detail.html",
                "admin/detail.html",
            ],
            context,
            current_app=self.admin_site.name,
        )


class DetailAdminUtil(DetailAdminView):

    def init_request(self, obj):
        self.obj = obj
        self.org_obj = obj



