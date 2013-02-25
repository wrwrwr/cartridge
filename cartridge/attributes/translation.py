from .models import (Attribute, ChoiceAttribute, ChoiceAttributeOption,
                     StringAttribute)

from modeltranslation.translator import TranslationOptions, translator


class AttributeTranslationOptions(TranslationOptions):
    fields = ('name',)


class ChoiceAttributeOptionTranslationOptions(TranslationOptions):
    fields = ('option',)


translator.register(Attribute, AttributeTranslationOptions)
translator.register((ChoiceAttribute, StringAttribute))
translator.register(ChoiceAttributeOption,
                    ChoiceAttributeOptionTranslationOptions)
