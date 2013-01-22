
from cartridge.shop.models import (Product, ProductImage, ProductOption,
                                   Category, SelectedProduct, CartItem,
                                   OrderItem, Discount, Sale, DiscountCode)

from modeltranslation.translator import TranslationOptions, translator


class ProductImageTranslationOptions(TranslationOptions):
    fields = ("description",)


class ProductOptionTranslationOptions(TranslationOptions):
    fields = ("name",)


class SelectedProductTranslationOptions(TranslationOptions):
    fields = ("description",)


class DiscountTranslationOptions(TranslationOptions):
    fields = ("title",)


translator.register(ProductImage, ProductImageTranslationOptions)
translator.register(ProductOption, ProductOptionTranslationOptions)
translator.register(SelectedProduct, SelectedProductTranslationOptions)
translator.register(Discount, DiscountTranslationOptions)
translator.register((Product, Category, CartItem, OrderItem, Sale, DiscountCode))

