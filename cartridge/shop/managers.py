
from collections import defaultdict
from datetime import datetime, timedelta

from django.db.models import Manager, Q, Sum
from django.utils.datastructures import SortedDict
from django.utils.timezone import now

from mezzanine.conf import settings


class CartManager(Manager):

    def from_request(self, request):
        """
        Return a cart by ID stored in the session, creating it if not
        found as well as removing old carts prior to creating a new
        cart.
        """
        n = now()
        expiry_minutes = timedelta(minutes=settings.SHOP_CART_EXPIRY_MINUTES)
        expiry_time = n - expiry_minutes
        cart_id = request.session.get("cart", None)
        cart = None
        if cart_id:
            try:
                cart = self.get(last_updated__gte=expiry_time, id=cart_id)
            except self.model.DoesNotExist:
                request.session["cart"] = None
            else:
                # Update timestamp and clear out old carts.
                cart.last_updated = n
                cart.save()
                self.filter(last_updated__lt=expiry_time).delete()
        if not cart:
            # Forget what checkout step we were up to.
            try:
                del request.session["order"]["step"]
                request.session.modified = True
            except KeyError:
                pass
            from cartridge.shop.utils import EmptyCart
            cart = EmptyCart(request)
        return cart


class OrderManager(Manager):

    def from_request(self, request):
        """
        Returns the last order made by session key. Used for
        Google Anayltics order tracking in the order complete view,
        and in tests.
        """
        orders = self.filter(key=request.session.session_key).order_by("-id")
        if orders:
            return orders[0]
        raise self.model.DoesNotExist


class ProductOptionManager(Manager):

    def as_fields(self):
        """
        Return a dict of product options as their field names and
        choices.
        """
        options = defaultdict(list)
        for option in self.all():
            options["option%s" % option.type].append(option.name)
        return options


class ProductVariationManager(Manager):

    use_for_related_fields = True

    def _empty_options_lookup(self, exclude=None):
        """
        Create a lookup dict of field__isnull for options fields.
        """
        if not exclude:
            exclude = {}
        return dict([("%s__isnull" % f.name, True)
            for f in self.model.option_fields() if f.name not in exclude])

    def create_from_options(self, options):
        """
        Create all unique variations from the selected options.
        """
        if options:
            options = SortedDict(options)
            # Build all combinations of options.
            variations = [[]]
            for values_list in options.values():
                variations = [x + [y] for x in variations for y in values_list]
            for variation in variations:
                # Lookup unspecified options as null to ensure a
                # unique filter.
                variation = dict(zip(options.keys(), variation))
                lookup = dict(variation)
                lookup.update(self._empty_options_lookup(exclude=variation))
                try:
                    self.get(**lookup)
                except self.model.DoesNotExist:
                    self.create(**variation)

    def manage_empty(self):
        """
        Create an empty variation (no options) if none exist,
        otherwise if multiple variations exist ensure there is no
        redundant empty variation. Also ensure there is at least one
        default variation.
        """
        total_variations = self.count()
        if total_variations == 0:
            self.create()
        elif total_variations > 1:
            self.filter(**self._empty_options_lookup()).delete()
        try:
            self.get(default=True)
        except self.model.DoesNotExist:
            first_variation = self.all()[0]
            first_variation.default = True
            first_variation.save()

    def set_default_images(self, deleted_image_ids):
        """
        Assign the first image for the product to each variation that
        doesn't have an image. Also remove any images that have been
        deleted via the admin to avoid invalid image selections.
        """
        variations = self.all()
        if not variations:
            return
        image = variations[0].product.images.exclude(id__in=deleted_image_ids)
        if image:
            image = image[0]
        for variation in variations:
            save = False
            if unicode(variation.image_id) in deleted_image_ids:
                variation.image = None
                save = True
            if image and not variation.image:
                variation.image = image
                save = True
            if save:
                variation.save()


