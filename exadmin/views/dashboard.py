import copy

from django import forms
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models.base import ModelBase
from django.forms.forms import DeclarativeFieldsMetaclass
from django.forms.util import flatatt
from django.template import loader
from django.template.context import RequestContext
from django.test.client import RequestFactory
from django.utils.encoding import force_unicode, smart_unicode
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache
from exadmin import widgets as exwidgets
from exadmin.layout import FormHelper
from exadmin.models import UserSettings, UserWidget
from exadmin.sites import site
from exadmin.views.base import CommAdminView, filter_hook, csrf_protect_m
from exadmin.views.edit import CreateAdminView
from exadmin.views.list import ListAdminView


class WidgetTypeSelect(forms.Widget):

    def __init__(self, widgets, attrs=None):
        super(WidgetTypeSelect, self).__init__(attrs)
        self._widgets = widgets

    def render(self, name, value, attrs=None):
        if value is None: value = ''
        final_attrs = self.build_attrs(attrs, name=name)
        final_attrs['class'] = 'nav nav-pills nav-stacked'
        output = [f'<ul{flatatt(final_attrs)}>']
        if options := self.render_options(force_unicode(value), final_attrs['id']):
            output.append(options)
        output.append(u'</ul>')
        output.append(
            f"""<input type="hidden" id="{final_attrs['id']}_input" name="{name}" value="{force_unicode(value)}"/>"""
        )
        return mark_safe(u'\n'.join(output))

    def render_option(self, selected_choice, widget, id):
        if widget.widget_type == selected_choice:
            selected_html = u' class="active"'
        else:
            selected_html = ''
        return (u'<li%s><a onclick="'+
            'javascript:$(this).parent().parent().find(\'>li\').removeClass(\'active\');$(this).parent().addClass(\'active\');'+
            '$(\'#%s_input\').attr(\'value\', \'%s\')' % (id, widget.widget_type) +
            '"><h4><i class="%s"></i> %s</h4><p>%s</p></a></li>') % (
            selected_html,
            widget.widget_icon,
            widget.widget_title or widget.widget_type,
            widget.description)

    def render_options(self, selected_choice, id):
        output = [
            self.render_option(selected_choice, widget, id)
            for widget in self._widgets
        ]
        return u'\n'.join(output)


class UserWidgetAdmin(object):

    list_display = ('widget_type', 'page_id', 'user')
    list_filter = ['user', 'widget_type', 'page_id']
    list_display_links = ('widget_type',)
    user_fields = ['user']

    wizard_form_list = (
            (_(u"Widget Type"), ('page_id', 'widget_type')),
            (_(u"Widget Params"), {'callback': "get_widget_params_form", 'convert': "convert_widget_params"})
        )

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'widget_type':
            widgets = widget_manager._widgets.values()
            form_widget = WidgetTypeSelect(widgets)
            return forms.ChoiceField(choices=[(w.widget_type, w.description) for w in widgets], widget=form_widget)
        if db_field.name == 'page_id':
            kwargs['widget'] = forms.HiddenInput
        return super(UserWidgetAdmin, self).formfield_for_dbfield(db_field, **kwargs)

    def get_widget_params_form(self, wizard):
        data = wizard.get_cleaned_data_for_step(wizard.steps.first)
        widget_type = data['widget_type']
        widget = widget_manager.get(widget_type)
        fields = copy.deepcopy(widget.base_fields)
        if fields.has_key('id'):
            del fields['id']
        return DeclarativeFieldsMetaclass("WidgetParamsForm", (forms.Form,), fields)

    def convert_widget_params(self, wizard, cleaned_data, form):
        widget = UserWidget()
        value = dict([(f.name, f.value()) for f in form])
        widget.set_value(value)
        cleaned_data['value'] = widget.value
        cleaned_data['user'] = self.user.pk

    def get_list_display(self):
        list_display = super(UserWidgetAdmin, self).get_list_display()
        if not self.user.is_superuser:
            list_display.remove('user')
        return list_display

    def queryset(self):
        if self.user.is_superuser:
            return super(UserWidgetAdmin, self).queryset()
        return UserWidget.objects.filter(user=self.user)

    def delete_model(self):
        try:
            obj = self.obj
            portal_pos = UserSettings.objects.get(
                user=obj.user, key=f"dashboard:{obj.page_id}:pos"
            )
            pos = [[w for w in col.split(',') if w != str(obj.id)] for col in portal_pos.value.split('|')]
            portal_pos.value = '|'.join([','.join(col) for col in pos])
            portal_pos.save()
        except Exception:
            pass
        super(UserWidgetAdmin, self).delete_model()


