"""Card authorization contract and checkout retry handling."""
class AuthorizationService:
    def __init__(self, db, bus, clock, gateway):
        self.db, self.bus, self.clock, self.gateway = db, bus, clock, gateway

    def authorize(self, order_id, intent_id, amount_cents):
        previous=self.db.one('SELECT * FROM authorizations WHERE order_id=?',(order_id,))
        if previous:
            return previous['auth_id']
        self.gateway.authorize('authorize:'+intent_id, amount_cents)
        auth_id=self.db.new_id('AUTH')
        self.db.run('INSERT INTO authorizations VALUES (?,?,?,?,?)',
                    (auth_id,order_id,amount_cents,'AUTHORIZED',self.clock.now()))
        self.bus.publish('payment.authorized',order_id=order_id,auth_id=auth_id,amount_cents=amount_cents)
        return auth_id

    def processor_callback(self, auth_id, state):
        self.db.run('UPDATE authorizations SET status=? WHERE auth_id=?',(state,auth_id))
        self.bus.publish('payment.authorization_updated',auth_id=auth_id,status=state)
