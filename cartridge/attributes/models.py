import hashlib
import re

from django import forms
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.db.models.fields import BLANK_CHOICE_DASH
from django.template.loader import render_to_string
from django.utils.translation import ugettext, ugettext_lazy as _

from mezzanine.core.models import Orderable
from mezzanine.utils.models import upload_to
from mezzanine.utils.translation import for_all_languages

from cartridge.shop import fields
from cartridge.shop.models import Product, SelectedProduct

from .managers import PolymorphicManager


# TODO: Get rid of the digests -- code full value comparisons.


# Which attributes may be assigned to products, limits and orders choices in
# product attribute inline.
# TODO: Should be a non-editable setting.
PRODUCT_ATTRIBUTES_ORDER = (
    'stringattribute', 'charactersattribute',
    'simplechoiceattribute', 'imagechoiceattribute', 'colorchoiceattribute',
    'subproductchoiceattribute', 'subproductimagechoiceattribute',
    'imageattribute', 'listattribute')
ATTRIBUTE_TYPES = Q(app_label='attributes', model__in=PRODUCT_ATTRIBUTES_ORDER)


class PolymorphicModel(models.Model):
    # Simplistic implementation of dynamic model typecasting.
    content_type = models.ForeignKey(ContentType, editable=False)

    objects = PolymorphicManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not hasattr(self, 'content_type'):
            self.content_type = ContentType.objects.get_for_model(
                self.__class__, for_concrete_model=False)
        return super(PolymorphicModel, self).save(*args, **kwargs)

    def as_content_type(self):
        return self.content_type.get_object_for_this_type(pk=self.pk)


class Attribute(PolymorphicModel):
    # Needs to implement make_value that creates a value object from
    # cleaned form data.
    name = models.CharField(_("Name"), max_length=255,
        help_text=_("Attribute kind such as color, size etc."))
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
        return '{}_{}'.format(self.__class__.__name__.lower(), self.id)

    def digest(self):
        # Digests are used to generate attribute hashes, to easily check
        # if attribute sets match.
        return self.field_name()

    def products(self):
        """
        Returns all products this attribute is assigned to.
        """
        attribute_type = ContentType.objects.get_for_model(
            self, for_concrete_model=False)
        return Product.objects.filter(
            attributes__attribute_type=attribute_type,
            attributes__attribute_id=self.id)


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


class AttributeValue(PolymorphicModel):
    # Attribute values can't relate to attributes or options, as they
    # may persist past their deletion, so only attribute name is saved.
    # The base class stores content type, so we can get hold of
    # the leaf models using relation from items.
    # If bool(value) is False the value is considered undefined and not saved,
    # unicode(value) should return a string suitable for cart description.
    attribute = models.CharField(max_length=255)
    visible = models.BooleanField()
    item_type = models.ForeignKey(ContentType,
                                  related_name='attributevalue_items_set')
    item_id = models.IntegerField()
    item = generic.GenericForeignKey('item_type', 'item_id')

    def __init__(self, *args, **kwargs):
        # Copies all translations of attribute name.
        attribute = kwargs.get('attribute', None)
        super(AttributeValue, self).__init__(*args, **kwargs)
        if isinstance(attribute, Attribute):
            def set_attribute():
                self.attribute = attribute.name
            for_all_languages(set_attribute)
            self.visible = attribute.visible

    def __getattr__(self, name):
        # Default to zero price (some subclasses have a price field).
        if name == 'price':
            return 0
        raise AttributeError

    def digest(self):
        # Used to check if a product with the same attributes / values is
        # in the cart.
        return unicode(self).encode('unicode_escape')

    def process_subproduct_attributes(self, subproducts):
        """
        For subproduct value assigns subproduct attribute values to the value.
        The argument may be a list of attribute values dicts (for a list of
        subproducts) or just a single dict.
        """
        raise AttributeError("Only to be used with subproduct values.")


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

    def make_value(self, value, product):
        return StringValue(attribute=self, string=value)


class StringValue(AttributeValue):
    string = models.TextField()

    def __nonzero__(self):
        return bool(self.string)

    def __unicode__(self):
        return unicode(self.string)


