
from django.conf.urls.defaults import patterns, url
from django.utils.translation import ugettext_lazy as _


urlpatterns = patterns("cartridge.shop.views",
    url(_("^product/(?P<slug>.*)/$"), "product", name="shop_product"),
    url(_("^wishlist/$"), "wishlist", name="shop_wishlist"),
    url(_("^cart/$"), "cart", name="shop_cart"),
    url(_("^checkout/$"), "checkout_steps", name="shop_checkout"),
    url(_("^checkout/complete/$"), "complete", name="shop_complete"),
    url(_("^invoice/(?P<order_id>\d+)/$"), "invoice", name="shop_invoice"),
)
