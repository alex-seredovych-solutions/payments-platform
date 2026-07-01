"""Legacy pricing quote, with one order-wide reduction for promotions."""
from acme_shared.money import allocate_proportionally

def quote_cart(lines,coupon_cents=0,shipping_cents=700,tax_cents=0):
    merchandise=sum(int(line['unit_price_cents'])*int(line['quantity']) for line in lines)
    return {'merchandise_cents':merchandise,'coupon_cents':coupon_cents,
            'shipping_cents':shipping_cents,'tax_cents':tax_cents,
            'amount_cents':merchandise-coupon_cents+shipping_cents+tax_cents}

def allocate_discount_for_adjustment(discount_cents,lines):
    weights=[line['unit_price_cents']*line['quantity'] for line in lines]
    return allocate_proportionally(discount_cents,weights)
