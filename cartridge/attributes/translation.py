from .models import (Attribute, ChoiceAttribute, ChoiceAttributeOption,
                     StringAttribute, LettersAttribute, ListAttribute,
                     ImageAttribute)

from modeltranslation.translator import TranslationOptions, translator


class AttributeTranslationOptions(TranslationOptions):
    fields = ('name',)


class ChoiceAttributeOptionTranslationOptions(TranslationOptions):
    fields = ('option',)


translator.register(Attribute, AttributeTranslationOptions)
translator.register((ChoiceAttribute, StringAttribute, LettersAttribute,
                     ListAttribute, ImageAttribute))
translator.register(ChoiceAttributeOption,
                    ChoiceAttributeOptionTranslationOptions)
