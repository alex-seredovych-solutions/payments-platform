"""Risk-review records used by checkout and dispatch eligibility."""
class RiskReview:
    def __init__(self,db,bus):
        self.db,self.bus=db,bus

    def request(self,order_id):
        self.db.run("UPDATE orders SET risk_state='REVIEW' WHERE order_id=?",(order_id,))
        self.bus.publish('fraud.review_requested',order_id=order_id)

    def clear(self,order_id):
        self.db.run("UPDATE orders SET risk_state='CLEAR' WHERE order_id=?",(order_id,))
        self.bus.publish('fraud.cleared',order_id=order_id)
