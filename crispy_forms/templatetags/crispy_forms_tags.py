# -*- coding: utf-8 -*-
from copy import copy

from django.conf import settings
from django.forms.formsets import BaseFormSet
from django.template import Context
from django.template.loader import get_template
from django import template

from crispy_forms.helper import FormHelper

register = template.Library()
# We import the filters, so they are available when doing load crispy_forms_tags
from crispy_forms_filters import *

TEMPLATE_PACK = getattr(settings, 'CRISPY_TEMPLATE_PACK', 'bootstrap')


class ForLoopSimulator(object):
    """
    Simulates a forloop tag, precisely::

        {% for form in formset.forms %}

    If `{% crispy %}` is rendering a formset with a helper, We inject a `ForLoopSimulator` object
    in the context as `forloop` so that formset forms can do things like::

        Fieldset("Item {{ forloop.counter }}", [...])
        HTML("{% if forloop.first %}First form text{% endif %}"
    """
    def __init__(self, formset):
        self.len_values = len(formset.forms)

        # Shortcuts for current loop iteration number.
        self.counter = 1
        self.counter0 = 0
        # Reverse counter iteration numbers.
        self.revcounter = self.len_values
        self.revcounter0 = self.len_values - 1
        # Boolean values designating first and last times through loop.
        self.first = True
        self.last = self.len_values == 1

    def iterate(self):
        """
        Updates values as if we had iterated over the for
        """
        self.counter += 1
        self.counter0 += 1
        self.revcounter -= 1
        self.revcounter0 -= 1
        self.first = False
        self.last = (self.revcounter0 == self.len_values - 1)


def copy_context(context):
    """
    Copies a `Context` variable. It uses `Context.__copy__` if available
    (introduced in Django 1.3) or copy otherwise.
    """
    if hasattr(context, "__copy__"):
        return context.__copy__()

    duplicate = copy(context)
    duplicate.dicts = context.dicts[:]
    return duplicate


class BasicNode(template.Node):
    """
    Basic Node object that we can rely on for Node objects in normal
    template tags. I created this because most of the tags we'll be using
    will need both the form object and the helper string. This handles
    both the form object and parses out the helper string into attributes
    that templates can easily handle.
    """
    def __init__(self, form, helper):
        self.form = form
        self.helper = helper if helper is not None else None

    def get_render(self, context):
        """
        Returns a `Context` object with all the necesarry stuff for rendering the form

        :param context: `django.template.Context` variable holding the context for the node

        `self.form` and `self.helper` are resolved into real Python objects resolving them
        from the `context`. The `actual_form` can be a form or a formset. If it's a formset
        `is_formset` is set to True. If the helper has a layout we use it, for rendering the
        form or the formset's forms.
        """
        # Nodes are not thread safe in multithreaded environments
        # https://docs.djangoproject.com/en/dev/howto/custom-template-tags/#thread-safety-considerations
        if self not in context.render_context:
            context.render_context[self] = (
                template.Variable(self.form),
                template.Variable(self.helper) if self.helper else None
            )
        form, helper = context.render_context[self]

        actual_form = form.resolve(context)
        if self.helper is not None:
            helper = helper.resolve(context)
        else:
            # If the user names the helper within the form `helper` (standard), we use it
            # This allows us to have simplified tag syntax: {% crispy form %}
            helper = actual_form.helper if hasattr(actual_form, 'helper') else FormHelper()

        # We get the response dictionary
        is_formset = isinstance(actual_form, BaseFormSet)
        response_dict = self.get_response_dict(helper, context, is_formset)
        node_context = copy_context(context)
        node_context.update(response_dict)

        if helper and helper.layout:
            if is_formset:
                forloop = ForLoopSimulator(actual_form)
                for form in actual_form.forms:
                    node_context.update({'forloop': forloop})
                    form.form_html = helper.render_layout(form, node_context)
                    forloop.iterate()

            else:
                actual_form.form_html = helper.render_layout(actual_form, node_context)
        if is_formset:
            response_dict.update({'formset': actual_form})
        else:
            response_dict.update({'form': actual_form})

        return Context(response_dict)

    def get_response_dict(self, helper, context, is_formset):
        """
        Returns a dictionary with all the parameters necessary to render the form/formset in a template.

        :param attrs: Dictionary with the helper's attributes used for rendering the form/formset
        :param context: `django.template.Context` for the node
        :param is_formset: Boolean value. If set to True, indicates we are working with a formset.
        """
        if not isinstance(helper, FormHelper):
            raise TypeError('helper object provided to {% crispy %} tag must be a crispy.helper.FormHelper object.')

        attrs = helper.get_attributes()
        form_type = "formset" if is_formset else "form"
        # We take form/formset parameters from attrs if they are set, otherwise we use defaults
        response_dict = {
            f'{form_type}_action': attrs['attrs'].get("action", ''),
            f'{form_type}_method': attrs.get("form_method", 'post'),
            f'{form_type}_tag': attrs.get("form_tag", True),
            f'{form_type}_class': attrs['attrs'].get("class", ''),
            f'{form_type}_id': attrs['attrs'].get("id", ""),
            f'{form_type}_style': attrs.get("form_style", None),
            'form_error_title': attrs.get("form_error_title", None),
            'formset_error_title': attrs.get("formset_error_title", None),
            'form_show_errors': attrs.get("form_show_errors", True),
            'help_text_inline': attrs.get("help_text_inline", False),
            'html5_required': attrs.get("html5_required", False),
            'inputs': attrs.get('inputs', []),
            'is_formset': is_formset,
            f'{form_type}_attrs': attrs.get('attrs', ''),
            'flat_attrs': attrs.get('flat_attrs', ''),
            'error_text_inline': attrs.get('error_text_inline', True),
        }

        # Handles custom attributes added to helpers
        for attribute_name, value in attrs.items():
            if attribute_name not in response_dict:
                response_dict[attribute_name] = value

        if context.has_key('csrf_token'):
            response_dict['csrf_token'] = context['csrf_token']

        return response_dict


whole_uni_formset_template = get_template(
    f'{TEMPLATE_PACK}/whole_uni_formset.html'
)
whole_uni_form_template = get_template(f'{TEMPLATE_PACK}/whole_uni_form.html')

class CrispyFormNode(BasicNode):
    def render(self, context):
        c = self.get_render(context)

        if c['is_formset']:
            template = (
                get_template(f'{TEMPLATE_PACK}/whole_uni_formset.html')
                if settings.DEBUG
                else whole_uni_formset_template
            )
        elif settings.DEBUG:
            template = get_template(f'{TEMPLATE_PACK}/whole_uni_form.html')
        else:
            template = whole_uni_form_template

        return template.render(c)


# {% crispy %} tag
@register.tag(name="uni_form")
@register.tag(name="crispy")
def do_uni_form(parser, token):
    """
    You need to pass in at least the form/formset object, and can also pass in the
    optional `crispy_forms.helpers.FormHelper` object.

    helper (optional): A `uni_form.helper.FormHelper` object.

    Usage::

        {% include crispy_tags %}
        {% crispy form form.helper %}

    If the `FormHelper` attribute is named `helper` you can simply do::

        {% crispy form %}
    """
    token = token.split_contents()
    form = token.pop(1)

    try:
        helper = token.pop(1)
    except IndexError:
        helper = None

    return CrispyFormNode(form, helper)
