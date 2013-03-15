import hashlib
import re

from django import forms
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.db.models.fields import BLANK_CHOICE_DASH
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

from mezzanine.core.models import Orderable
from mezzanine.utils.models import upload_to
from mezzanine.utils.translation import for_all_languages

from cartridge.shop import fields
from cartridge.shop.models import (Product, CartItem, OrderItem)


# Used to limit choices in generic relations.
#       Non-editable setting maybe?
ATTRIBUTE_TYPES = Q(app_label='attributes', model__in=(
    'stringattribute', 'charactersattribute',
    'simplechoiceattribute', 'imagechoiceattribute', 'colorchoiceattribute',
    'imageattribute', 'listattribute'))
VALUE_TYPES = Q(app_label='attributes', model__in=(
    'stringvalue', 'charactersvalue',
    'choicevalue', 'imagevalue', 'listvalue'))


class Attribute(models.Model):
    # Needs to implement make_value that creates a value object from
    # cleaned form data.
    name = models.CharField(_("Name"), max_length=255,
        help_text=_("Attribute kind such as colour, size etc."))
    required = models.BooleanField(_("Required"), default=True,
        help_text=_("Can the client leave this attribute unspecified?"))
    visible = models.BooleanField(_("Visible"), default=True,
        help_text=_("Should this attribute be visible in cart?"))

    class Meta:
        abstract = True

    def __unicode__(self):
        return unicode(self.name)

    def field_name(self):
        # Field names can't contain Unicode, punycode would be another
        # possible choice.
        return self.name.encode('unicode_escape')

    def digest(self):
        # Digests are used to generate attribute hashes, to easily check
        # if attribute sets match.
        return self.field_name()


class ProductAttribute(Orderable):
    # Attribute assigned to a product.
    product = models.ForeignKey(Product, related_name='attributes')
    attribute_type = models.ForeignKey(ContentType,
                                       limit_choices_to=ATTRIBUTE_TYPES)
    attribute_id = models.IntegerField()
    attribute = generic.GenericForeignKey('attribute_type', 'attribute_id')

    class Meta:
        unique_together = ('product', 'attribute_type', 'attribute_id')
        verbose_name = _("product attribute")
        verbose_name_plural = _("product attributes")

    def __unicode__(self):
        return u'{}: {}'.format(self.product, self.attribute)


class AttributeValue(models.Model):
    # Attribute values can't relate to attributes or options, as they
    # may persist past their deletion.
    # If bool(value) is False the value is considered undefined and not saved,
    # unicode(value) should return a string suitable for cart description.
    attribute = models.CharField(_("Attribute name"), max_length=255)

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        # Copies all translations of attribute name.
        attribute = kwargs.pop('attribute')
        super(AttributeValue, self).__init__(*args, **kwargs)
        def set_attribute():
            self.attribute = attribute.name
        for_all_languages(set_attribute)

    def price(self):
        return 0

    def digest(self):
        # Used to check if a product with the same attributes / values is
        # in the cart.
        return unicode(self).encode('unicode_escape')


class ItemAttributeValue(models.Model):
    # Attribute value assigned to a cart or order item
    # (or a product variation?).
    value_type = models.ForeignKey(ContentType,
                                   limit_choices_to=VALUE_TYPES)
    value_id = models.IntegerField()
    value = generic.GenericForeignKey('value_type', 'value_id')

    class Meta:
        unique_together = ('item', 'value_type', 'value_id')
        abstract = True

    def __unicode__(self):
        return u'{}: {}'.format(self.value.attribute, self.value)


# TODO: Should allow to (selectively) create variations (filters) for some
#       attribute value sets, thus supporting subproduct sales or stock.
#class VariationAttribute(AttributeValue):
#    variation = models.ForeignKey(ProductVariation,
#        related_name='attribute_values')


class CartItemAttributeValue(ItemAttributeValue):
    item = models.ForeignKey(CartItem, related_name='attribute_values')


# TODO: Hopefully wishlists will become storable some day.
#class WishlistItemAttributeValue(ItemAttributeValue):
#    item = models.ForeignKey(WishlistItem, related_name='attribute_values')


class OrderItemAttributeValue(ItemAttributeValue):
    item = models.ForeignKey(OrderItem, related_name='attribute_values')


class StringAttribute(Attribute):
    max_length = models.PositiveIntegerField(_("Max length"),
        null=True, blank=True,
        help_text=_("Maximum number of characters a client can enter. "
                    "Leave blank if you don't want to limit the text length."))

    class Meta:
        verbose_name = _("string attribute")
        verbose_name_plural = _("string attributes")

    def field(self):
        return forms.CharField(label=self.name, max_length=self.max_length,
                               required=self.required)

    def make_value(self, value, variation):
        return StringValue(attribute=self, string=value)


