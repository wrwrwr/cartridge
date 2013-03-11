from .models import (Attribute, ChoiceAttribute, ChoiceAttributeOption,
                     StringAttribute, LettersAttribute)

from modeltranslation.translator import TranslationOptions, translator


class AttributeTranslationOptions(TranslationOptions):
    fields = ('name',)


class ChoiceAttributeOptionTranslationOptions(TranslationOptions):
    fields = ('option',)


translator.register(Attribute, AttributeTranslationOptions)
translator.register((ChoiceAttribute, StringAttribute, LettersAttribute))
translator.register(ChoiceAttributeOption,
                    ChoiceAttributeOptionTranslationOptions)