site.register(UserWidget, UserWidgetAdmin)

class WidgetManager(object):
    _widgets = None

    def __init__(self):
        self._widgets = {}

    def register(self, widget_class):
        self._widgets[widget_class.widget_type] = widget_class
        return widget_class

    def get(self, name):
        return self._widgets[name]

widget_manager = WidgetManager()

class WidgetDataError(Exception):

    def __init__(self, widget, errors):
        super(WidgetDataError, self).__init__(str(errors))
        self.widget = widget
        self.errors = errors

class BaseWidget(forms.Form):

    template = 'admin/widgets/base.html'
    description = 'Base Widget, don\'t use it.'
    widget_title = None
    widget_icon = 'icon-plus-sign-alt'
    base_title = None

    id = forms.IntegerField(_('Widget ID'), widget=forms.HiddenInput)
    title = forms.CharField(_('Widget Title'), required=False)

    def __init__(self, dashboard, data):
        self.dashboard = dashboard
        self.admin_site = dashboard.admin_site
        self.request = dashboard.request
        self.user = dashboard.request.user
        self.convert(data)
        super(BaseWidget, self).__init__(data)

        if not self.is_valid():
            raise WidgetDataError(self, self.errors.as_text())

        self.setup()

    def setup(self):
        helper = FormHelper()
        helper.form_tag = False
        self.helper = helper

        self.id = self.cleaned_data['id']
        self.title = self.cleaned_data['title'] or self.base_title

        if not (self.user.is_superuser or self.has_perm()):
            raise PermissionDenied

    @property
    def widget(self):
        context = {'widget_id': self.id, 'widget_title': self.title, 'form': self}
        self.context(context)
        return loader.render_to_string(self.template, context, context_instance=RequestContext(self.request))

    def context(self, context):
        pass

    def convert(self, data):
        pass

    def has_perm(self):
        return False

    def save(self):
        value = dict([(f.name, f.value()) for f in self])
        user_widget = UserWidget.objects.get(id=self.id)
        user_widget.set_value(value)
        user_widget.save()

    def static(self, path):
        return self.dashboard.static(path)

    def media(self):
        return forms.Media()

@widget_manager.register
class HtmlWidget(BaseWidget):
    widget_type = 'html'
    description = 'Html Content Widget, can write any html content in widget.'

    content = forms.CharField(label=_('Html Content'), widget=exwidgets.AdminTextareaWidget, required=False)

    def has_perm(self):
        return True

    def context(self, context):
        context['content'] = self.cleaned_data['content']

class ModelChoiceIterator(object):
    def __init__(self, field):
        self.field = field

    def __iter__(self):
        from exadmin import site as g_admin_site
        for m, ma in g_admin_site._registry.items():
            yield (f'{m._meta.app_label}.{m._meta.module_name}', m._meta.verbose_name)

class ModelChoiceField(forms.ChoiceField):

    def __init__(self, required=True, widget=None, label=None, initial=None,
                 help_text=None, *args, **kwargs):
        # Call Field instead of ChoiceField __init__() because we don't need
        # ChoiceField.__init__().
        forms.Field.__init__(self, required, widget, label, initial, help_text,
                       *args, **kwargs)
        self.widget.choices = self.choices

    def __deepcopy__(self, memo):
        return forms.Field.__deepcopy__(self, memo)

    def _get_choices(self):
        return ModelChoiceIterator(self)

    choices = property(_get_choices, forms.ChoiceField._set_choices)

    def to_python(self, value):
        if isinstance(value, ModelBase):
            return value
        app_label, model_name = value.lower().split('.')
        return models.get_model(app_label, model_name)

    def prepare_value(self, value):
        if isinstance(value, ModelBase):
            value = f'{value._meta.app_label}.{value._meta.module_name}'
        return value

    def valid_value(self, value):
        value = self.prepare_value(value)
        return any(value == smart_unicode(k) for k, v in self.choices)

