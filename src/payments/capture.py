"""Payment collection worker driven by fulfillment and processor outcomes."""
class CaptureService:
    def __init__(self, db, bus, clock, gateway, settings, ledger):
        self.db,self.bus,self.clock,self.gateway,self.settings,self.ledger=db,bus,clock,gateway,settings,ledger

    def on_fulfillment_accepted(self, event):
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(event.payload['order_id'],))
        if not order or order['status']=='DECLINED':
            return
        self.capture_full_order(order['order_id'])

    def capture_full_order(self, order_id):
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(order_id,))
        operation_key='capture:'+order_id
        existing=self.db.one('SELECT * FROM captures WHERE operation_key=?',(operation_key,))
        if existing:
            return existing['capture_id']
        self.gateway.capture(operation_key,order['amount_cents'])
        capture_id=self.db.new_id('CAP')
        self.db.run('INSERT INTO captures VALUES (?,?,?,?,?,?,?,?)',
           (capture_id,order['auth_id'],order_id,None,order['amount_cents'],operation_key,'SETTLED',operation_key))
        self.ledger.post(order_id,operation_key,'CAPTURE',order['amount_cents'])
        self.bus.publish('payment.capture_settled',order_id=order_id,capture_id=capture_id,
                         amount_cents=order['amount_cents'])
        return capture_id

    def on_pack_verified(self, event):
        if self.settings.capture_after_pack_verified:
            self.capture_full_order(event.payload['order_id'])


def candidate_capture_allocation(order_amount_cents, per_package_weights):
    from acme_shared.money import allocate_proportionally
    return allocate_proportionally(order_amount_cents, per_package_weights)
