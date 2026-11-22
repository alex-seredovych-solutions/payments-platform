"""Deterministic pricing snapshot and adjustment allocation.

The checkout API still stores the legacy order-wide invoice as the authoritative
amount. More detailed line allocations are persisted separately so a downstream
service can potentially use them when package billing is enabled.
"""
from acme_shared.money import allocate_proportionally


def quote_cart(lines, coupon_cents=0, shipping_cents=700, tax_cents=0):
    if not lines or any(int(line['quantity']) <= 0 or int(line['unit_price_cents']) < 0 for line in lines):
        raise ValueError('Cart must contain nonnegative priced merchandise')
    merchandise = sum(int(line['unit_price_cents']) * int(line['quantity']) for line in lines)
    if any(value < 0 for value in (coupon_cents, shipping_cents, tax_cents)):
        raise ValueError('Financial components must be nonnegative')
    if coupon_cents > merchandise:
        raise ValueError('Coupon exceeds eligible merchandise')
    return {'merchandise_cents': merchandise, 'coupon_cents': coupon_cents,
            'shipping_cents': shipping_cents, 'tax_cents': tax_cents,
            'amount_cents': merchandise - coupon_cents + shipping_cents + tax_cents}


def line_financial_allocations(lines, coupon_cents, points_reduction_cents,
                               shipping_cents, tax_cents, coupon_eligible_skus=None):
    """Allocate financial values in integer cents, by original order line.

    Coupon value is allocated on merchandise before promotional points. Values
    remain distinct so later refunds do not mistake a discount for cash tender.
    The simplified simulator uses an order-level tax result; a real tax engine
    would preserve per-jurisdiction classifications in this snapshot too.
    """
    names = [line.get('line_id', str(i)) for i, line in enumerate(lines)]
    ordered = sorted(range(len(lines)), key=lambda i: names[i])
    merchandise = [int(line['unit_price_cents']) * int(line['quantity']) for line in lines]
    discount_weights = [merchandise[i] if coupon_eligible_skus is None or lines[i]['sku'] in coupon_eligible_skus else 0
                        for i in ordered]
    if coupon_cents > sum(discount_weights):
        raise ValueError('Coupon exceeds merchandise eligible for this promotion')
    discounts = allocate_proportionally(coupon_cents, discount_weights)
    coupon = [0] * len(lines)
    for ix, amount in zip(ordered, discounts):
        coupon[ix] = amount
    remaining = [max(0, merchandise[i] - coupon[i]) for i in range(len(lines))]
    if points_reduction_cents > sum(remaining):
        raise ValueError('Points reduction exceeds merchandise after coupon')
    points = allocate_proportionally(points_reduction_cents, [remaining[i] for i in ordered])
    shipping = allocate_proportionally(shipping_cents, [merchandise[i] for i in ordered])
    taxes = allocate_proportionally(tax_cents, [merchandise[i] for i in ordered])
    allocated = []
    for position, ix in enumerate(ordered):
        paid = merchandise[ix] - coupon[ix] - points[position] + shipping[position] + taxes[position]
        allocated.append({'index': ix, 'merchandise_cents': merchandise[ix],
                          'coupon_allocated_cents': coupon[ix], 'points_allocated_cents': points[position],
                          'shipping_allocated_cents': shipping[position], 'tax_allocated_cents': taxes[position],
                          'card_due_cents': paid})
    return sorted(allocated, key=lambda row: row['index'])


def allocate_discount_for_adjustment(discount_cents, lines):
    weights = [line['unit_price_cents'] * line['quantity'] for line in lines]
    return allocate_proportionally(discount_cents, weights)
