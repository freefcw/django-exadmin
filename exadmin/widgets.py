"""
Form Widget classes specific to the Django admin site.
"""
from itertools import chain
from django import forms
from django.forms.widgets import RadioFieldRenderer, RadioInput
from django.utils.encoding import force_unicode
from django.utils.safestring import mark_safe
from django.utils.html import conditional_escape

from util import static


class AdminDateWidget(forms.DateInput):

    @property
    def media(self):
        return forms.Media(js=[static('exadmin/js/bootstrap-datepicker.js'), static("exadmin/js/widgets/datetime.js")],
            css={'screen': [static('exadmin/css/datepicker.css')]})

    def __init__(self, attrs=None, format=None):
        final_attrs = {'class': 'date-field', 'size': '10'}
        if attrs is not None:
            final_attrs |= attrs
        super(AdminDateWidget, self).__init__(attrs=final_attrs, format=format)

    def render(self, name, value, attrs=None):
        input_html = super(AdminDateWidget, self).render(name, value, attrs)
        return mark_safe(
            f'<div class="input-append date">{input_html}<span class="add-on"><i class="icon-calendar"></i></span></div>'
        )

class AdminTimeWidget(forms.TimeInput):

    @property
    def media(self):
        return forms.Media(js=[static('exadmin/js/bootstrap-timepicker.js'), static("exadmin/js/widgets/datetime.js")],
            css={'screen': [static('exadmin/css/timepicker.css')]})

    def __init__(self, attrs=None, format=None):
        final_attrs = {'class': 'time-field', 'size': '8'}
        if attrs is not None:
            final_attrs |= attrs
        super(AdminTimeWidget, self).__init__(attrs=final_attrs, format=format)

    def render(self, name, value, attrs=None):
        input_html = super(AdminTimeWidget, self).render(name, value, attrs)
        return mark_safe(
            f'<div class="input-append time">{input_html}<span class="add-on"><i class="icon-time"></i></span></div>'
        )

class AdminSplitDateTime(forms.SplitDateTimeWidget):
    """
    A SplitDateTime Widget that has some admin-specific styling.
    """
    def __init__(self, attrs=None):
        widgets = [AdminDateWidget, AdminTimeWidget]
        # Note that we're calling MultiWidget, not SplitDateTimeWidget, because
        # we want to define widgets.
        forms.MultiWidget.__init__(self, widgets, attrs)

    def format_output(self, rendered_widgets):
        return mark_safe(
            f'<div class="datetime">{rendered_widgets[0]} - {rendered_widgets[1]}</div>'
        )

class AdminRadioInput(RadioInput):

    def render(self, name=None, value=None, attrs=None, choices=()):
        name = name or self.name
        value = value or self.value
        attrs = attrs or self.attrs
        if 'id' in self.attrs:
            label_for = f""" for="{self.attrs['id']}_{self.index}\""""
        else:
            label_for = ''
        choice_label = conditional_escape(force_unicode(self.choice_label))
        return mark_safe(
            f"""<label{label_for} class="radio {attrs.get('class', '')}">{self.tag()} {choice_label}</label>"""
        )

class AdminRadioFieldRenderer(RadioFieldRenderer):

    def __iter__(self):
        for i, choice in enumerate(self.choices):
            yield AdminRadioInput(self.name, self.value, self.attrs.copy(), choice, i)

    def __getitem__(self, idx):
        choice = self.choices[idx] # Let the IndexError propogate
        return AdminRadioInput(self.name, self.value, self.attrs.copy(), choice, idx)

    def render(self):
        return mark_safe(u'\n'.join([force_unicode(w) for w in self]))

class AdminRadioSelect(forms.RadioSelect):
    renderer = AdminRadioFieldRenderer


class AdminCheckboxSelect(forms.CheckboxSelectMultiple):
    def render(self, name, value, attrs=None, choices=()):
        if value is None: value = []
        has_id = attrs and 'id' in attrs
        final_attrs = self.build_attrs(attrs, name=name)
        output = []
        # Normalize to strings
        str_values = {force_unicode(v) for v in value}
        for i, (option_value, option_label) in enumerate(chain(self.choices, choices)):
            # If an ID attribute was given, add a numeric index as a suffix,
            # so that the checkboxes don't all have the same ID attribute.
            if has_id:
                final_attrs = dict(final_attrs, id=f"{attrs['id']}_{i}")
                label_for = f""" for="{final_attrs['id']}\""""
            else:
                label_for = ''

            cb = forms.CheckboxInput(final_attrs, check_test=lambda value: value in str_values)
            option_value = force_unicode(option_value)
            rendered_cb = cb.render(name, option_value)
            option_label = conditional_escape(force_unicode(option_label))
            output.append(
                f"""<label{label_for} class="checkbox {final_attrs.get('class', '')}">{rendered_cb} {option_label}</label>"""
            )
        return mark_safe(u'\n'.join(output))

class AdminFileWidget(forms.ClearableFileInput):
    template_with_initial = f'<p class="file-upload">{forms.ClearableFileInput.template_with_initial}</p>'
    template_with_clear = f'<span class="clearable-file-input">{forms.ClearableFileInput.template_with_clear}</span>'

class AdminTextareaWidget(forms.Textarea):
    def __init__(self, attrs=None):
        final_attrs = {'class': 'textarea-field'}
        if attrs is not None:
            final_attrs |= attrs
        super(AdminTextareaWidget, self).__init__(attrs=final_attrs)

class AdminTextInputWidget(forms.TextInput):
    def __init__(self, attrs=None):
        final_attrs = {'class': 'text-field'}
        if attrs is not None:
            final_attrs |= attrs
        super(AdminTextInputWidget, self).__init__(attrs=final_attrs)

class AdminURLFieldWidget(forms.TextInput):
    def __init__(self, attrs=None):
        final_attrs = {'class': 'url-field'}
        if attrs is not None:
            final_attrs |= attrs
        super(AdminURLFieldWidget, self).__init__(attrs=final_attrs)

class AdminIntegerFieldWidget(forms.TextInput):
    def __init__(self, attrs=None):
        final_attrs = {'class': 'int-field'}
        if attrs is not None:
            final_attrs |= attrs
        super(AdminIntegerFieldWidget, self).__init__(attrs=final_attrs)

class AdminCommaSeparatedIntegerFieldWidget(forms.TextInput):
    def __init__(self, attrs=None):
        final_attrs = {'class': 'sep-int-field'}
        if attrs is not None:
            final_attrs |= attrs
        super(AdminCommaSeparatedIntegerFieldWidget, self).__init__(attrs=final_attrs)
