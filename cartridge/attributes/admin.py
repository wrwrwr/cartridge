from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse
from django.db.models import ImageField
from django.utils.html import format_html, format_html_join
from django.utils.translation import ugettext_lazy as _

from mezzanine.core.admin import (TranslationAdmin,
                                  TranslationInlineModelAdmin,
                                  TabularDynamicInlineAdmin)

from cartridge.shop.forms import ImageWidget

from .models import (
    ProductAttribute,
    StringAttribute, CharactersAttribute,
    ChoiceOption, ChoiceOptionsGroup, SimpleChoiceAttribute,
    ImageChoiceAttribute, ImageChoiceOption,
    ColorChoiceAttribute, ColorChoiceOption,
    ImageAttribute, ListAttribute)
from .forms import AttributeSelectionForm, ProductAttributeForm


class PolymorphicAdmin(admin.ModelAdmin):
    """
    Filters objects to just those that match admin model's
    content type.
    """
    def queryset(self, request):
        content_type = ContentType.objects.get_for_model(
            self.model, for_concrete_model=False)
        print self.model, repr(content_type)
        return self.model.objects.filter(content_type=content_type)


class AttributeAdmin(TranslationAdmin):
    list_display = ('name', 'product_links', 'required', 'visible')
    list_editable = ('required', 'visible')
    list_filter = ('required', 'visible')
    ordering = ('name',)

    class Media:
        css = {'all': ('admin/css/attribute.css',)}

    def product_links(self, attribute):
        """
        Links to all products the attribute or list attribute relating to it
        are assigned to.
        """
        attributes = [attribute]
        products = []
        while attributes:
            attribute = attributes.pop()
            attribute_type = ContentType.objects.get_for_model(
                attribute, for_concrete_model=False)
            print attribute, attribute_type, attribute.products()
            attributes.extend(
                ListAttribute.objects.filter(attribute_type=attribute_type,
                                             attribute_id=attribute.id))
            products.extend(attribute.products())
        return format_html_join(u', ', u'<a href="{}">{}</a>',
            ((reverse('admin:shop_product_change', args=(p.id,)), p.title)
             for p in products))
    product_links.short_description = _("Products")


class StringAttributeAdmin(AttributeAdmin):
    string_fields = ['max_length']
    list_display = list(AttributeAdmin.list_display) + string_fields
    list_editable = list(AttributeAdmin.list_editable) + string_fields


class CharactersAttributeAdmin(StringAttributeAdmin):
    letters_fields = ['free_characters']
    list_display = list(StringAttributeAdmin.list_display) + letters_fields
    list_editable = list(StringAttributeAdmin.list_editable) + letters_fields


class TabularTranslationInline(TabularDynamicInlineAdmin,
                               TranslationInlineModelAdmin):
    pass


class ChoiceOptionsGroupInline(TabularTranslationInline):
    model = ChoiceOptionsGroup


class SimpleChoiceOptionInline(TabularTranslationInline):
    model = ChoiceOption


class SimpleChoiceAttributeAdmin(PolymorphicAdmin, AttributeAdmin):
    inlines = (ChoiceOptionsGroupInline, SimpleChoiceOptionInline)


class ImageChoiceOptionInline(TabularTranslationInline):
    model = ImageChoiceOption
    formfield_overrides = {ImageField: {'widget': ImageWidget}}


class ImageChoiceAttributeAdmin(PolymorphicAdmin, AttributeAdmin):
    inlines = (ChoiceOptionsGroupInline, ImageChoiceOptionInline)


class ColorChoiceOptionInline(TabularTranslationInline):
    model = ColorChoiceOption


class ColorChoiceAttributeAdmin(PolymorphicAdmin, AttributeAdmin):
    inlines = (ChoiceOptionsGroupInline, ColorChoiceOptionInline)


def attribute_fieldsets(fieldsets):
    # Hide type / id fields, but keep the processing they provide.
    fields = fieldsets[0][1]['fields']
    fields.remove('attribute_type')
    fields.remove('attribute_id')
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
    readonly_fields = ('edit',)

    def get_fieldsets(self, request, obj=None):
        return attribute_fieldsets(
            super(ProductAttributeAdmin, self).get_fieldsets(request, obj))

    def edit(self, product_attribute):
        if product_attribute.attribute is not None:
            attribute = product_attribute.attribute
            while True:
                try:
                    attribute = attribute.attribute
                except AttributeError:
                    break
            app = attribute._meta.app_label
            model = attribute.__class__.__name__.lower()
            id = attribute.id
            return format_html(
                u'<a href="{}" title="{}" class="changelink"> </a>',
                reverse('admin:{}_{}_change'.format(app, model), args=(id,)),
                _("Edit"))
        else:
            return ''
    edit.short_description = _("Edit")
    edit.allow_tags = True


admin.site.register(StringAttribute, StringAttributeAdmin)
admin.site.register(CharactersAttribute, CharactersAttributeAdmin)
#admin.site.register(ChoiceAttribute, ChoiceAttributeAdmin)
admin.site.register(SimpleChoiceAttribute, SimpleChoiceAttributeAdmin)
admin.site.register(ImageChoiceAttribute, ImageChoiceAttributeAdmin)
admin.site.register(ColorChoiceAttribute, ColorChoiceAttributeAdmin)
admin.site.register(ImageAttribute, AttributeAdmin)
admin.site.register(ListAttribute, ListAttributeAdmin)
