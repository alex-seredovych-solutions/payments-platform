"""Processor callback consolidation and optional terminal-state precedence."""

FINAL_STATES={'CAPTURE_SETTLED','VOID_CONFIRMED','REFUND_SETTLED','REFUND_FAILED'}
PENDING_STATES={'CAPTURE_PENDING','VOID_PENDING','REFUND_PENDING'}

class CallbackReducer:
    def __init__(self,db,bus,settings=None):
        self.db,self.bus,self.settings=db,bus,settings
        self.latest={}
        self.seen=set()

    def accept(self,operation_id,state,received_at,callback_id=None):
        if state not in FINAL_STATES|PENDING_STATES|{'AUTHORIZED'}:
            raise ValueError(f'Unknown processor state: {state}')
        if callback_id is not None and callback_id in self.seen:
            return self.latest.get(operation_id,{}).get('status')
        if callback_id is not None:
            self.seen.add(callback_id)
        previous=self.latest.get(operation_id)
        strict=self.settings and self.settings.immutable_event_precedence
        if strict and previous and previous['status'] in FINAL_STATES and state in PENDING_STATES:
            return previous['status']
        # The default reducer prefers latest receiver timestamp when merging callbacks.
        if previous is None or received_at>=previous['received_at']:
            self.latest[operation_id]={'status':state,'received_at':received_at,
                                       'callback_id':callback_id}
            self.bus.publish('payment.processor_status',operation_id=operation_id,
                             status=state,received_at=received_at)
        return self.latest[operation_id]['status']
