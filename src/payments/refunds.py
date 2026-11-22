"""Asynchronous captured-money refunds with amount limits and provider settlement."""
class RefundService:
    def __init__(self,db,bus,clock,gateway,ledger):
        self.db,self.bus,self.clock,self.gateway,self.ledger=db,bus,clock,gateway,ledger

    def request(self,order_id,amount_cents,request_id,capture_id=None):
        if amount_cents<=0 or not request_id:
            raise ValueError('Refund must have a positive amount and stable request ID')
        operation_key='refund:'+request_id
        earlier=self.db.one('SELECT * FROM refunds WHERE operation_key=?',(operation_key,))
        if earlier:
            if earlier['amount_cents']!=amount_cents or earlier['order_id']!=order_id:
                raise ValueError('Refund request was replayed with conflicting values')
            return earlier['refund_id']
        if capture_id:
            capture=self.db.one('SELECT * FROM captures WHERE capture_id=? AND order_id=?',
                                (capture_id,order_id))
        else:
            capture=self.db.one('SELECT * FROM captures WHERE order_id=? ORDER BY capture_id LIMIT 1',
                                (order_id,))
        if not capture:
            raise ValueError('Cannot refund an uncaptured order')
        prior=self.db.one('SELECT COALESCE(SUM(amount_cents),0) AS n FROM refunds WHERE capture_id=? '
                          'AND state!=?',(capture['capture_id'],'FAILED'))['n']
        available=capture['amount_cents']-prior
        if amount_cents>available:
            raise ValueError('Refund exceeds remaining captured monetary value')
        provider=self.gateway.refund(operation_key,amount_cents)
        refund_id=self.db.new_id('REF')
        self.db.run('INSERT INTO refunds VALUES (?,?,?,?,?,?)',
                    (refund_id,order_id,capture['capture_id'],amount_cents,
                     provider['status'],operation_key))
        self.bus.publish('refund.requested',order_id=order_id,refund_id=refund_id,
                         capture_id=capture['capture_id'],amount_cents=amount_cents,
                         financial_status=provider['status'])
        return refund_id

    def settle(self,refund_id):
        refund=self.db.one('SELECT * FROM refunds WHERE refund_id=?',(refund_id,))
        if not refund:
            raise KeyError(refund_id)
        if refund['state']=='SETTLED':
            return refund_id
        if refund['state']!='PENDING':
            raise ValueError('Cannot settle a failed or canceled refund')
        result=self.gateway.settle_refund(refund['operation_key'])
        with self.db.transaction():
            self.db.run("UPDATE refunds SET state='SETTLED' WHERE refund_id=?",(refund_id,))
            self.ledger.post(refund['order_id'],refund['operation_key'],'REFUND',-refund['amount_cents'])
        self.bus.publish('refund.settled',order_id=refund['order_id'],refund_id=refund_id,
                         capture_id=refund['capture_id'],amount_cents=refund['amount_cents'])
        return refund_id

    def fail(self,refund_id,reason):
        refund=self.db.one('SELECT * FROM refunds WHERE refund_id=?',(refund_id,))
        if not refund or refund['state']=='SETTLED':
            raise ValueError('Unknown or settled refund')
        self.db.run("UPDATE refunds SET state='FAILED' WHERE refund_id=?",(refund_id,))
        self.bus.publish('refund.failed',order_id=refund['order_id'],refund_id=refund_id,reason=reason)

    def eligible_monetary_amount(self,order_id):
        """Exclude points and coupons from cash refunds by using captured tender."""
        captured=self.db.one('SELECT COALESCE(SUM(amount_cents),0) AS n FROM captures WHERE order_id=?',
                             (order_id,))['n']
        reversed_=self.db.one("SELECT COALESCE(SUM(amount_cents),0) AS n FROM refunds "
                              "WHERE order_id=? AND state IN ('PENDING','SETTLED')",(order_id,))['n']
        return max(0,captured-reversed_)


def refund_retry_key(original_capture_id,request_id):
    return f'{original_capture_id}:refund:{request_id}'

def reconcile_partial_refund(capture_cents,requested_refund_cents,already_refunded_cents):
    available=max(0,capture_cents-already_refunded_cents)
    return {'allowed_cents':min(requested_refund_cents,available),
            'unallocated_cents':max(0,requested_refund_cents-available)}
