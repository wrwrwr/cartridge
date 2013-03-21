from django import forms
from django.db.models.fields import BLANK_CHOICE_DASH
from django.utils.translation import ugettext_lazy as _

from mezzanine.core.forms import DynamicInlineAdminForm


class AttributeSelectionForm(forms.ModelForm):
    # Choice of existing attributes instead of generic type / id.
    attribute = forms.ChoiceField(label=_("Attribute"))

    def __init__(self, *args, **kwargs):
        super(AttributeSelectionForm, self).__init__(*args, **kwargs)

        # Populate attribute field choices with all models having content type
        # allowable for the attribute_type field (grouped by content type).
        # Note: this assumes that attribute_type uses limit_choices_to.
        attributes = BLANK_CHOICE_DASH[:]
        for attribute_type in self.fields['attribute_type'].queryset:
            attributes_group = []
            for attribute in attribute_type.model_class().objects.all():
                attributes_group.append(
                    ('{}-{}'.format(attribute_type.pk, attribute.pk),
                     attribute))
            attributes.append((attribute_type, attributes_group))
        self.fields['attribute'].choices = attributes

        # Split attribute_type-attribute_id values in data, so they are
        # saved in the model fields.
        data = self.data
        attribute = self.add_prefix('attribute')
        if attribute in data and data[attribute] != '':
            type_id = data.get(attribute).split('-', 1)
            data[attribute + '_type'], data[attribute + '_id'] = type_id

        # Make an initial value for the attribute field by joining initial
        # values for attribute_type and attribute_id.
        initial = self.initial
        try:
            initial['attribute'] = '{}-{}'.format(
                initial['attribute_type'], initial['attribute_id'])
        except KeyError:
            pass


class ProductAttributeForm(DynamicInlineAdminForm, AttributeSelectionForm):
    pass