class CharactersAttribute(StringAttribute):
    # Product unit price based on length.
    free_characters = models.CharField(_("Free characters"), max_length=50,
        blank=True,
        help_text=_("Characters excluded from the price calculation "
                    "(regular expression)."))

    class Meta:
        verbose_name = _("characters attribute")
        verbose_name_plural = _("characters attributes")

    def make_value(self, value, product):
        characters = value
        if self.free_characters:
            characters = re.sub(self.free_characters, '', characters)
        price = (len(characters) - 1) * product.price()
        return CharactersValue(attribute=self, price=price, string=value,
                               free_characters=self.free_characters)


class CharactersValue(StringValue):
    free_characters = models.CharField(max_length=50)
    price = fields.MoneyField()


class ChoiceAttribute(Attribute):
    def field(self):
        choices = BLANK_CHOICE_DASH[:]
        for group in self.groups.all():
            choices_group = tuple(o.choice() for o in group.options.all())
            choices.append((group.name, choices_group))
        choices.extend(
            o.choice() for o in self.options.filter(group__isnull=True))
        return forms.ChoiceField(label=self.name, choices=choices,
                                 required=self.required)

    def make_value(self, value, product):
        if value != '':
            option = self.options.get(pk=value)
        else:
            option = None
        return ChoiceValue(attribute=self, option=option)


class ChoiceOptionsGroup(Orderable):
    attribute = models.ForeignKey(ChoiceAttribute, related_name='groups',)
    name = models.CharField(_("Name"), max_length=255,
        help_text=_("Group name displayed as a heading in selection boxes."))

    class Meta:
        order_with_respect_to = 'attribute'
        verbose_name = _("options group")
        verbose_name_plural = _("options groups")

    def __unicode__(self):
        return unicode(self.name)


class ChoiceOption(PolymorphicModel):
    attribute = models.ForeignKey(ChoiceAttribute, related_name='options')
    group = models.ForeignKey(ChoiceOptionsGroup, related_name='options',
        null=True, blank=True,
        help_text=_("Group this option together with some other options. "
                    "After creating new groups you need to save before they "
                    "are available for selection."))
    name = models.CharField(_("Option"), max_length=255,
        help_text=_("Potential value of the attribute."))
    price = fields.MoneyField(_("Price change"), default=0,
        help_text=_("Unit price will be modified by this amount, "
                    "if the option is chosen."))

    class Meta:
        order_with_respect_to = 'attribute'
        verbose_name = _("choice option")
        verbose_name_plural = _("choice options")

    def __unicode__(self):
        if self.group:
            return u'{}, {}'.format(self.group, self.name)
        else:
            return unicode(self.name)

    def choice(self):
        context = {'name': self.name, 'price': self.price}
        template = 'attributes/includes/choice_option.html'
        return (self.id, render_to_string(template, context))


class ChoiceValue(AttributeValue):
    # Option name and price from the time of creation.
    group = models.CharField(max_length=255, default='')
    option = models.CharField(max_length=255, default='')
    price = fields.MoneyField(default=0)

    def __init__(self, *args, **kwargs):
        option = kwargs.get('option', None)
        super(ChoiceValue, self).__init__(*args, **kwargs)
        if isinstance(option, ChoiceOption):
            def set_group_option():
                self.group = option.group.name if option.group else ''
                self.option = option.name
            for_all_languages(set_group_option)
            self.price = option.price

    def __nonzero__(self):
        return bool(self.option)

    def __unicode__(self):
        return unicode(self.option)


class SimpleChoiceAttribute(ChoiceAttribute):
    """
    Basic choice option, knows the attribute and group it belongs to, has
    display name and may have a price. This submodel is needed to separate
    different choice attributes in administration.
    """
    class Meta:
        proxy = True
        verbose_name = _("simple choice attribute")
        verbose_name_plural = _("simple choice attributes")


class ImageChoiceAttribute(ChoiceAttribute):
    """
    Adds image illustration for choice options, the images are uploaded for
    options and not stored with values.
    """
    class Meta:
        proxy = True
        verbose_name = _("image choice attribute")
        verbose_name_plural = _("image choice attributes")


class ImageChoiceOption(ChoiceOption):
    image = models.ImageField(_("Image"), null=True, blank=True,
        upload_to=upload_to('attributes.ImageChoiceOption.image',
                            'attributes/image_choice'),
        help_text=_("Image presenting the option."))


