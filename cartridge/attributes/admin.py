from django.contrib import admin
from django.db.models import ImageField

from mezzanine.core.admin import TranslationAdmin, TabularDynamicInlineAdmin

from cartridge.shop.forms import ImageWidget

from .models import (ProductAttribute, ChoiceAttribute, ChoiceAttributeOption,
                     StringAttribute, LettersAttribute, ListAttribute,
                     ImageAttribute)
from .forms import AttributeSelectionForm, ProductAttributeForm


class AttributeAdmin(TranslationAdmin):
    list_display = ('name', 'required', 'visible')
    list_editable = ('required', 'visible')
    list_filter = ('required', 'visible')
    ordering = ('name',)

    class Media:
        css = {'all': ('admin/css/attribute.css',)}


class ChoiceAttributeOptionInline(TabularDynamicInlineAdmin):
    model = ChoiceAttributeOption
    formfield_overrides = {ImageField: {'widget': ImageWidget}}


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


def attribute_fieldsets(fieldsets):
    # Hide type / id fields, but keep the processing they provide.
    fields = fieldsets[0][1]['fields']
    index = fields.index('attribute_type')
    fields.remove('attribute_type')
    fields.remove('attribute_id')
    # Workaround for https://code.djangoproject.com/ticket/12238.
    fields.insert(index, 'attribute')
    return fieldsets


class ListAttributeAdmin(AttributeAdmin):
    model = ListAttribute
    form = AttributeSelectionForm
    list_fields = ['attribute']
    list_display = list(AttributeAdmin.list_display) + list_fields

    def get_fieldsets(self, request, obj=None):
        return attribute_fieldsets(
            super(ListAttributeAdmin, self).get_fieldsets(request, obj))


class ProductAttributeAdmin(TabularDynamicInlineAdmin):
    model = ProductAttribute
    form = ProductAttributeForm

    def get_fieldsets(self, request, obj=None):
        return attribute_fieldsets(
            super(ProductAttributeAdmin, self).get_fieldsets(request, obj))


admin.site.register(ChoiceAttribute, ChoiceAttributeAdmin)
admin.site.register(StringAttribute, StringAttributeAdmin)
admin.site.register(LettersAttribute, LettersAttributeAdmin)
admin.site.register(ListAttribute, ListAttributeAdmin)
admin.site.register(ImageAttribute, AttributeAdmin)
