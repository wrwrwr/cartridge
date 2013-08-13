def get_subvalues(subproduct):
    """
    Given a subproducts' structure leaf returns a list of attribute values
    from that leaf.

    Leafs are currently (option id, attribute values dict) tuples.
    """
    return subproduct[1].values()


def get_subproducts(request, product=None, attribute=None, default=None):
    """
    Returns subproduct attribute values that will be saved when the given
    parent product is added to the cart.

    Subproduct attribute values are prestored as dict(dict(tuple*)):

        product id --> attribute id --> (option id, attribute values),

    (*) values may be lists (or even lists of lists) of tuples to reflect the
    structure for ``ListAttributes``.
    """
    subproducts = request.session.get('subproducts', {})
    if product is None:
        return subproducts
    product_subproducts = subproducts.get(product.id, {})
    if attribute is None:
        return product_subproducts
    return product_subproducts.get(attribute.id, default)


def set_subproducts(request, product, attribute, subproducts):
    """
    Stores attribute values for a subproduct attribute in session -- to be
    saved when the parent product is added to the cart.

    ``Subproducts`` should be an (option id, attribute values) tuple or a list
    or tree with such tuples as leaves. You may pass a false value to remove a
    subproduct (also removing parent entries if empty).

    Adding subproducts without attribute values is also supported, as it's
    useful for incremental construction of a subproducts list.
    """
    if subproducts:
        request.session.setdefault('subproducts', {}).setdefault(
            product.id, {})[attribute.id] = subproducts
    else:
        remove_subproducts(request, product, attribute)


def remove_subproducts(request, product=None, attribute=None):
    """
    Removes subproducts prestored for an attribute, for all attributes
    of a product, or all temporary subproducts.
    """
    try:
        if product is not None and attribute is not None:
            del request.session['subproducts'][product.id][attribute.id]
        if product is not None and (attribute is None or
                not request.session['subproducts'][product.id]):
            del request.session['subproducts'][product.id]
        if product is None or not request.session['subproducts']:
            del request.session['subproducts']
    except KeyError:
        pass