class ModelBaseWidget(BaseWidget):

    app_label = None
    module_name = None
    model_perm = 'change'
    model = ModelChoiceField(label=_(u'Target Model'))

    def __init__(self, dashboard, data):
        self.dashboard = dashboard
        super(ModelBaseWidget, self).__init__(dashboard, data)

    def setup(self):
        self.model = self.cleaned_data['model']
        self.app_label = self.model._meta.app_label
        self.module_name = self.model._meta.module_name

        super(ModelBaseWidget, self).setup()

    def has_perm(self):
        return self.dashboard.has_model_perm(self.model, self.model_perm)

    def filte_choices_model(self, model, modeladmin):
        return self.dashboard.has_model_perm(model, self.model_perm)

    def model_admin_urlname(self, name, *args, **kwargs):
        return reverse(
            f"{self.admin_site.app_name}:{self.app_label}_{self.module_name}_{name}",
            args=args,
            kwargs=kwargs,
        )

class PartialBaseWidget(BaseWidget):

    def get_view_class(self, view_class, model=None, **opts):
        admin_class = self.admin_site._registry.get(model) if model else None
        return self.admin_site.get_view_class(view_class, admin_class, **opts)

    def get_factory(self):
        return RequestFactory()

    def setup_request(self, request):
        request.user = self.user
        return request

    def make_get_request(self, path, data={}, **extra):
        req = self.get_factory().get(path, data, **extra)
        return self.setup_request(req)

    def make_post_request(self, path, data={}, **extra):
        req = self.get_factory().post(path, data, **extra)
        return self.setup_request(req)

@widget_manager.register
class QuickBtnWidget(BaseWidget):
    widget_type = 'qbutton'
    description = 'Quick button Widget, quickly open any page.'
    template = "admin/widgets/qbutton.html"
    base_title = "Quick Buttons"

    def convert(self, data):
        self.q_btns = data.pop('btns', [])

    def get_model(self, model_or_label):
        if isinstance(model_or_label, ModelBase):
            return model_or_label
        else:
            return models.get_model(*model_or_label.lower().split('.'))

    def context(self, context):
        btns = []
        for b in self.q_btns:
            btn = {}
            if b.has_key('model'):
                model = self.get_model(b['model'])
                btn['url'] = reverse(
                    f"{self.admin_site.app_name}:{model._meta.app_label}_{model._meta.module_name}_{b.get('view', 'changelist')}"
                )
                btn['title'] = model._meta.verbose_name
            else:
                btn['url'] = b['url']

            if b.has_key('title'):
                btn['title'] = b['title']
            if b.has_key('icon'):
                btn['icon'] = b['icon']
            btns.append(btn)

        context.update({ 'btns': btns })

@widget_manager.register
class ListWidget(ModelBaseWidget, PartialBaseWidget):
    widget_type = 'list'
    description = 'Any Objects list Widget.'
    template = "admin/widgets/list.html"

    def convert(self, data):
        self.list_params = data.pop('params', {})

    def setup(self):
        super(ListWidget, self).setup()

        if not self.title:
            self.title = self.model._meta.verbose_name_plural

        req = self.make_get_request("", self.list_params)
        self.list_view = self.get_view_class(ListAdminView, self.model, list_per_page=10)(req)

    def context(self, context):
        list_view = self.list_view
        list_view.make_result_list()

        base_fields = list_view.base_list_display
        if len(base_fields) > 5:
            base_fields = base_fields[:5]

        context['result_headers'] = [c for c in list_view.result_headers().cells if c.field_name in base_fields]
        context['results'] = [
            list(filter(lambda c: c.field_name in base_fields, r.cells))
            for r in list_view.results()
        ]
        context['result_count'] = list_view.result_count
        context['page_url'] = self.model_admin_urlname('changelist')

@widget_manager.register
class AddFormWidget(ModelBaseWidget, PartialBaseWidget):
    widget_type = 'addform'
    description = 'Add any model object Widget.'
    template = "admin/widgets/addform.html"
    model_perm = 'add'

    def setup(self):
        super(AddFormWidget, self).setup()

        if self.title is None:
            self.title = _('Add %s') % self.model._meta.verbose_name

        req = self.make_get_request("")
        self.add_view = self.get_view_class(CreateAdminView, self.model, list_per_page=10)(req)
        self.add_view.instance_forms()

    def context(self, context):
        helper = FormHelper()
        helper.form_tag = False

        context.update({
            'addform': self.add_view.form_obj,
            'addhelper': helper,
            'addurl': self.add_view.model_admin_urlname('add'),
            'model': self.model
            })

    def media(self):
        media = self.add_view.media + self.add_view.form_obj.media
        media.add_js([self.static('exadmin/js/quick-form.js'),])
        return media

