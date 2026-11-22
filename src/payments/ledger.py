"""Financial audit entries, capture totals and reconciliation exceptions."""
class FinancialLedger:
    def __init__(self,db,clock):
        self.db,self.clock=db,clock

    def post(self,order_id,operation_id,kind,amount_cents):
        if kind not in ('CAPTURE','REFUND','VOID','ADJUSTMENT'):
            raise ValueError('Unrecognized financial operation')
        if not operation_id:
            raise ValueError('Processor operation reference is required')
        journal_id=self.db.new_id('JRN')
        self.db.run('INSERT INTO journal VALUES (?,?,?,?,?,?)',
                    (journal_id,order_id,operation_id,kind,amount_cents,self.clock.now()))
        return journal_id

    def post_once(self,order_id,operation_id,kind,amount_cents):
        prior=self.db.one('SELECT * FROM journal WHERE operation_id=? AND kind=?',(operation_id,kind))
        if prior:
            if prior['amount_cents']!=amount_cents:
                raise ValueError('Same ledger operation has different amount')
            return prior['journal_id']
        return self.post(order_id,operation_id,kind,amount_cents)

    def total_captured(self,order_id):
        result=self.db.one("SELECT COALESCE(SUM(amount_cents),0) AS amount FROM journal "
                           "WHERE order_id=? AND kind='CAPTURE'",(order_id,))
        return result['amount']

    def reconcile(self,order_id):
        captured=self.db.one('SELECT COALESCE(SUM(amount_cents),0) AS n FROM captures WHERE order_id=?',
                             (order_id,))['n']
        journal=self.total_captured(order_id)
        duplicates=self.db.all("SELECT operation_id,kind,COUNT(*) AS n FROM journal WHERE order_id=? "
                               "GROUP BY operation_id,kind HAVING COUNT(*)>1",(order_id,))
        package_unlinked=self.db.one('SELECT COUNT(*) AS n FROM captures WHERE order_id=? AND package_id IS NULL',
                                     (order_id,))['n']
        return {'captured':captured,'journal':journal,'balanced':captured==journal,
                'duplicate_operation_count':len(duplicates),
                'captures_without_package':package_unlinked,
                'duplicates':duplicates}
