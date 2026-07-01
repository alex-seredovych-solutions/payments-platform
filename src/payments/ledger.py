"""Financial journal: entries retain processor operation references."""
class FinancialLedger:
    def __init__(self, db, clock):
        self.db,self.clock=db,clock

    def post(self, order_id, operation_id, kind, amount_cents):
        jid=self.db.new_id('JRN')
        self.db.run('INSERT INTO journal VALUES (?,?,?,?,?,?)',
            (jid,order_id,operation_id,kind,amount_cents,self.clock.now()))
        return jid

    def total_captured(self, order_id):
        row=self.db.one("SELECT COALESCE(SUM(amount_cents),0) AS amount FROM journal WHERE order_id=? AND kind='CAPTURE'",(order_id,))
        return row['amount']

    def reconcile(self, order_id):
        captured=self.db.one('SELECT COALESCE(SUM(amount_cents),0) AS n FROM captures WHERE order_id=?',(order_id,))['n']
        return {'captured':captured,'journal':self.total_captured(order_id),
                'balanced':captured==self.total_captured(order_id)}
