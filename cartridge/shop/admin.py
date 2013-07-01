"""
Admin classes for all the shop models.

Many attributes in here are controlled by the ``SHOP_USE_VARIATIONS``
setting which defaults to True. In this case, variations are managed in
the product change view, and are created given the ``ProductOption``
values selected.

A handful of fields (mostly those defined on the abstract ``Priced``
model) are duplicated across both the ``Product`` and
``ProductVariation`` models, with the latter being the definitive
source, and the former supporting denormalised data that can be
referenced when iterating through products, without having to
query the underlying variations.

When ``SHOP_USE_VARIATIONS`` is set to False, a single variation is
still stored against each product, to keep consistent with the overall
model design. Since from a user perspective there are no variations,
the inlines for variations provide a single inline for managing the
one variation per product, so in the product change view, a single set
of price fields are available via the one variation inline.

Also when ``SHOP_USE_VARIATIONS`` is set to False, the denormalised
price fields on the product model are presented as editable fields in
the product change list - if these form fields are used, the values
are then pushed back onto the one variation for the product.
"""

from copy import deepcopy

from django.contrib import admin
from django.db.models import ImageField
from django.utils.translation import ugettext_lazy as _

from mezzanine.conf import settings
from mezzanine.core.admin import (
    TranslationAdmin, TranslationInlineModelAdmin,
    DisplayableAdmin, TabularDynamicInlineAdmin)
from mezzanine.pages.admin import PageAdmin

from cartridge.attributes.admin import ProductAttributeAdmin
from cartridge.shop.fields import MoneyField
from cartridge.shop.forms import ProductAdminForm, ProductVariationAdminForm
from cartridge.shop.forms import ProductVariationAdminFormset
from cartridge.shop.forms import DiscountAdminForm, ImageWidget, MoneyWidget
from cartridge.shop.models import (
    Category, Product, ProductImage, ProductVariation, ProductOption,
    Order, OrderItem, Sale, DiscountCode, Voucher, VoucherCode,
    LoyaltyDiscount, FacebookDiscount)
from cartridge.shop.utils import order_totals_fields


# Lists of field names.
option_fields = [f.name for f in ProductVariation.option_fields()]
_flds = lambda s: [f.name for f in Order._meta.fields if f.name.startswith(s)]
billing_fields = _flds("billing_detail")
shipping_fields = _flds("shipping_detail")


################
#  CATEGORIES  #
################

# Categories fieldsets are extended from Page fieldsets, since
# categories are a Mezzanine Page type.
category_fieldsets = deepcopy(PageAdmin.fieldsets)
category_fieldsets[0][1]["fields"][3:3] = ["content", "products"]
category_fieldsets += ((_("Product filters"), {
    "fields": ("sale", ("price_min", "price_max"), "combined"),
    "classes": ("collapse-closed",)},),)
if settings.SHOP_CATEGORY_USE_FEATURED_IMAGE:
    category_fieldsets[0][1]["fields"].insert(3, "featured_image")

# Options are only used when variations are in use, so only provide
# them as filters for dynamic categories when this is the case.
if settings.SHOP_USE_VARIATIONS:
    category_fieldsets[-1][1]["fields"] = (("options",) +
                                        category_fieldsets[-1][1]["fields"])


class CategoryAdmin(PageAdmin):
    fieldsets = category_fieldsets
    formfield_overrides = {ImageField: {"widget": ImageWidget}}
    filter_horizontal = ("options", "products",)

################
#  VARIATIONS  #
################

# If variations aren't used, the variation inline should always
# provide a single inline for managing the single variation per
# product.
variation_fields = ["sku", "num_in_stock", "unit_price",
                    "sale_price", "sale_from", "sale_to", "image"]
if settings.SHOP_USE_VARIATIONS:
    variation_fields.insert(1, "default")
    variations_max_num = None
    variations_extra = 0
else:
    variations_max_num = 1
    variations_extra = 1


class ProductVariationAdmin(admin.TabularInline):
    verbose_name_plural = _("Current variations")
    model = ProductVariation
    fields = variation_fields
    max_num = variations_max_num
    extra = variations_extra
    formfield_overrides = {MoneyField: {"widget": MoneyWidget}}
    form = ProductVariationAdminForm
    formset = ProductVariationAdminFormset


class ProductImageAdmin(TabularDynamicInlineAdmin,
                        TranslationInlineModelAdmin):
    model = ProductImage
    formfield_overrides = {ImageField: {"widget": ImageWidget}}

##############
#  PRODUCTS  #
##############

product_fieldsets = deepcopy(DisplayableAdmin.fieldsets)
product_fieldsets[0][1]["fields"][1] = ("status", "available")
product_fieldsets[0][1]["fields"].extend(["content", "categories"])
product_fieldsets = list(product_fieldsets)
product_fieldsets.append((_("Other products"), {
    "classes": ("collapse-closed",),
    "fields": ("related_products", "upsell_products")}))

