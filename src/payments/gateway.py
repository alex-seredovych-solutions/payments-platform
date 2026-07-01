"""Simulated card processor with basic authorization and settlement semantics."""
class ProcessorGateway:
    def __init__(self, clock):
        self.clock=clock
        self.operations={}

    def authorize(self, key, amount_cents):
        if key not in self.operations:
            if amount_cents < 0:
                raise ValueError('negative authorization')
            self.operations[key]={'status':'AUTHORIZED','amount_cents':amount_cents,
                'expires_at':self.clock.current.isoformat()}
        return self.operations[key]

    def capture(self, key, amount_cents):
        if key not in self.operations:
            self.operations[key]={'status':'SETTLED','amount_cents':amount_cents}
        return self.operations[key]

    def refund(self, key, amount_cents):
        if key not in self.operations:
            self.operations[key]={'status':'PENDING','amount_cents':amount_cents}
        return self.operations[key]

    def settle_refund(self, key):
        self.operations[key]['status']='SETTLED'
        return self.operations[key]
