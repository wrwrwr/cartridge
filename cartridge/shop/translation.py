
from cartridge.shop.models import (
    Product, ProductImage, ProductOption, Category, SelectedProduct, CartItem,
    OrderItem, Discount, Sale, DiscountCode, Voucher, LoyaltyDiscount,
    FacebookDiscount)

from modeltranslation.translator import TranslationOptions, translator


class ProductTranslationOptions(TranslationOptions):
    fields = ("keywords_string",)


class ProductImageTranslationOptions(TranslationOptions):
    fields = ("description",)


class ProductOptionTranslationOptions(TranslationOptions):
    fields = ("name",)


class SelectedProductTranslationOptions(TranslationOptions):
    fields = ("description",)


class CartItemTranslationOptions(TranslationOptions):
    fields = ("url",)


class DiscountTranslationOptions(TranslationOptions):
    fields = ("title",)


translator.register(Product, ProductTranslationOptions)
translator.register(ProductImage, ProductImageTranslationOptions)
translator.register(ProductOption, ProductOptionTranslationOptions)
translator.register(SelectedProduct, SelectedProductTranslationOptions)
translator.register(CartItem, CartItemTranslationOptions)
translator.register(Discount, DiscountTranslationOptions)
translator.register(
    (Category, OrderItem,
     Sale, DiscountCode, Voucher, LoyaltyDiscount, FacebookDiscount))
