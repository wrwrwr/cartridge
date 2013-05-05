import locale
import platform

from django import template

from mezzanine.conf import settings

from cartridge.shop.utils import set_locale


register = template.Library()


@register.filter
def currency(value, frac_digits=None):
    """
    Formats a value as currency according to locale, allowing to override
    the locale precision.
    """
    set_locale()
    if not value:
        value = 0
    if hasattr(locale, "currency") and frac_digits is None:
        value = locale.currency(value, grouping=True)
        if platform.system() == 'Windows':
            value = unicode(value, encoding='iso_8859_1')
    else:
        # based on locale.currency() in python >= 2.5
        conv = locale.localeconv()
        if frac_digits is None:
            frac_digits = conv["frac_digits"]
        value = [conv["currency_symbol"], conv["p_sep_by_space"] and " " or "",
            (("%%.%sf" % frac_digits) % value).replace(".",
            conv["mon_decimal_point"])]
        if not conv["p_cs_precedes"]:
            value.reverse()
        value = "".join(value)
    return value


def _order_totals(context):
    """
    Adds ``item_total``, ``order_total``, and a ``totals`` list with
    (label, value) tuples for other nonzero totals to the template context.
    Uses the order object for email receipts, or the cart object for checkout.
    """
    totals = []
    if "order" in context:
        order = context["order"]
        order_total = item_total = order.item_total
        for total_field, type_field, label in settings.SHOP_ORDER_TOTALS:
            if type_field:
                label = getattr(order, type_field)
            total = getattr(order, total_field)
            if total:
                totals.append((label, total))
                order_total += total
    else:
        request = context["request"]
        order_total = item_total = request.cart.total_price()
        if item_total > 0:
            # Ignore session if cart has no items, as cart may have
            # expired sooner than the session.
            session = request.session
            for total_field, type_field, label in settings.SHOP_ORDER_TOTALS:
                if type_field:
                    label = session.get(type_field, None)
                total = session.get(total_field, None)
                if total:
                    totals.append((label, total))
                    order_total += total
    context["item_total"] = item_total
    context["totals"] = totals
    context["order_total"] = order_total
    return context


@register.inclusion_tag("shop/includes/order_totals.html", takes_context=True)
def order_totals(context):
    """
    HTML version of order_totals.
    """
    return _order_totals(context)


@register.inclusion_tag("shop/includes/order_totals.txt", takes_context=True)
def order_totals_text(context):
    """
    Text version of order_totals.
    """
    return _order_totals(context)


@register.simple_tag(takes_context=True)
def order_totals_context(context):
    """
    Sets totals variables in context. For special tasks like PDF invoices.
    """
    _order_totals(context)
    return ""
