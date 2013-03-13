from modeltranslation.translator import TranslationOptions, translator

from .models import (Attribute, ChoiceAttribute, ChoiceAttributeOptionsGroup,
                     ChoiceAttributeOption, StringAttribute, LettersAttribute,
                     ListAttribute, ImageAttribute)


class AttributeTranslationOptions(TranslationOptions):
    fields = ('name',)


class ChoiceAttributeOptionsGroupTranslationOptions(TranslationOptions):
    fields = ('name',)


class ChoiceAttributeOptionTranslationOptions(TranslationOptions):
    fields = ('option',)


translator.register(Attribute, AttributeTranslationOptions)
translator.register((ChoiceAttribute, StringAttribute, LettersAttribute,
                     ListAttribute, ImageAttribute))
translator.register(ChoiceAttributeOptionsGroup,
                    ChoiceAttributeOptionsGroupTranslationOptions)
translator.register(ChoiceAttributeOption,
                    ChoiceAttributeOptionTranslationOptions)
