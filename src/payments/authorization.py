"""Authorization and financial reservation of final checkout amount."""
class AuthorizationService:
    def __init__(self,db,bus,clock,gateway):
        self.db,self.bus,self.clock,self.gateway=db,bus,clock,gateway

    def authorize(self,order_id,intent_id,amount_cents):
        if amount_cents < 0:
            raise ValueError('Cannot authorize negative funds')
        previous=self.db.one('SELECT * FROM authorizations WHERE order_id=?',(order_id,))
        if previous:
            if previous['amount_cents']!=amount_cents:
                raise ValueError('Existing order authorization has different amount')
            return previous['auth_id']
        operation_key='authorize:'+intent_id
        response=self.gateway.authorize(operation_key,amount_cents)
        if response['status']!='AUTHORIZED':
            raise RuntimeError('Payment authorization not confirmed')
        auth_id=self.db.new_id('AUTH')
        self.db.run('INSERT INTO authorizations VALUES (?,?,?,?,?)',
                    (auth_id,order_id,amount_cents,'AUTHORIZED',self.clock.now()))
        self.bus.publish('payment.authorized',order_id=order_id,auth_id=auth_id,
                         amount_cents=amount_cents,processor_operation_key=operation_key)
        return auth_id

    def processor_callback(self,auth_id,state):
        record=self.db.one('SELECT * FROM authorizations WHERE auth_id=?',(auth_id,))
        if not record:
            raise KeyError(auth_id)
        accepted_states={'AUTHORIZED','DECLINED','VOID_PENDING','VOID_CONFIRMED','EXPIRED'}
        if state not in accepted_states:
            raise ValueError('Unknown authorization state')
        if record['status']=='VOID_CONFIRMED' and state=='AUTHORIZED':
            return record['status']
        self.db.run('UPDATE authorizations SET status=? WHERE auth_id=?',(state,auth_id))
        self.bus.publish('payment.authorization_updated',order_id=record['order_id'],
                         auth_id=auth_id,status=state)
        return state

    def expiry_for(self,intent_id):
        """Gateway knows expiry, but legacy authorization rows do not persist it."""
        return self.gateway.operations.get('authorize:'+intent_id,{}).get('expires_at')


def authorization_audit_fields(intent_id,auth_id):
    return {'intent_id':intent_id,'auth_id':auth_id,'operation_type':'AUTHORIZE'}

def authorization_timeout_key(intent_id,provider_attempt):
    return f'{intent_id}:auth-attempt:{provider_attempt}'

AUTHORIZATION_REVIEW_GROUP='eng-payments'
