"""Fake payment provider with idempotent operations and authorization expiry.

The provider is richer than the current ACME integration: the client must still
persist expiry, correlate callbacks and select the correct capture trigger.
"""
from datetime import timedelta

class ProcessorGateway:
    def __init__(self,clock):
        self.clock=clock
        self.operations={}
        self.failed_operations=set()

    def fail_next(self,key):
        self.failed_operations.add(key)

    def _guard(self,key,amount_cents):
        if not key or amount_cents < 0:
            raise ValueError('Invalid processor operation')
        if key in self.failed_operations:
            self.failed_operations.remove(key)
            raise ConnectionError(f'Processor operation temporarily unavailable: {key}')

    def authorize(self,key,amount_cents):
        self._guard(key,amount_cents)
        if key not in self.operations:
            expiration=(self.clock.current+timedelta(days=7)).isoformat()
            self.operations[key]={'status':'AUTHORIZED','amount_cents':amount_cents,
                                  'expires_at':expiration,'operation_key':key}
        elif self.operations[key]['amount_cents']!=amount_cents:
            raise ValueError('Conflicting amount for existing authorization request')
        return dict(self.operations[key])

    def capture(self,key,amount_cents):
        self._guard(key,amount_cents)
        if key not in self.operations:
            self.operations[key]={'status':'SETTLED','amount_cents':amount_cents,
                                  'operation_key':key,'received_at':self.clock.now()}
        elif self.operations[key]['amount_cents']!=amount_cents:
            raise ValueError('Capture operation key reused for different amount')
        return dict(self.operations[key])

    def void(self,key,authorization_key):
        auth=self.operations.get(authorization_key)
        if auth is None or auth['status']!='AUTHORIZED':
            return {'status':'NOT_VOIDABLE','operation_key':key}
        self.operations.setdefault(key,{'status':'VOID_CONFIRMED','operation_key':key,
                                        'amount_cents':auth['amount_cents']})
        auth['status']='VOIDED'
        return dict(self.operations[key])

    def refund(self,key,amount_cents):
        self._guard(key,amount_cents)
        if key not in self.operations:
            self.operations[key]={'status':'PENDING','amount_cents':amount_cents,'operation_key':key}
        elif self.operations[key]['amount_cents']!=amount_cents:
            raise ValueError('Refund request changed for idempotency key')
        return dict(self.operations[key])

    def settle_refund(self,key):
        operation=self.operations[key]
        if operation['status'] not in ('PENDING','SETTLED'):
            raise ValueError('Refund must be processing before settlement')
        operation['status']='SETTLED'
        operation['settled_at']=self.clock.now()
        return dict(operation)