class StringValue(AttributeValue):
    string = models.TextField()

    def __nonzero__(self):
        return bool(self.string)

    def __unicode__(self):
        return self.string


class CharactersAttribute(StringAttribute):
    # Product unit price based on length.
    free_characters = models.CharField(_("Free characters"), max_length=50,
        blank=True,
        help_text=_("Characters excluded from the price calculation "
                    "(regular expression)."))

    class Meta:
        verbose_name = _("characters attribute")
        verbose_name_plural = _("characters attributes")

    def make_value(self, value, variation):
        characters = value
        if self.free_characters:
            characters = re.sub(self.free_characters, '', characters)
        price = (len(characters) - 1) * variation.price()
        return CharactersValue(attribute=self, price=price, string=value,
                               free_characters=self.free_characters)


class CharactersValue(StringValue):
    free_characters = models.CharField(max_length=50)
    price = fields.MoneyField()

    def price(self):
        return self.price


class ChoiceAttribute(Attribute):
    def field(self):
        choices = BLANK_CHOICE_DASH[:]
        for group in self.groups.all():
            choices_group = tuple(o.choice() for o in group.options.all())
            choices.append((group.name, choices_group))
        else:
            choices.extend(o.choice() for o in self.options.all())
        return forms.ChoiceField(label=self.name, choices=choices,
                                 required=self.required)

    def make_value(self, value, variation):
        option = ChoiceOption.objects.get(pk=value)
        return ChoiceValue(option=option)


class ChoiceOptionsGroup(Orderable):
    attribute = models.ForeignKey(ChoiceAttribute, related_name='groups',
        help_text=_("What attribute is this option group of?"))
    name = models.CharField(_("Name"), max_length=255,
        help_text=_("Group name displayed as a bold heading in selection "
                    " boxes."))

    class Meta:
        order_with_respect_to = 'attribute'
        verbose_name = _("options group")
        verbose_name_plural = _("options groups")


class ChoiceOption(Orderable):
    attribute = models.ForeignKey(ChoiceAttribute, related_name='options',
        help_text=_("What attribute is this value for?"))
    group = models.ForeignKey(ChoiceOptionsGroup, related_name='options',
        null=True, blank=True,
        help_text=_("Group this option together with some other options. "
                    "After creating new groups you need to save before they "
                    "are available for selection."))
    option = models.CharField(_("Option"), max_length=255,
        help_text=_("Potential value of the attribute."))
    price = fields.MoneyField(_("Price change"), default=0,
        help_text=_("Unit price will be modified by this amount, "
                    "if the option is chosen."))

    class Meta:
        order_with_respect_to = 'attribute'
        verbose_name = _("choice option")
        verbose_name_plural = _("choice options")

    def choice(self):
        context = {'option': self.option, 'price': self.price}
        template = 'attributes/choice_option.html'
        return (self.id, render_to_string(template, context))


class ChoiceValue(AttributeValue):
    # Option name and price from the time of creation.
    group = models.CharField(max_length=255)
    option = models.CharField(max_length=255)
    price = fields.MoneyField()

    def __init__(self, *args, **kwargs):
        option = kwargs.pop('option')
        super(ChoiceValue, self).__init__(*args, **kwargs)
        def set_group_option():
            self.group = option.group.name
            self.option = option.option
        for_all_languages(set_group_option)
        self.price = option.price

    def __nonzero__(self):
        return bool(self.option)

    def __unicode__(self):
        if self.group:
            return u'{}, {}'.format(self.group, self.option)
        else:
            return self.option

    def price(self):
        return self.price


class SimpleChoiceAttribute(ChoiceAttribute):
    # Note that all choice attribute subclasses only offer additional
    # presentation, but store their values as base choice values.
    # TODO: This could be resolved using attribute / group / option factories.
    class Meta:
        verbose_name = _("simple choice attribute")
        verbose_name_plural = _("simple choice attributes")


class ImageChoiceAttribute(ChoiceAttribute):
    class Meta:
        verbose_name = _("image choice attribute")
        verbose_name_plural = _("image choice attributes")


class ImageChoiceOption(ChoiceOption):
    image = models.ImageField(_("Image"), null=True, blank=True,
        upload_to=upload_to('attributes.ImageChoiceOption.image',
                            'attributes/options'),
        help_text=_("Image presenting the option."))


