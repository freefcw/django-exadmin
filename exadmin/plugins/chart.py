
import datetime, decimal, calendar

from django import forms
from django.template import loader
from django.http import HttpResponseNotFound
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.utils import simplejson
from django.utils.encoding import smart_unicode
from django.db import models
from django.utils.http import urlencode
from django.utils.translation import ugettext as _

from exadmin.sites import site
from exadmin.views import BaseAdminPlugin, ListAdminView
from exadmin.views.dashboard import ModelBaseWidget, widget_manager
from exadmin.util import lookup_field, label_for_field

@widget_manager.register
class ChartWidget(ModelBaseWidget):
    widget_type = 'chart'
    template = 'admin/widgets/chart.html'

    def convert(self, data):
        self.list_params = data.pop('params', {})
        self.chart = data.pop('chart', None)

    def setup(self):
        super(ChartWidget, self).setup()

        self.charts = {}
        self.one_chart = False
        model_admin = self.admin_site._registry[self.model]
        if hasattr(model_admin, 'data_charts'):
            chart = self.chart

            if chart and chart in model_admin.data_charts:
                self.charts = {chart : model_admin.data_charts[chart]}
                self.one_chart = True
                if self.title is None:
                    self.title = model_admin.data_charts[chart].get('title')
            else:
                self.charts = model_admin.data_charts
                if self.title is None:
                    self.title = _("%s Charts") % self.model._meta.verbose_name_plural

    def filte_choices_model(self, model, modeladmin):
        return bool(getattr(modeladmin, 'data_charts', None)) and \
            super(ChartWidget, self).filte_choices_model(model, modeladmin)

    def get_chart_url(self, name, v):
        return self.model_admin_urlname('chart', name) + "?" + urlencode(self.list_params)

    def context(self, context):
        context.update({
            'charts': [{"name": name, "title": v['title'], 'url': self.get_chart_url(name, v)} for name,v in self.charts.items()],
        })

    # Media
    def media(self):
        media = forms.Media()
        media.add_js([self.static('exadmin/js/jquery.flot.js')])
        media.add_js([self.static('exadmin/js/jquery.flot.pie.js')])
        media.add_js([self.static('exadmin/js/jquery.flot.resize.js')])
        media.add_js([self.static('exadmin/js/charts.js')])
        return media

class JSONEncoder(DjangoJSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime.date, datetime.datetime)):
            return calendar.timegm(o.timetuple()) * 1000
        elif isinstance(o, decimal.Decimal):
            return str(o)
        else:
            try:
                return super(JSONEncoder, self).default(o)
            except Exception:
                return smart_unicode(o)

class ChartsPlugin(BaseAdminPlugin):

    data_charts = {}

    def get_chart_url(self, name, v):
        return self.admin_view.model_admin_urlname('chart', name) + self.admin_view.get_query_string()

    # Media
    def get_media(self, media):
        if self.data_charts:
            media.add_js([self.static('exadmin/js/jquery.flot.js')])
            media.add_js([self.static('exadmin/js/jquery.flot.pie.js')])
            media.add_js([self.static('exadmin/js/jquery.flot.resize.js')])
            media.add_js([self.static('exadmin/js/charts.js')])
        return media

    # Block Views
    def block_results_top(self, context, nodes):
        if self.data_charts:
            context.update({
                'charts': [{"name": name, "title": v['title'], 'url': self.get_chart_url(name, v)} for name,v in self.data_charts.items()],
            })
            nodes.append(loader.render_to_string('admin/blocks/charts.html', context_instance=context))

class ChartsView(ListAdminView):

    data_charts = {}

    def get_ordering(self):
        if self.chart.has_key('order'):
            return self.chart['order']
        else:
            return super(ChartsView, self).get_ordering()

    def get(self, request, name):
        if not self.data_charts.has_key(name):
            return HttpResponseNotFound()

        self.chart = self.data_charts[name]

        self.x_field = self.chart['x-field']
        y_fields = self.chart['y-field']
        self.y_fields = (y_fields,) if type(y_fields) not in (list, tuple) else y_fields

        datas = [{"data":[], "label": label_for_field(i, self.model, model_admin=self)} for i in self.y_fields]

        self.make_result_list()

        for obj in self.result_list:
            xf, attrs, value = lookup_field(self.x_field, obj, self)
            for i, yfname in enumerate(self.y_fields):
                yf, yattrs, yv = lookup_field(yfname, obj, self)
                datas[i]["data"].append((value, yv))

        option = {'series': {'lines': { 'show': True }, 'points': { 'show': False }},
                'grid': { 'hoverable': True, 'clickable': True }}
        try:
            xfield = self.opts.get_field(self.x_field)
            if type(xfield) in (models.DateTimeField, models.DateField, models.TimeField):
                option['xaxis'] = { 'mode': "time", 'tickLength': 5}
                if type(xfield) is models.DateField:
                    option['xaxis']['timeformat'] = "%y/%m/%d";
                elif type(xfield) is models.TimeField:
                    option['xaxis']['timeformat'] = "%H:%M:%S";
                else:
                    option['xaxis']['timeformat'] = "%y/%m/%d %H:%M:%S";
        except Exception:
            pass

        option |= self.chart.get('option', {})

        content = {'data': datas, 'option': option}
        json = simplejson.dumps(content, cls=JSONEncoder, ensure_ascii=False)

        return HttpResponse(json)

site.register_plugin(ChartsPlugin, ListAdminView)
site.register_modelview(r'^chart/(.+)/$', ChartsView, name='%s_%s_chart')


