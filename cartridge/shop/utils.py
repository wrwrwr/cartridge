import hmac
from locale import setlocale, LC_MONETARY
try:
    from hashlib import sha512 as digest
except ImportError:
    from md5 import new as digest

from django.core.exceptions import ImproperlyConfigured
from django.utils.timezone import now
from django.utils.translation import ugettext as _

from mezzanine.conf import settings


class EmptyCart(object):
    """
    A dummy cart object used before any items have been added.
    Used to avoid querying the database for cart and items on each
    request.
    """

    id = None
    pk = None
    has_items = lambda *a, **k: False
    skus = lambda *a, **k: []
    upsell_products = lambda *a, **k: []
    total_quantity = lambda *a, **k: 0
    total_price = lambda *a, **k: 0
    calculate_discount = lambda *a, **k: 0
    __int__ = lambda *a, **k: 0
    __iter__ = lambda *a, **k: iter([])

    def __init__(self, request):
        """
        Store the request so we can add the real cart ID to the
        session if any items get added.
        """
        self._request = request

    def add_item(self, *args, **kwargs):
        """
        Create a real cart object, add the items to it and store
        the cart ID in the session.
        """
        from cartridge.shop.models import Cart
        cart = Cart.objects.create(last_updated=now())
        cart.add_item(*args, **kwargs)
        self._request.session["cart"] = cart.id


def make_choices(choices):
    """
    Zips a list with itself for field choices.
    """
    return zip(choices, choices)


def recalculate_discount(request):
    """
    Updates discounts when the cart is modified.

    If a discount code is entered applies its discount, otherwise
    checks loyalty and Facebook discounts and chooses just one highest.
    """
    from cartridge.shop.forms import DiscountForm
    from cartridge.shop.models import Cart, LoyaltyDiscount, FacebookDiscount
    # Rebind the cart to request since it's been modified.
    request.cart = Cart.objects.from_request(request)
    try:
        del request.session["discount_total"]
    except KeyError:
        pass
    if request.session.get("disable_discounts"):
        return
    discount_code = request.session.get("discount_code", "")
    if discount_code != "":
        discount_form = DiscountForm(request, {"discount_code": discount_code})
        if discount_form.is_valid():
            # TODO: Move session logic to DiscountCode model.
            discount_form.set_discount()
    else:
        loyalty_discount, loyalty_total = LoyaltyDiscount.objects.get_highest(
            request.user, request.cart)
        facebook_discount, facebook_total = \
            FacebookDiscount.objects.get_highest(
                request.user, request.cart, request.COOKIES)
        if loyalty_discount or facebook_discount:
            if loyalty_total > facebook_total:
                loyalty_discount.update_session(request)
            else:
                facebook_discount.update_session(request)


def set_shipping(request, shipping_type, shipping_total):
    """
    Stores the shipping type and total in the session.
    """
    request.session["shipping_type"] = shipping_type
    request.session["shipping_total"] = shipping_total


def set_tax(request, tax_type, tax_total):
    """
    Stores the tax type and total in the session.
    """
    request.session["tax_type"] = tax_type
    request.session["tax_total"] = tax_total


def sign(value):
    """
    Returns the hash of the given value, used for signing order key stored in
    cookie for remembering address fields.
    """
    return hmac.new(settings.SECRET_KEY, value, digest).hexdigest()


def set_locale():
    """
    Sets the locale for currency formatting.
    """
    currency_locale = settings.SHOP_CURRENCY_LOCALE
    try:
        if setlocale(LC_MONETARY, currency_locale) == "C":
            # C locale doesn't contain a suitable value for "frac_digits".
            raise
    except:
        msg = _("Invalid currency locale specified for SHOP_CURRENCY_LOCALE: "
                "'%s'. You'll need to set the locale for your system, or "
                "configure the SHOP_CURRENCY_LOCALE setting in your settings "
                "module.")
        raise ImproperlyConfigured(msg % currency_locale)
