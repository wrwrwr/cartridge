from django import forms
from django.db.models.fields import BLANK_CHOICE_DASH
from django.utils.translation import ugettext_lazy as _

from mezzanine.core.forms import DynamicInlineAdminForm


class AttributeSelectionForm(forms.ModelForm):
    # Choice of existing attributes instead of generic type / id.

    def __init__(self, *args, **kwargs):
        # Create a fake "attribute" field and populate its choices with all
        # objects having content type allowable for the attribute_type field.
        # Note: this assumes that attribute_type uses limit_choices_to.
        attributes = BLANK_CHOICE_DASH[:]
        for attribute_type in self.base_fields['attribute_type'].queryset:
            attributes_group = []
            for attribute in attribute_type.model_class().objects.all():
                attributes_group.append(
                    ('{}-{}'.format(attribute_type.pk, attribute.pk),
                     attribute))
            attributes.append((attribute_type, attributes_group))
        self.base_fields['attribute'] = forms.ChoiceField(label=_("Attribute"),
                                                          choices=attributes)

        super(AttributeSelectionForm, self).__init__(*args, **kwargs)

        # Split attribute_type-attribute_id values in data, so they can
        # be saved using separate fields.
        data = self.data
        attribute = self.add_prefix('attribute')
        type_id = data.get(attribute, '').split('-', 1)
        if len(type_id) == 2:
            data[attribute + '_type'], data[attribute + '_id'] = type_id
        # Make an initial value for the fake "attribute" field equal to
        # the current attribute_type-attribute_id.
        try:
            initial = self.initial
            initial['attribute'] = '{}-{}'.format(
                initial['attribute_type'], initial['attribute_id'])
        except KeyError:
            pass


class ProductAttributeForm(DynamicInlineAdminForm, AttributeSelectionForm):
    pass
