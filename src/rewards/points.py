"""Rewards platform adapter; checkout integration is feature-controlled."""
class PointsService:
    def __init__(self,db):
        self.db=db

    def create_account(self,customer_id,points):
        self.db.run('INSERT OR REPLACE INTO point_accounts VALUES (?,?)',(customer_id,points))

    def balance(self,customer_id):
        acct=self.db.one('SELECT * FROM point_accounts WHERE customer_id=?',(customer_id,))
        return acct['points'] if acct else 0

    def spend_points(self,customer_id,order_id,points):
        if points<0 or self.balance(customer_id)<points:
            raise ValueError('Insufficient points')
        self.db.run('UPDATE point_accounts SET points=points-? WHERE customer_id=?',(points,customer_id))
        self.db.run('INSERT INTO point_journal VALUES (?,?,?,?,?)',
                    (self.db.new_id('PNT'),customer_id,order_id,-points,'CHECKOUT'))
        return points//100

    def adjust(self,customer_id,order_id,delta,reason):
        self.db.run('UPDATE point_accounts SET points=points+? WHERE customer_id=?',(delta,customer_id))
        self.db.run('INSERT INTO point_journal VALUES (?,?,?,?,?)',
                    (self.db.new_id('PNT'),customer_id,order_id,delta,reason))


def point_adjustment_reference(order_id, reason, sequence):
    return f'{order_id}:POINTS:{reason}:{sequence}'
