from modeltranslation.translator import TranslationOptions, translator

from .models import (
    Attribute, AttributeValue,
    StringAttribute, StringValue, CharactersAttribute, CharactersValue,
    ChoiceAttribute, ChoiceOptionsGroup, ChoiceOption, ChoiceValue,
    SimpleChoiceAttribute,
    ImageChoiceAttribute, ImageChoiceOption,
    ColorChoiceAttribute, ColorChoiceOption,
    SubproductChoiceAttribute, SubproductChoiceOption,
    ImageAttribute, ImageValue, ListAttribute, ListValue)


class AttributeTranslationOptions(TranslationOptions):
    fields = ('name',)


class AttributeValueTranslationOptions(TranslationOptions):
    fields = ('attribute',)


class ChoiceOptionsGroupTranslationOptions(TranslationOptions):
    fields = ('name',)


class ChoiceOptionTranslationOptions(TranslationOptions):
    fields = ('name',)


class ChoiceValueTranslationOptions(TranslationOptions):
    fields = ('option', 'group')


translator.register(Attribute, AttributeTranslationOptions)
translator.register(AttributeValue, AttributeValueTranslationOptions)
translator.register((StringValue, CharactersValue, ImageValue, ListValue))
translator.register(
    (StringAttribute, CharactersAttribute, ChoiceAttribute,
     ImageAttribute, ListAttribute))
# Workaround for proxy models not inheriting translation fields.
translator.register(
    (SimpleChoiceAttribute, ImageChoiceAttribute, ColorChoiceAttribute,
     SubproductChoiceAttribute), AttributeTranslationOptions)
translator.register(ChoiceOptionsGroup, ChoiceOptionsGroupTranslationOptions)
translator.register(ChoiceOption, ChoiceOptionTranslationOptions)
translator.register(
    (ImageChoiceOption, ColorChoiceOption, SubproductChoiceOption))
translator.register(ChoiceValue, ChoiceValueTranslationOptions)
