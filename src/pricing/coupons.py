"""Coupon eligibility, promotion constraints, and accepted redemption history."""
from datetime import datetime

class CouponService:
    def __init__(self,db,clock):
        self.db,self.clock=db,clock
        self.extended_rules={}

    def create(self,code,flat_discount_cents,end_at=None):
        if not code or flat_discount_cents<0:
            raise ValueError('Invalid coupon')
        self.db.run('INSERT OR REPLACE INTO coupons VALUES (?,?,?,?)',
                    (code,flat_discount_cents,1,end_at))

    def configure(self,code,starts_at=None,customer_limit=None,global_limit=None,eligible_skus=None):
        if not self.db.one('SELECT 1 FROM coupons WHERE code=?',(code,)):
            raise KeyError(code)
        self.extended_rules[code]={'starts_at':starts_at,'customer_limit':customer_limit,
                                   'global_limit':global_limit,
                                   'eligible_skus':set(eligible_skus) if eligible_skus else None}

    def discount(self,code,merchandise_cents,lines=None,customer_id=None):
        if not code:
            return 0
        coupon=self.db.one('SELECT * FROM coupons WHERE code=?',(code,))
        if not coupon or not coupon['enabled']:
            raise ValueError('Coupon not available')
        if coupon['end_at'] and coupon['end_at']<self.clock.now():
            raise ValueError('Coupon expired')
        rule=self.extended_rules.get(code,{})
        if rule.get('starts_at') and self.clock.now()<rule['starts_at']:
            raise ValueError('Coupon not active')
        if rule.get('global_limit') is not None and self.redemption_count(code)>=rule['global_limit']:
            raise ValueError('Coupon redemption limit reached')
        if rule.get('customer_limit') is not None and customer_id:
            used=self.db.one('SELECT COUNT(*) AS n FROM coupon_usage u JOIN orders o ON o.order_id=u.order_id '
                             'WHERE u.code=? AND o.customer_id=?',(code,customer_id))['n']
            if used>=rule['customer_limit']:
                raise ValueError('Customer redemption limit reached')
        eligible=merchandise_cents
        if rule.get('eligible_skus') is not None and lines is not None:
            eligible=sum(x['unit_price_cents']*x['quantity'] for x in lines
                         if x['sku'] in rule['eligible_skus'])
        return min(max(0,eligible),coupon['flat_discount_cents'])

    def redeem(self,order_id,code):
        if not code:
            return
        self.db.run('INSERT INTO coupon_usage VALUES (?,?,?)',(order_id,code,self.clock.now()))

    def redemption_count(self,code):
        return self.db.one('SELECT COUNT(*) AS n FROM coupon_usage WHERE code=?',(code,))['n']


def redemption_guard_key(order_id,coupon_code):
    return f'{order_id}:{coupon_code}'
