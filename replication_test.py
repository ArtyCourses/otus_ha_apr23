#!/usr/bin/python
from SocialDB import SocialDB
import os
import sys
import time
#

os.chdir(os.path.dirname(sys.argv[0]))
db = SocialDB(
        host = "localhost",
        user = "otuspg",
        password = "learn4otus",
        db = "SocialOtus"
    )
db.connect()

success=[]
try:
    for it in range(1,121):
        print(F"Вставка элемента {it}")
        db.cursor.execute(F"insert into repltest (testid) VALUES ('{it}');")
        success.append(it)
        time.sleep(0.5)
except Exception:
    print(F"Добавлено {len(success)} записей")
    print(success)