product_list_display = ["admin_thumb", "title", "status", "available", "_order",
                        "admin_link"]
product_list_editable = ["status", "available", "_order"]

# If variations are used, set up the product option fields for managing
# variations. If not, expose the denormalised price fields for a product
# in the change list view.
if settings.SHOP_USE_VARIATIONS:
    product_fieldsets.insert(1, (_("Create new variations"),
        {"classes": ("create-variations",), "fields": option_fields}))
else:
    extra_list_fields = ["sku", "unit_price", "sale_price", "num_in_stock"]
    product_list_display[4:4] = extra_list_fields
    product_list_editable.extend(extra_list_fields)


class ProductAdmin(DisplayableAdmin):

    class Media:
        js = ("cartridge/js/admin/product_variations.js",)
        css = {"all": ("cartridge/css/admin/product.css",)}

    list_display = product_list_display
    list_display_links = ("admin_thumb", "title")
    list_editable = product_list_editable
    list_filter = ("status", "available", "categories")
    filter_horizontal = ("categories", "related_products", "upsell_products")
    search_fields = ("title", "content", "categories__title",
                     "variations__sku")
    inlines = (ProductImageAdmin, ProductAttributeAdmin, ProductVariationAdmin)
    form = ProductAdminForm
    fieldsets = product_fieldsets

    def save_model(self, request, obj, form, change):
        """
        Store the product object for creating variations in save_formset.
        """
        super(ProductAdmin, self).save_model(request, obj, form, change)
        self._product = obj

    def save_formset(self, request, form, formset, change):
        """

        Here be dragons. We want to perform these steps sequentially:

        - Save variations formset
        - Run the required variation manager methods:
          (create_from_options, manage_empty, etc)
        - Save the images formset

        The variations formset needs to be saved first for the manager
        methods to have access to the correct variations. The images
        formset needs to be run last, because if images are deleted
        that are selected for variations, the variations formset will
        raise errors when saving due to invalid image selections. This
        gets addressed in the set_default_images method.

        An additional problem is the actual ordering of the inlines,
        which are in the reverse order for achieving the above. To
        address this, we store the images formset as an attribute, and
        then call save on it after the other required steps have
        occurred.

        """

        # Store the images formset for later saving, otherwise save the
        # formset.
        if formset.model == ProductImage:
            self._images_formset = formset
        else:
            super(ProductAdmin, self).save_formset(request, form, formset,
                                                   change)

        # Run each of the variation manager methods if we're saving
        # the variations formset.
        if formset.model == ProductVariation:

            # Build up selected options for new variations.
            options = dict([(f, request.POST.getlist(f)) for f in option_fields
                             if request.POST.getlist(f)])
            # Create a list of image IDs that have been marked to delete.
            deleted_images = [request.POST.get(f.replace("-DELETE", "-id"))
                              for f in request.POST if f.startswith("images-")
                              and f.endswith("-DELETE")]

            # Create new variations for selected options.
            self._product.variations.create_from_options(options)
            # Create a default variation if there are none.
            self._product.variations.manage_empty()

            # Remove any images deleted just now from variations they're
            # assigned to, and set an image for any variations without one.
            self._product.variations.set_default_images(deleted_images)

            # Save the images formset stored previously.
            super(ProductAdmin, self).save_formset(request, form,
                                                 self._images_formset, change)

            # Run again to allow for no images existing previously, with
            # new images added which can be used as defaults for variations.
            self._product.variations.set_default_images(deleted_images)

            # Copy duplicate fields (``Priced`` fields) from the default
            # variation to the product.
            self._product.copy_default_variation()


class ProductOptionAdmin(TranslationAdmin):
    ordering = ("type", "name")
    list_display = ("type", "name")
    list_display_links = ("type",)
    list_editable = ("name",)
    list_filter = ("type",)
    search_fields = ("type", "name")
    radio_fields = {"type": admin.HORIZONTAL}


class OrderItemInline(admin.TabularInline):
    verbose_name_plural = _("Items")
    model = OrderItem
    extra = 0
    formfield_overrides = {MoneyField: {"widget": MoneyWidget}}


class OrderAdmin(admin.ModelAdmin):
    ordering = ("status", "-id")
    list_display = ("id", "billing_name", "total", "time", "status",
                    "transaction_id", "invoice")
    list_editable = ("status",)
    list_filter = ("status", "time")
    list_display_links = ("id", "billing_name",)
    search_fields = (["id", "status", "transaction_id"] +
                     billing_fields + shipping_fields)
    date_hierarchy = "time"
    radio_fields = {"status": admin.HORIZONTAL}