class Dashboard(CommAdminView):

    widgets = []
    title = "Dashboard"

    def get_page_id(self):
        return self.request.path

    def get_portal_key(self):
        return f"dashboard:{self.get_page_id()}:pos"

    @filter_hook
    def get_widget(self, widget_or_id, data=None):
        try:
            if isinstance(widget_or_id, UserWidget):
                widget = widget_or_id
            else:
                widget = UserWidget.objects.get(user=self.user, page_id=self.get_page_id(), id=widget_or_id)
            return widget_manager.get(widget.widget_type)(self, data or widget.get_value())
        except UserWidget.DoesNotExist:
            return None

    @filter_hook
    def get_init_widget(self):
        portal = []
        widgets = self.widgets
        for col in widgets:
            portal_col = []
            for opts in col:
                try:
                    widget = UserWidget(user=self.user, page_id=self.get_page_id(), widget_type=opts['type'])
                    widget.set_value(opts)
                    widget.save()
                    portal_col.append(self.get_widget(widget))
                except (PermissionDenied, WidgetDataError):
                    widget.delete()
                    continue
            portal.append(portal_col)

        UserSettings(
            user=self.user,
            key=f"dashboard:{self.get_page_id()}:pos",
            value='|'.join([','.join([str(w.id) for w in col]) for col in portal]),
        ).save()

        return portal

    @filter_hook
    def get_widgets(self):
        portal_pos = UserSettings.objects.filter(user=self.user, key=self.get_portal_key())
        if len(portal_pos) and portal_pos[0].value:
            portal_pos = portal_pos[0].value
            widgets = []
            user_widgets = dict([(uw.id, uw) for uw in UserWidget.objects.filter(user=self.user, page_id=self.get_page_id())])
            for col in portal_pos.split('|'):
                ws = []
                for wid in col.split(','):
                    try:
                        widget = user_widgets.get(int(wid))
                        if widget:
                            ws.append(self.get_widget(widget))
                    except Exception, e:
                        import logging
                        logging.error(e,exc_info=True)
                widgets.append(ws)
            return widgets
        else:
            return self.get_init_widget()

    @filter_hook
    def get_title(self):
        return self.title

    @filter_hook
    def get_context(self):
        new_context = {
            'title': self.get_title(),
        }
        context = super(Dashboard, self).get_context()
        context.update(new_context)
        return context

    @never_cache
    def get(self, request):
        self.widgets = self.get_widgets()
        context = self.get_context()
        context.update(
            {
                'portal_key': self.get_portal_key(),
                'columns': [
                    ('span%d' % (12 // len(self.widgets)), ws)
                    for ws in self.widgets
                ],
                'has_add_widget_permission': self.has_model_perm(
                    UserWidget, 'add'
                ),
                'add_widget_url': f"{self.admin_urlname(f'{UserWidget._meta.app_label}_{UserWidget._meta.module_name}_add')}?user={self.user.id}&page_id={self.get_page_id()}",
            }
        )
        return self.template_response('admin/dashboard.html', context)

    @csrf_protect_m
    def post(self, request):
        widget_id = request.POST['id']
        if request.POST.get('_delete', None) != 'on':
            widget = self.get_widget(widget_id, request.POST.copy())
            widget.save()
        else:
            try:
                widget = UserWidget.objects.get(user=self.user, page_id=self.get_page_id(), id=widget_id)
                widget.delete()
                try:
                    portal_pos = UserSettings.objects.get(
                        user=self.user, key=f"dashboard:{self.get_page_id()}:pos"
                    )
                    pos = [[w for w in col.split(',') if w != str(widget_id)] for col in portal_pos.value.split('|')]
                    portal_pos.value = '|'.join([','.join(col) for col in pos])
                    portal_pos.save()
                except Exception:
                    pass
            except UserWidget.DoesNotExist:
                pass

        return self.get(request)

    @filter_hook
    def get_media(self):
        media = super(Dashboard, self).get_media()
        media.add_js([self.static('exadmin/js/portal.js'), self.static('exadmin/js/dashboard.js')])
        media.add_css({'screen': [self.static('exadmin/css/form.css'), self.static('exadmin/css/dashboard.css')]})
        for ws in self.widgets:
            for widget in ws:
                media = media + widget.media()
        return media
        