class ColorChoiceAttribute(ChoiceAttribute):
    """
    Extends choice options with encoded colors.
    """
    class Meta:
        proxy = True
        verbose_name = _("color choice attribute")
        verbose_name_plural = _("color choice attributes")


class ColorChoiceOption(ChoiceOption):
    color = models.CharField(_("Color"), max_length=20,
        help_text=_("Choosable color (in #RRGGBB notation)."))


class SubproductChoiceAttribute(ChoiceAttribute):
    """
    Product as an attribute of another product. Intended as a
    way of realizing product sets. Inbuilt form only supports
    subproducts without attributes.
    """
    class Meta:
        proxy = True
        verbose_name = _("subproduct choice attribute")
        verbose_name_plural = _("subproduct choice attributes")

    def make_value(self, value, product):
        if value != '':
            option = self.options.get(pk=value)
        else:
            option = None
        return SubproductChoiceValue(attribute=self, option=option)


class SubproductChoiceOption(ChoiceOption):
    """
    A product available for choice as an attribute value (assumed to have
    just a single variation). Parent's name is ignored and product's name
    is used instead.
    """
    subproduct = models.ForeignKey(Product,
        help_text=_("Another product, being a part or add-on for the main "
                    "product (the product the attribute is assigned to)."))

    @property
    def name(self):
        return unicode(self.subproduct.variations.all()[0])

    @name.setter
    def name(self, value):
        pass

    def choice(self):
        """
        Price displayed is product's price plus options price.
        """
        variation = self.subproduct.variations.all()[0]
        context = {'name': self.name, 'price': variation.price() + self.price}
        template = 'attributes/includes/choice_option.html'
        return (self.id, render_to_string(template, context))


class SubproductChoiceValue(ChoiceValue, SelectedProduct):
    """
    Attribute values of the subproduct use this model as the target
    for their ``item`` relation -- where for the top level products they
    would point to ``CartItem`` or ``OrderItem`` objects.
    """
    def __init__(self, *args, **kwargs):
        """
        Does all that ``cart.add_item`` does, except for saving attribute
        values.
        """
        option = kwargs.get('option', None)
        quantity = kwargs.pop('quantity', 1)
        super(SubproductChoiceValue, self).__init__(*args, **kwargs)
        if isinstance(option, SubproductChoiceOption):
            variation = option.subproduct.variations.all()[0]
            self.sku = variation.sku
            self.unit_price = variation.price()
            self.price = self.unit_price

            def set_description():
                self.description = unicode(variation)
            for_all_languages(set_description)
            self.quantity = quantity

    def save(self, *args, **kwargs):
        """
        Saves attribute values pointing at this subproduct.
        """
        super(SubproductChoiceValue, self).save(*args, **kwargs)
        for attribute, value in self._attribute_values.iteritems():
            value.item = value.item  # TODO: A bit surprising... Item is set
                                     #       in process_subproduct_attributes,
                                     #       but item_id doesn't get set.
            value.save()
        self._attribute_values = {}

    def __unicode__(self):
        text = unicode(self.option)
        vavs = self.visible_attribute_values()
        if vavs:
            text += u' ({})'.format(u'; '.join(unicode(v) for v in vavs))
        return text

    def digest(self):
        """
        Products with differing subproduct attributes differ.
        """
        return '{} ({})'.format(
            super(SubproductChoiceValue, self).digest(),
            ', '.join(v.digest() for a, v
                      in self._attribute_values.iteritems()))

    def process_subproduct_attributes(self, subproducts):
        """
        Stores subproduct attributes for saving (when we are saved).
        Sets item of subproduct values and updates price.

        ``Subproducts`` is expected be an (option id, attribute_values) tuple.
        """
        self._attribute_values = subproducts[1]
        for attribute, value in self._attribute_values.iteritems():
            value.item = self
            self.unit_price += value.price
            self.price += value.price


class SubproductImageChoiceAttribute(SubproductChoiceAttribute):
    """
    Subproduct choice with an additional image for illustration.
    """
    class Meta:
        proxy = True
        verbose_name = _("subproduct image choice attribute")
        verbose_name_plural = _("subproduct image choice attributes")


class SubproductImageChoiceOption(SubproductChoiceOption):
    image = models.ImageField(_("Image"), null=True, blank=True,
        upload_to=upload_to('attributes.SubproductImageChoiceOption.image',
                            'attributes/subproduct_image_choice'),
        help_text=_("Additional image illustrating the subproduct."))


