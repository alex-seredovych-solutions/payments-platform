"""Processor callback state consolidation."""
class CallbackReducer:
    def __init__(self,db,bus):
        self.db,self.bus=db,bus
        self.latest={}

    def accept(self, operation_id, state, received_at):
        current=self.latest.get(operation_id)
        if current is None or received_at>=current['received_at']:
            self.latest[operation_id]={'status':state,'received_at':received_at}
            self.bus.publish('payment.processor_status',operation_id=operation_id,status=state)
        return self.latest[operation_id]['status']
