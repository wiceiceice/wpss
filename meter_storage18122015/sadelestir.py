import sqlite3
from datetime import datetime
import time

def sadelestir():

    save_time = datetime.now()

    # Connecting to the database file
    conn2 = sqlite3.connect('tenantdata.sqlite')

    if (save_time.hour==14):

        print "Sayaclari sadelestiriyor"

        cursor1 = conn2.cursor()
        cursor2 = conn2.cursor()

        cursor1.execute('''

        DELETE FROM tenant_counter

        WHERE EXISTS (SELECT * FROM tenant_counter AS r
        WHERE r.id = tenant_counter.id AND r.date = tenant_counter.date 
        AND r.sayacdeger > tenant_counter.sayacdeger)

        ''')

        conn2.commit()

        cursor2.execute('''

        delete   from tenant_counter

        where    rowid not in
        (
         select  min(rowid)
         from    tenant_counter AS r
         where r.id = tenant_counter.id
         and r.date = tenant_counter.date
         and r.sayacdeger = tenant_counter.sayacdeger)

         ''')

    conn2.commit()
    conn2.close()
    return

sadelestir()

print 'bitti'
