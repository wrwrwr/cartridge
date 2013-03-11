from django import forms
from django.contrib import admin
from django.db.models.fields import BLANK_CHOICE_DASH
from django.utils.translation import ugettext_lazy as _

from mezzanine.core.admin import TranslationAdmin, TabularDynamicInlineAdmin
from mezzanine.core.forms import DynamicInlineAdminForm

from .models import (ProductAttribute, ChoiceAttribute, ChoiceAttributeOption,
                     StringAttribute, LettersAttribute, ListAttribute)


class AttributeAdmin(TranslationAdmin):
    list_display = ('name', 'required', 'visible')
    list_editable = ('required', 'visible')
    list_filter = ('required', 'visible')
    ordering = ('name',)


class ChoiceAttributeOptionInline(TabularDynamicInlineAdmin):
    model = ChoiceAttributeOption


class ChoiceAttributeAdmin(AttributeAdmin):
    inlines = (ChoiceAttributeOptionInline,)


class StringAttributeAdmin(AttributeAdmin):
    string_fields = ['max_length']
    list_display = list(AttributeAdmin.list_display) + string_fields
    list_editable = list(AttributeAdmin.list_editable) + string_fields


class LettersAttributeAdmin(StringAttributeAdmin):
    letters_fields = ['free_characters']
    list_display = list(StringAttributeAdmin.list_display) + letters_fields
    list_editable = list(StringAttributeAdmin.list_editable) + letters_fields


class ProductAttributeForm(DynamicInlineAdminForm):
    # Display attributes as type / name in a single list.

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

        super(ProductAttributeForm, self).__init__(*args, **kwargs)

        if self.prefix.startswith('attributes-'):
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


class ProductAttributeAdmin(TabularDynamicInlineAdmin):
    model = ProductAttribute
    form = ProductAttributeForm

    def get_fieldsets(self, req, obj=None):
        fieldsets = super(ProductAttributeAdmin, self).get_fieldsets(req, obj)
        fields = fieldsets[0][1]['fields']
        # Hide type / id fields, but keep the processing they provide.
        fields.remove('attribute_type')
        fields.remove('attribute_id')
        # Workaround for https://code.djangoproject.com/ticket/12238.
        fields.insert(0, 'attribute')
        return fieldsets


admin.site.register(ChoiceAttribute, ChoiceAttributeAdmin)
admin.site.register(StringAttribute, StringAttributeAdmin)
admin.site.register(LettersAttribute, LettersAttributeAdmin)
admin.site.register(ListAttribute)
