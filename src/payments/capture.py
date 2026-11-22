"""Capture orchestration across orders, packages, eligibility, processor and ledger.

Package capture support is feature-controlled while the established checkout
consumer continues to handle fulfillment acceptance events.
"""
from datetime import datetime
from acme_shared.money import allocate_proportionally

class CaptureService:
    def __init__(self,db,bus,clock,gateway,settings,ledger):
        self.db,self.bus,self.clock,self.gateway,self.settings,self.ledger=(
            db,bus,clock,gateway,settings,ledger)

    def on_fulfillment_accepted(self,event):
        if self.settings.capture_after_pack_verified or self.settings.capture_after_carrier_acceptance:
            return
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(event.payload['order_id'],))
        if not order or order['status']=='DECLINED':
            return
        # Established task-acceptance capture path retained for rollout compatibility.
        self.capture_full_order(order['order_id'])

    def capture_full_order(self,order_id):
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(order_id,))
        if order is None:
            raise KeyError(order_id)
        key='capture:'+order_id
        existing=self.db.one('SELECT * FROM captures WHERE operation_key=?',(key,))
        if existing:
            return existing['capture_id']
        processor=self.gateway.capture(key,order['amount_cents'])
        capture_id=self.db.new_id('CAP')
        self.db.run('INSERT INTO captures VALUES (?,?,?,?,?,?,?,?)',
                    (capture_id,order['auth_id'],order_id,None,order['amount_cents'],
                     key,processor['status'],key))
        self.ledger.post(order_id,key,'CAPTURE',order['amount_cents'])
        self.bus.publish('payment.capture_settled',order_id=order_id,capture_id=capture_id,
                         amount_cents=order['amount_cents'],processor_operation_id=key)
        return capture_id

    def on_pack_verified(self,event):
        if self.settings.capture_after_pack_verified and not self.settings.capture_after_carrier_acceptance:
            return self.capture_package(event.payload['package_id'],stage='PACK_VERIFIED')
        return None

    def on_carrier_accepted(self,event):
        if self.settings.capture_after_carrier_acceptance:
            return self.capture_package(event.payload['package_id'],stage='CARRIER_ACCEPTED')
        return None

    def _package_amount(self,package_id):
        """Reconstruct charges from accepted line values and persistent package lineage."""
        entries=self.db.all("""SELECT pa.quantity, ol.quantity AS ordered_quantity,
                  a.card_due_cents, ol.line_id FROM package_lines pa
                  JOIN order_lines ol ON pa.line_id=ol.line_id
                  JOIN order_line_allocations a ON a.line_id=pa.line_id
                  WHERE pa.package_id=? ORDER BY ol.line_id""",(package_id,))
        if not entries:
            raise ValueError('Package has no stable order-line allocation')
        amount=0
        for entry in entries:
            if entry['quantity']>entry['ordered_quantity'] or entry['ordered_quantity']<=0:
                raise ValueError('Package quantity exceeds accepted order line')
            # Integer cent floor for partial quantities; package splitting a single
            # line requires a separate residual allocation reconciliation.
            amount+=entry['card_due_cents']*entry['quantity']//entry['ordered_quantity']
        return amount

    def capture_package(self,package_id,stage='PACK_VERIFIED'):
        if not self.settings.multi_capture_enabled:
            raise RuntimeError('Merchant multi-capture is not enabled')
        package=self.db.one('SELECT * FROM packages WHERE package_id=?',(package_id,))
        if not package:
            raise KeyError(package_id)
        order=self.db.one('SELECT * FROM orders WHERE order_id=?',(package['order_id'],))
        task=self.db.one('SELECT * FROM warehouse_tasks WHERE package_id=?',(package_id,))
        if order['status']=='CANCELLED' or order['risk_state']!='CLEAR':
            raise ValueError('Order is canceled or held by risk review')
        if not task or not task['pack_verified'] or task['state']=='EXCEPTION':
            raise ValueError('Package has no completed verification')
        if stage=='CARRIER_ACCEPTED' and not package['carrier_accepted_at']:
            raise ValueError('Carrier has not accepted custody')
        key=f'capture:{order["order_id"]}:{package_id}'
        prior=self.db.one('SELECT * FROM captures WHERE operation_key=?',(key,))
        if prior:
            return prior['capture_id']
        authorization=self.db.one('SELECT * FROM authorizations WHERE auth_id=?',(order['auth_id'],))
        if authorization['status']!='AUTHORIZED':
            raise ValueError('Authorization is not eligible for capture')
        # Provider expiration metadata is available from the gateway adapter;
        # the order-facing financial record does not carry its full lifecycle yet.
        amount=self._package_amount(package_id)
        previous=self.db.one('SELECT COALESCE(SUM(amount_cents),0) AS n FROM captures WHERE order_id=?',
                             (order['order_id'],))['n']
        if previous+amount>authorization['amount_cents']:
            raise ValueError('Aggregate capture would exceed authorization')
        response=self.gateway.capture(key,amount)
        capture_id=self.db.new_id('CAP')
        self.db.run('INSERT INTO captures VALUES (?,?,?,?,?,?,?,?)',
                    (capture_id,order['auth_id'],order['order_id'],package_id,amount,key,
                     response['status'],key))
        self.ledger.post(order['order_id'],key,'CAPTURE',amount)
        self.bus.publish('payment.capture_settled',order_id=order['order_id'],
                         package_id=package_id,capture_id=capture_id,
                         amount_cents=amount,processor_operation_id=key)
        return capture_id


def candidate_capture_allocation(order_amount_cents,per_package_weights):
    return allocate_proportionally(order_amount_cents,per_package_weights)

def verified_package_capture_key(order_id,package_id,verified):
    return f'capture:{order_id}:{package_id}' if verified else None
