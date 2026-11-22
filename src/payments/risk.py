"""Fraud review decisions and order-level financial release holds."""
class RiskReview:
    def __init__(self,db,bus):
        self.db,self.bus=db,bus
        self.cases={}

    def request(self,order_id,reason='MANUAL_REVIEW'):
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(order_id,))
        if not order:
            raise KeyError(order_id)
        if order['status']=='CANCELLED':
            return False
        self.cases[order_id]={'state':'REVIEW','reason':reason,'decision_version':1}
        self.db.run("UPDATE orders SET risk_state='REVIEW' WHERE order_id=?",(order_id,))
        self.bus.publish('fraud.review_requested',order_id=order_id,reason=reason,
                         decision_version=1)
        return True

    def clear(self,order_id,reviewer='risk-operator'):
        case=self.cases.get(order_id,{'decision_version':0})
        case.update(state='CLEAR',decision_version=case['decision_version']+1,
                    reviewer=reviewer)
        self.cases[order_id]=case
        self.db.run("UPDATE orders SET risk_state='CLEAR' WHERE order_id=?",(order_id,))
        self.bus.publish('fraud.cleared',order_id=order_id,reviewer=reviewer,
                         decision_version=case['decision_version'])

    def reject(self,order_id,reason='POLICY_REJECTION'):
        case=self.cases.get(order_id,{'decision_version':0})
        case.update(state='REJECTED',decision_version=case['decision_version']+1,
                    reason=reason)
        self.cases[order_id]=case
        self.db.run("UPDATE orders SET risk_state='REJECTED' WHERE order_id=?",(order_id,))
        self.bus.publish('fraud.rejected',order_id=order_id,reason=reason,
                         decision_version=case['decision_version'])
