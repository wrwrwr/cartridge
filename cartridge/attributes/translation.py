from modeltranslation.translator import TranslationOptions, translator

from .models import (
    Attribute, AttributeValue,
    StringAttribute, StringValue, CharactersAttribute, CharactersValue,
    ChoiceAttribute, ChoiceOptionsGroup, ChoiceOption, ChoiceValue,
    SimpleChoiceAttribute,
    ImageChoiceAttribute, ImageChoiceOption,
    ColorChoiceAttribute, ColorChoiceOption,
    ImageAttribute, ImageValue, ListAttribute, ListValue)


class AttributeTranslationOptions(TranslationOptions):
    fields = ('name',)


class AttributeValueTranslationOptions(TranslationOptions):
    fields = ('attribute',)


class ChoiceOptionsGroupTranslationOptions(TranslationOptions):
    fields = ('name',)


class ChoiceOptionTranslationOptions(TranslationOptions):
    fields = ('option',)


class ChoiceValueTranslationOptions(TranslationOptions):
    fields = ('option', 'group')


translator.register(Attribute, AttributeTranslationOptions)
translator.register(AttributeValue, AttributeValueTranslationOptions)
translator.register((StringValue, CharactersValue, ImageValue, ListValue))
translator.register(
    (StringAttribute, CharactersAttribute, ChoiceAttribute,
     SimpleChoiceAttribute, ImageChoiceAttribute, ColorChoiceAttribute,
     ImageAttribute, ListAttribute))
translator.register(ChoiceOptionsGroup, ChoiceOptionsGroupTranslationOptions)
translator.register(ChoiceOption, ChoiceOptionTranslationOptions)
translator.register((ImageChoiceOption, ColorChoiceOption,))
translator.register(ChoiceValue, ChoiceValueTranslationOptions)
