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

from cartridge.shop import fields
from cartridge.shop.models import (Product, CartItem, OrderItem)

# Used to limit choices in generic relations.
ATTRIBUTE_TYPES = Q(
    app_label='attributes', model__in=('choiceattribute', 'stringattribute',
                                       'lettersattribute', 'listattribute',
                                       'imageattribute'))
VALUE_TYPES = Q(
    app_label='attributes', model__in=('choiceattributevalue',
                                       'stringattributevalue',
                                       'lettersattributevalue',
                                       'listattributevalue',
                                       'imageattributevalue'))


class Attribute(models.Model):
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
        verbose_name = _("product attribute")
        verbose_name_plural = _("product attributes")

    def __unicode__(self):
        return unicode(u'{}: {}'.format(self.product, self.attribute))


class AttributeValue(models.Model):
    # Common interface of all values.
    class Meta:
        abstract = True

    def __nonzero__(self):
        # If bool(value) is False it's considered undefined and not saved.
        return super(AttributeValue, self).__nonzero__()

    def price(self, variation):
        # Added to unit price.
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
        abstract = True

    def __unicode__(self):
        return unicode(u'{}: {}'.format(self.value.attribute, self.value))


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


class ChoiceAttribute(Attribute):
    class Meta:
        verbose_name = _("choice attribute")
        verbose_name_plural = _("choice attributes")

    def field(self):
        options = ChoiceAttributeOption.objects.filter(attribute=self)
        choices = BLANK_CHOICE_DASH[:] + [o.choice() for o in options]
        return forms.ChoiceField(label=self.name, choices=choices,
                                 required=self.required)

    def make_value(self, value):
        option = ChoiceAttributeOption.objects.get(pk=value)
        return ChoiceAttributeValue(option=option)


class ChoiceAttributeOption(Orderable):
    attribute = models.ForeignKey(ChoiceAttribute,
        help_text=_("What attribute is this value for?"))
    option = models.CharField(_("Option"), max_length=255,
        help_text=_("Potential value of the attribute."))
    price = fields.MoneyField(_("Price change"), null=True, blank=True,
        help_text=_("Unit price will be modified by this amount, "
                    "if the option is chosen."))

    class Meta:
        order_with_respect_to = 'attribute'
        verbose_name = _("choice option")
        verbose_name_plural = _("choice options")

    def __unicode__(self):
        return u'{}: {}'.format(self.attribute, self.option)

    def choice(self):
        context = {'option': self.option, 'price': self.price}
        template = 'attributes/choice_option.html'
        return (self.id, render_to_string(template, context))


class ChoiceAttributeValue(AttributeValue):
    option = models.ForeignKey(ChoiceAttributeOption, verbose_name=_("Option"))

    def __getattr__(self, name):
        # We don't know the attribute, but the option does.
        if name == 'attribute':
            return self.option.attribute
        else:
            raise AttributeError

    def __nonzero__(self):
        # If bool(value) is False it's considered undefined and not saved.
        return self.option is not None

    def __unicode__(self):
        return unicode(self.option.option)

    def price(self, variation):
        return self.option.price


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

    def make_value(self, value):
        return StringAttributeValue(attribute=self, string=value)


class StringAttributeValue(AttributeValue):
    attribute = models.ForeignKey(StringAttribute)
    string = models.TextField(_("String"))

    def __nonzero__(self):
        return bool(self.string)

    def __unicode__(self):
        return self.string


class LettersAttribute(StringAttribute):
    # Product unit price based on length.
    free_characters = models.CharField(_("Free characters"), max_length=50,
        blank=True,
        help_text=_("Characters excluded from the price calculation "
                    "(regular expression)."))

    class Meta:
        verbose_name = _("letters attribute")
        verbose_name_plural = _("letters attributes")

    def make_value(self, value):
        return LettersAttributeValue(attribute=self, string=value)


class LettersAttributeValue(StringAttributeValue):
    def price(self, variation):
        string = self.string
        if self.attribute.free_characters:
            string = re.sub(self.attribute.free_characters, '', string)
        return (len(string) - 1) * variation.price()


class ListAttribute(Attribute):
    # Multiple values for a single attribute.
    attribute_type = models.ForeignKey(ContentType,
                                       limit_choices_to=ATTRIBUTE_TYPES)
    attribute_id = models.IntegerField()
    attribute = generic.GenericForeignKey('attribute_type', 'attribute_id')
    separator = models.CharField(_("Values separator"),
        max_length=10, default=', ',
        help_text=_("Character or string used to separate values when "
                    "parsing posted string. Must be guaranteed not to "
                    "appear in string representation of any single value."))

    class Meta:
        verbose_name = _("list attribute")
        verbose_name_plural = _("list attributes")

    def field(self):
        return forms.CharField(label=self.name, required=self.required)

    def make_value(self, value):
        tokens = value.split(self.separator)
        values = [self.attribute.make_value(t) for t in tokens]
        return ListAttributeValue(attribute=self, values=values)


class ListAttributeValue(AttributeValue):
    # Combines a set of other attribute values into a list behaving as
    # a single value.
    attribute = models.ForeignKey(ListAttribute)

    # Placeholder for unsaved subvalues.
    _values = None

    def __init__(self, *args, **kwargs):
        # Temporarily stores values on an instance variable, so we
        # can save the list and its element together.
        self._values = kwargs.pop('values')
        super(ListAttributeValue, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        # Saves list elements, after saving the list model.
        super(ListAttributeValue, self).save(*args, **kwargs)
        if self._values:
            for value in self._values[:]:
                try:
                    value.save(*args, **kwargs)
                except:
                    raise
                else:
                    self._values = self._values[1:]

    def __nonzero__(self):
        return any(self.values.all())

    def __unicode__(self):
        return self.attribute.separator.join(self.values.all())

    def price(self, variation):
        return sum(v.price(variation) for v in self.values.all())

    def digest(self):
        return self.attribute.separator.join(
            v.digest() for v in self.values.all())


class ListAttributeValueValue(models.Model):
    # One of values on the list.

    list = models.ForeignKey(ListAttributeValue, related_name='values')
    value_type = models.ForeignKey(ContentType,
                                   limit_choices_to=VALUE_TYPES)
    value_id = models.IntegerField()
    value = generic.GenericForeignKey('value_type', 'value_id')

    class Meta:
        order_with_respect_to = 'list'


class ImageAttribute(Attribute):
    class Meta:
        verbose_name = _("image attribute")
        verbose_name_plural = _("image attributes")

    def field(self):
        return forms.ImageField(label=self.name, required=self.required)

    def make_value(self, value):
        return ImageAttributeValue(attribute=self, image=value)


class ImageAttributeValue(AttributeValue):
    attribute = models.ForeignKey(StringAttribute)
    image = models.ImageField(upload_to=upload_to(
        'attributes.ImageAttributeValue.image', 'attributes'))

    def __nonzero__(self):
        return bool(self.image)

    def __unicode__(self):
        return self.image


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
