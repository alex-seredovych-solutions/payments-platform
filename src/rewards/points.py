"""Loyalty point reservations and immutable redemption journal.

Loyalty APIs exist in this code, but checkout remains disabled by default and
is not guaranteed atomic with financial authorization across services.
"""
class PointsService:
    def __init__(self,db):
        self.db=db

    def create_account(self,customer_id,points):
        if points<0:
            raise ValueError('Negative balances are not permitted')
        self.db.run('INSERT OR REPLACE INTO point_accounts VALUES (?,?)',(customer_id,points))

    def balance(self,customer_id):
        account=self.db.one('SELECT * FROM point_accounts WHERE customer_id=?',(customer_id,))
        return account['points'] if account else 0

    def spend_points(self,customer_id,order_id,points):
        if points<0 or points%100:
            raise ValueError('Points must be nonnegative and divisible by 100')
        existing=self.db.one("SELECT * FROM point_journal WHERE customer_id=? AND order_id=? "
                             "AND reason='CHECKOUT'",(customer_id,order_id))
        if existing:
            if -existing['delta']!=points:
                raise ValueError('Conflicting points redemption for accepted order')
            return points//100
        with self.db.transaction():
            updated=self.db.run('UPDATE point_accounts SET points=points-? '
                                'WHERE customer_id=? AND points>=?',(points,customer_id,points))
            if updated.rowcount!=1:
                raise ValueError('Insufficient points')
            self.db.run('INSERT INTO point_journal VALUES (?,?,?,?,?)',
                        (self.db.new_id('PNT'),customer_id,order_id,-points,'CHECKOUT'))
        return points//100

    def adjust(self,customer_id,order_id,delta,reason):
        if not reason:
            raise ValueError('Adjustment reason is required')
        with self.db.transaction():
            updated=self.db.run('UPDATE point_accounts SET points=points+? '
                                'WHERE customer_id=? AND points+?>=0',(delta,customer_id,delta))
            if updated.rowcount!=1:
                raise ValueError('Invalid adjustment or missing account')
            journal_id=self.db.new_id('PNT')
            self.db.run('INSERT INTO point_journal VALUES (?,?,?,?,?)',
                        (journal_id,customer_id,order_id,delta,reason))
        return journal_id

    def history(self,customer_id):
        return self.db.all('SELECT * FROM point_journal WHERE customer_id=? ORDER BY id',(customer_id,))


def point_adjustment_reference(order_id,reason,sequence):
    return f'{order_id}:POINTS:{reason}:{sequence}'