class ColorChoiceAttribute(ChoiceAttribute):
    class Meta:
        verbose_name = _("color choice attribute")
        verbose_name_plural = _("color choice attributes")


class ColorChoiceOption(ChoiceOption):
    color = models.CharField(_("Color"), max_length=20,
        help_text=_("Choosable color (in #RRGGBB notation)."))


class ImageAttribute(Attribute):
    max_size = models.IntegerField(_("Maximum file size"), default=1,
        help_text=_("Maximum size of file users are allowed to upload, "
                    "in megabytes. Zero means no limit."))
    item_image = models.BooleanField(_("Use as item image"), default=True,
        help_text=_("Show the uploaded image instead of item's own image "
                    "in cart."))

    class Meta:
        verbose_name = _("image attribute")
        verbose_name_plural = _("image attributes")

    def field(self):
        return forms.ImageField(label=self.name, required=self.required)

    def make_value(self, value, variation):
        if (self.max_size > 0 and value and
                value._size > self.max_size * 1024 * 1024):
            raise forms.ValidationError(_("Uploaded image can't be larger "
                                          "than {} MB.").format(self.max_size))
        return ImageAttributeValue(attribute=self, image=value)


class ImageValue(AttributeValue):
    image = models.ImageField(upload_to=upload_to(
        'attributes.ImageValue.image', 'attributes/images'))

    def __nonzero__(self):
        return bool(self.image)

    def __unicode__(self):
        return self.image.name


class ListAttribute(Attribute):
    # Multiple values for a single attribute.
    attribute_type = models.ForeignKey(ContentType,
                                       limit_choices_to=ATTRIBUTE_TYPES)
    attribute_id = models.IntegerField()
    attribute = generic.GenericForeignKey('attribute_type', 'attribute_id')
    separator = models.CharField(_("Values separator"),
        max_length=10, default=',',
        help_text=_("Character or string used to separate values when "
                    "parsing posted string. Must be guaranteed not to "
                    "appear in string representation of any single value."))

    class Meta:
        verbose_name = _("list attribute")
        verbose_name_plural = _("list attributes")

    def field(self):
        return forms.CharField(label=self.name, required=self.required)

    def make_value(self, value, variation):
        tokens = value.split(self.separator)
        field = self.attribute.field()
        make_value = self.attribute.make_value
        values = [make_value(field.clean(t.strip()), variation)
                  for t in tokens]
        return ListValue(attribute=self, values=values,
                         separator=self.separator)


class ListValue(AttributeValue):
    # Combines a set of other attribute values into a list behaving as
    # a single value.
    separator = models.CharField(max_length=10)

    # Placeholder for unsaved list elements.
    _values = []

    def __init__(self, *args, **kwargs):
        # Temporarily stores values on an instance variable, so we
        # can save the list and its element together.
        self._values = kwargs.pop('values', [])
        super(ListValue, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        # Saves list elements, after saving the list model.
        super(ListAttributeValue, self).save(*args, **kwargs)
        for value in self._values:
            value.save(*args, **kwargs)
            ListSubvalue.objects.create(list_value=self, value=value)
        self._values = []

    def __nonzero__(self):
        return any(self._values) or any(self.subvalues.all())

    def __unicode__(self):
        return self.separator.join(unicode(v) for v in self.subvalues.all())

    def price(self):
        return sum(v.price() for v in self.subvalues.all())

    def digest(self):
        return self.separator.join(v.digest() for v in self.subvalues.all())


class ListSubvalue(models.Model):
    # One of values on the list. Delegates methods to the actual value.
    list_value = models.ForeignKey(ListValue, related_name='subvalues')
    value_type = models.ForeignKey(ContentType,
                                   limit_choices_to=VALUE_TYPES)
    value_id = models.IntegerField()
    value = generic.GenericForeignKey('value_type', 'value_id')

    class Meta:
        order_with_respect_to = 'list_value'

    def __nonzero__(self):
        return bool(self.value)

    def __unicode__(self):
        return unicode(self.value)

    def price(self):
        return self.value.price()

    def digest(self):
        return self.value.digest()


def attributes_hash(attribute_values):
    """
    Returns a string that can be used to uniquely identify the given attribute
    values set (hashes are used to quickly decide if cart contains an item with
    the same attributes).
    """
    if not attribute_values:
        return ''
    # Strong collision resistance shouldn't be necessary, so MD5 is OK.
    digest = hashlib.md5()
    for attribute, value in attribute_values.iteritems():
        digest.update('{}={}'.format(attribute.digest(), value.digest()))
    return digest.hexdigest()