class ImageAttribute(Attribute):
    """
    Allows users to upload an image to attach to the product.
    """
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

    def make_value(self, value, product):
        if (self.max_size > 0 and value and
                value._size > self.max_size * 1024 * 1024):
            raise forms.ValidationError(_("Uploaded image can't be larger "
                                          "than {} MB.").format(self.max_size))
        return ImageValue(attribute=self, image=value,
                          item_image=self.item_image)


class ImageValue(AttributeValue):
    image = models.ImageField(upload_to=upload_to(
        'attributes.ImageValue.image', 'attributes/image'))
    item_image = models.BooleanField()

    def __init__(self, *args, **kwargs):
        item_image = kwargs.get('item_image', None)
        super(ImageValue, self).__init__(*args, **kwargs)
        if item_image:
            self.visible = False

    def __nonzero__(self):
        return bool(self.image)

    def __unicode__(self):
        return self.image.name


class ListAttribute(Attribute):
    # Multiple values for a single attribute.
    attribute_type = models.ForeignKey(ContentType,
                                       limit_choices_to=ATTRIBUTE_TYPES,
                                       related_name='list_attributes')
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

    def save(self, *args, **kwargs):
        # Ensure related attributes don't make a cycle.
        attribute = self.attribute
        while attribute is not None:
            if (attribute.__class__ == self.__class__ and
                    attribute.pk == self.pk):
                raise AttributeError("You can't set list attribute's related "
                                     "attribute to the list attribute itself "
                                     "or any attribute that relates to it.")
            try:
                attribute = attribute.attribute
            except AttributeError:
                break
        super(ListAttribute, self).save(*args, **kwargs)

    def field(self):
        return forms.CharField(label=self.name, required=self.required)

    def make_value(self, value, product):
        tokens = value.split(self.separator)
        values = []
        field = self.attribute.field()
        make_value = self.attribute.make_value
        for token in tokens:
            value = make_value(field.clean(token.strip()), product)
            value.visible = False
            values.append(value)
        return ListValue(attribute=self, values=values,
                         separator=self.separator)


class ListValue(AttributeValue):
    # Combines a set of other attribute values into a list behaving as
    # a single value.
    separator = models.CharField(max_length=10)

    def __init__(self, *args, **kwargs):
        # Temporarily stores values on an instance variable, so we
        # can save the list and its elements together.
        self._values = kwargs.pop('values', [])
        super(ListValue, self).__init__(*args, **kwargs)

    def __nonzero__(self):
        return any(self.subvalues())

    def __unicode__(self):
        return self.separator.join(
            unicode(v) if v is not None else ugettext("none")
            for v in self.subvalues())

    def save(self, *args, **kwargs):
        # Saves list elements, after saving the list model.
        super(ListValue, self).save(*args, **kwargs)
        for value in self._values:
            if value:
                value.item = self.item
                value.save(*args, **kwargs)
                ListSubvalue.objects.create(list_value=self, value=value)
            else:
                # Not passing value=None is a workaround for
                # https://code.djangoproject.com/ticket/7551.
                ListSubvalue.objects.create(list_value=self)
        self._values = []

    @property
    def price(self):
        return sum(v.price for v in self.subvalues())

    def digest(self):
        return self.separator.join(v.digest() for v in self.subvalues())

    def subvalues(self):
        """
        Yields unsaved and then saved subvalues on the list.
        """
        for value in self._values:
            yield value
        for value in self.values.all():
            yield value.value

    def process_subproduct_attributes(self, subproducts):
        """
        Processes subproduct attributes for each subvalue.

        ``Subproducts`` should be a list of subproducts with entries
        suitable for processing by subvalues.
        """
        for subvalue, subproduct in zip(self.subvalues(), subproducts):
            subvalue.process_subproduct_attributes(subproduct)


class ListSubvalue(models.Model):
    # One of values on the list.
    list_value = models.ForeignKey(ListValue, related_name='values')
    value_type = models.ForeignKey(ContentType, null=True)
    value_id = models.IntegerField(null=True)
    value = generic.GenericForeignKey('value_type', 'value_id')

    class Meta:
        order_with_respect_to = 'list_value'


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