#   TODO: Proper attributes editing would require inlines within inlines.
#   There's an accepted Django ticket concerning this:
#       https://code.djangoproject.com/ticket/9025.
#   Considering that the inlined form misses what may be the most common use
#   case -- adding more products, replacing it with plain list won't hurt much.
#   inlines = (OrderItemInline,)
    formfield_overrides = {MoneyField: {"widget": MoneyWidget}}
    fieldsets = (
        (_("Billing details"), {"fields": (tuple(billing_fields),)}),
        (_("Shipping details"), {"fields": (tuple(shipping_fields),)}),
        (_("Order totals"), {"fields": ["item_total"] +
                                       order_totals_fields(flat=False) +
                                       ["total"]}),
        (None, {"fields": ("additional_instructions", "transaction_id",
                           "status")}),
    )


class DiscountAdmin(TranslationAdmin):
    list_display = ("title", "active", "valid_from", "valid_to",
                    "discount_deduct", "discount_percent", "discount_exact")
    list_editable = ("active", "valid_from", "valid_to",
                     "discount_deduct", "discount_percent", "discount_exact")
    filter_horizontal = ("categories", "products")
    formfield_overrides = {MoneyField: {"widget": MoneyWidget}}
    form = DiscountAdminForm
    fieldsets = (
        (None, {"fields": ("title", "active", "valid_from", "valid_to")}),
        (_("Apply to product and/or products in categories"),
            {"fields": ("products", "categories")}),
        (_("Reduce unit price by"),
            {"fields": (("discount_deduct", "discount_percent",
            "discount_exact"),)}),
    )


class SaleAdmin(DiscountAdmin):
    pass


discount_code_list = list(DiscountAdmin.list_display)
discount_code_list[4:4] = ("code", "uses_remaining", "min_purchase")
discount_code_list.append("free_shipping")
discount_code_fieldsets = list(DiscountAdmin.fieldsets)
discount_code_fieldsets += (
    (None, {"fields": ("free_shipping",)}),
    (_("Code"), {"fields": ("code", "uses_remaining", "min_purchase")}))


class DiscountCodeAdmin(DiscountAdmin):
    list_display = discount_code_list
    list_editable = discount_code_list[1:]
    fieldsets = discount_code_fieldsets


loyalty_discount_list = list(DiscountAdmin.list_display)
loyalty_discount_list[4:4] = ("min_purchase", "min_purchases")
loyalty_discount_list.append("free_shipping")
loyalty_discount_fieldsets = list(DiscountAdmin.fieldsets)
loyalty_discount_fieldsets += (
    (None, {"fields": ("free_shipping",)}),
    (_("Cart and previous orders value"),
     {"fields": ("min_purchase", "min_purchases")}))


class LoyaltyDiscountAdmin(DiscountAdmin):
    list_display = loyalty_discount_list
    list_editable = loyalty_discount_list[1:]
    fieldsets = loyalty_discount_fieldsets


class VoucherCodeInline(TabularDynamicInlineAdmin):
    model = VoucherCode


voucher_list = list(DiscountAdmin.list_display)
voucher_list.insert(3, "min_purchase")
voucher_list.append("free_shipping")
voucher_fieldsets = list(DiscountAdmin.fieldsets)
voucher_fieldsets += (
    (None, {"fields": ("free_shipping",)}),
    (_("Cart value"), {"fields": ("min_purchase",)}))


class VoucherAdmin(DiscountAdmin):
    list_display = voucher_list + ["codes_count"]
    list_editable = voucher_list[1:]
    fieldsets = voucher_fieldsets
    inlines = (VoucherCodeInline,)

    def codes_count(self, voucher):
        return "%d / %d" % (voucher.codes.filter(used=True).count(),
                            voucher.codes.all().count())
    codes_count.short_description = _("Codes count")


facebook_discount_list = list(DiscountAdmin.list_display)
facebook_discount_list[4:4] = ("connection", "target_id")
facebook_discount_list.append("free_shipping")
facebook_discount_fieldsets = list(DiscountAdmin.fieldsets)
facebook_discount_fieldsets += (
    (None, {"fields": ("free_shipping",)}),
    (_("Facebook connection"), {"fields": ("connection", "target_id",)}))


class FacebookDiscountAdmin(DiscountAdmin):
    list_display = facebook_discount_list
    list_editable = facebook_discount_list[1:]
    fieldsets = facebook_discount_fieldsets


admin.site.register(Category, CategoryAdmin)
admin.site.register(Product, ProductAdmin)
if settings.SHOP_USE_VARIATIONS:
    admin.site.register(ProductOption, ProductOptionAdmin)
admin.site.register(Order, OrderAdmin)
admin.site.register(Sale, SaleAdmin)
admin.site.register(DiscountCode, DiscountCodeAdmin)
admin.site.register(Voucher, VoucherAdmin)
admin.site.register(LoyaltyDiscount, LoyaltyDiscountAdmin)
admin.site.register(FacebookDiscount, FacebookDiscountAdmin)
