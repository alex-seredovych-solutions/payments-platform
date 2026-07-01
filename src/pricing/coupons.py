"""Merchant coupon catalog and checkout redemption counters."""
class CouponService:
    def __init__(self,db,clock):
        self.db,self.clock=db,clock

    def create(self,code,flat_discount_cents,end_at=None):
        self.db.run('INSERT OR REPLACE INTO coupons VALUES (?,?,?,?)',(code,flat_discount_cents,1,end_at))

    def discount(self,code,merchandise_cents):
        if not code:
            return 0
        promo=self.db.one('SELECT * FROM coupons WHERE code=?',(code,))
        if not promo or not promo['enabled'] or (promo['end_at'] and promo['end_at']<self.clock.now()):
            raise ValueError('Coupon not available')
        return min(merchandise_cents,promo['flat_discount_cents'])

    def redeem(self,order_id,code):
        if code:
            self.db.run('INSERT INTO coupon_usage VALUES (?,?,?)',(order_id,code,self.clock.now()))

    def redemption_count(self,code):
        return self.db.one('SELECT COUNT(*) AS n FROM coupon_usage WHERE code=?',(code,))['n']
