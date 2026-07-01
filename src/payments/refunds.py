"""Refund lifecycle and provider callbacks."""
class RefundService:
    def __init__(self, db,bus,clock,gateway,ledger):
        self.db,self.bus,self.clock,self.gateway,self.ledger=db,bus,clock,gateway,ledger

    def request(self, order_id, amount_cents, request_id):
        key='refund:'+request_id
        earlier=self.db.one('SELECT * FROM refunds WHERE operation_key=?',(key,))
        if earlier:
            return earlier['refund_id']
        capture=self.db.one('SELECT * FROM captures WHERE order_id=? ORDER BY capture_id LIMIT 1',(order_id,))
        if not capture:
            raise ValueError('Cannot refund an uncaptured order')
        if amount_cents > capture['amount_cents']:
            raise ValueError('Refund exceeds captured amount')
        self.gateway.refund(key,amount_cents)
        rid=self.db.new_id('REF')
        self.db.run('INSERT INTO refunds VALUES (?,?,?,?,?,?)',
                    (rid,order_id,capture['capture_id'],amount_cents,'PENDING',key))
        self.bus.publish('refund.requested',order_id=order_id,refund_id=rid,amount_cents=amount_cents)
        return rid

    def settle(self, refund_id):
        refund=self.db.one('SELECT * FROM refunds WHERE refund_id=?',(refund_id,))
        self.gateway.settle_refund(refund['operation_key'])
        self.db.run("UPDATE refunds SET state='SETTLED' WHERE refund_id=?",(refund_id,))
        self.ledger.post(refund['order_id'],refund['operation_key'],'REFUND',-refund['amount_cents'])
        self.bus.publish('refund.settled',order_id=refund['order_id'],refund_id=refund_id,
                         amount_cents=refund['amount_cents'])