class ProductActionManager(Manager):

    use_for_related_fields = True

    def _action_for_field(self, field):
        """
        Increases the given field by datetime.today().toordinal()
        which provides a time scaling value we can order by to
        determine popularity over time.
        """
        timestamp = datetime.today().toordinal()
        action, created = self.get_or_create(timestamp=timestamp)
        setattr(action, field, getattr(action, field) + 1)
        action.save()

    def added_to_cart(self):
        """
        Increase total_cart when product is added to cart.
        """
        self._action_for_field("total_cart")

    def purchased(self):
        """
        Increase total_purchased when product is purchased.
        """
        self._action_for_field("total_purchase")


class DiscountManager(Manager):

    def active(self, *args, **kwargs):
        """
        Items flagged as active and in valid date range if date(s) are
        specified.
        """
        n = now()
        valid_from = Q(valid_from__isnull=True) | Q(valid_from__lte=n)
        valid_to = Q(valid_to__isnull=True) | Q(valid_to__gte=n)
        valid = self.filter(valid_from, valid_to, active=True)
        return valid


class DiscountCodeManager(DiscountManager):

    def get_valid(self, code, cart):
        """
        Items flagged as active and within date range as well checking
        that the given cart contains items that the code is valid for.
        """
        total_price_valid = (Q(min_purchase__isnull=True) |
                             Q(min_purchase__lte=cart.total_price()))
        discount = self.active().exclude(
            uses_remaining__isnull=False, uses_remaining=0).get(
            total_price_valid, code=code)
        products = discount.all_products()
        if products.count() > 0:
            if products.filter(variations__sku__in=cart.skus()).count() == 0:
                raise self.model.DoesNotExist
        return discount


class LoyaltyDiscountManager(DiscountManager):

    def get_highest(self, user, cart):
        """
        Finds active discounts for which cart and orders subtotal limits are
        fullfilled and returns the one that gives the best cost reduction.
        """
        from cartridge.shop.models import Order
        orders = Order.objects.filter(user_id=user.id,
            status__in=settings.SHOP_LOYALTY_DISCOUNT_ORDER_STATUSES)
        orders_total = orders.aggregate(Sum("item_total"))['item_total__sum']
        if orders_total is None:
            orders_total = 0
        cart_total = cart.total_price()
        valid = ((Q(min_purchase__isnull=True) |
                  Q(min_purchase__lte=cart_total)) &
                 (Q(min_purchases__isnull=True) |
                  Q(min_purchases__lte=orders_total)))
        best_discount, best_total = None, 0
        for discount in self.active().filter(valid):
            products = discount.all_products()
            if (products.count() > 0 and products.filter(
                    variations__sku__in=cart.skus()).count() == 0):
                continue
            total = discount.get_total(user, cart)
            if total > best_total:
                best_discount, best_total = discount, total
        return best_discount, best_total

    def get_best_percent(self, user):
        """
        Finds the best discount for which the ``user`` has big enough
        orders total.
        """
        from cartridge.shop.models import Order
        orders = Order.objects.filter(user_id=user.id,
            status__in=settings.SHOP_LOYALTY_DISCOUNT_ORDER_STATUSES)
        orders_total = orders.aggregate(Sum("item_total"))['item_total__sum']
        if orders_total is None:
            orders_total = 0
        valid = (Q(min_purchase__isnull=True) &
                 Q(min_purchases__lte=orders_total))
        discounts = self.active().filter(valid).order_by('-discount_percent')
        if discounts:
            return discounts[0]
        else:
            return None


class FacebookDiscountManager(DiscountManager):

    def get_highest(self, user, cart, cookies):
        """
        Scans active discounts for which "liking" prerequisites are met.
        """
        import facebook
        facebook_user = facebook.get_user_from_cookie(
            cookies,
            settings.FACEBOOK_APP_ID, settings.FACEBOOK_APP_SECRET)
        if not facebook_user:
            return None, 0
        graph = facebook.GraphAPI(facebook_user['access_token'])
        best_discount, best_total = None, 0
        for discount in self.active():
            products = discount.all_products()
            if (products.count() > 0 and products.filter(
                    variations__sku__in=cart.skus()).count() == 0):
                continue
            data = graph.get_object('me', fields='{}.target_id({})'.format(
                discount.connection, discount.target_id))
            if not data.get(discount.connection, {}).get('data', []):
                continue
            total = discount.get_total(user, cart)
            if total > best_total:
                best_discount, best_total = discount, total
        return best_discount, best_total
