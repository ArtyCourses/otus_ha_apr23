import psycopg2
import json
from uuid import uuid4, UUID
from datetime import datetime,timedelta #,timezone,timedelta
import time
import hashlib

class SocialDB:
    "DB class for OTUS Laerning project Social"
    _pghost = None
    _db = None
    _user = None
    _password = None
    _connected = False
    _connection = None
    cursor = None

    def __init__(self, host, user, password, db):
        self._pghost = host
        self._db = db
        self._user = user
        self._password = password

    def __del__(self):
        if self._connected:
            self.disconnect()

    def connect(self):
        if self._connected:
            return
        self._connection = psycopg2.connect(
            host = self._pghost,
            user = self._user,
            password = self._password,
            database = self._db#,
            #async_ = True,
        )
        self._connection.set_session(autocommit = True)
        self._connected = True
        self.cursor = self._connection.cursor()

    def disconnect(self):
        if not self._connected:
            return
        self._connected = False
        self.cursor.close()
        self._connection.close()

    def db_registeruser(self,userdata):
        result={}
        result["errors"]=[]
        
        if not self._connected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result

        #
        #result["status"] = True
        #result["userid"] = userdata
        #return result
        #check date
        try:
            if not datetime.now() > datetime.strptime(userdata["birthdate"], "%d.%m.%Y"):
                raise ValueError
        except ValueError:
            result["errors"].append("incorrect birthdate format, should be DD.MM.YYYY")
        #check sex
        if not userdata["sex"] in ["male","female","notpresent"]:
            result["errors"].append("incorrect value of 'sex', should be 'male' or 'female'")

        #stop if errors        
        if len(result["errors"]) > 0:
            result["status"] = False
            return result

        #format value
        UserID = str(uuid4())
        #registred = time.time()
        registred = datetime.now().strftime("%s")
        salt = F"{UserID}{registred}"
        hashed_pwd = hashlib.pbkdf2_hmac("sha256", userdata["password"].encode(), salt.encode(), 100_000).hex()

        formated_user = {
            'id': UserID,
            "login": UserID,
            "password": hashed_pwd,
            "registred": registred
        }
        formated_userdata= {
            'id': UserID,
            "first_name": userdata["first_name"],
            "second_name": userdata["second_name"],
            "sex": userdata["sex"],
            "birthdate": userdata["birthdate"],
            "biography": userdata["biography"],
            "city": userdata["city"]
        }

        #insert
        self.cursor.execute("insert into Users (id,login,pwd,registred) VALUES (%(id)s,%(login)s,%(password)s,to_timestamp(%(registred)s));",formated_user)
        self.cursor.execute("insert into usersdata (userid, name, surname, sex, birthdate, biography, city) values (%(id)s,%(first_name)s,%(second_name)s,%(sex)s, to_date(%(birthdate)s,'DD.MM.YYYY'),%(biography)s,%(city)s);",formated_userdata)

        #return
        result["status"] = True
        result["userid"] = UserID
        return result

    def db_chklogin(self, login, pwd):
        result={}
        result["errors"]=[]
        
        if not self._connected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result

        #check
        try:
            uuid_valid = UUID(login, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect login format")
            return result

        self.cursor.execute("select id, login, pwd, registred from users where id = %(id)s;",{'id':login})
        tuser = self.cursor.fetchall()
        if len(tuser) == 1:
            dbu_id = tuser[0][0]
            dbu_pwd = tuser[0][2]
            dbu_reg = tuser[0][3]
            #checkreg = int(time.mktime(dbu_reg.timetuple())) + dbu_reg.microsecond / 1E6 - time.timezone
            checkreg = int(time.mktime(dbu_reg.timetuple())) - time.timezone
            math = F"{dbu_id}{checkreg}"
            hashed = hashlib.pbkdf2_hmac("sha256", pwd.encode(), math.encode(), 100_000).hex()
            if dbu_pwd == hashed:
                result["status"] = True
                return result
            else:
                result["status"] = False
                result["errors"].append("Incorrect username or password")
                return result
        elif len(tuser) > 1:
            result["status"] = False
            result["errors"].append("DB Errors non unique userid")
            return result
        elif len(tuser) < 1:
            result["status"] = False
            result["errors"].append("User not found")
            return result

    def db_create_session(self, login):
        result={}
        result["errors"]=[]
        if not self._connected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result
        #check
        try:
            uuid_valid = UUID(login, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect login format")
            return result

        ses_id = str(uuid4())
        ses_st = int(time.time())
        ses_exp = int(ses_st) + timedelta(hours=24).total_seconds()
        formated_session = {
            'id': ses_id,
            "userid": login,
            "started": str(ses_st),
            "expired": ses_exp
        }
        self.cursor.execute("insert into sessions (id, userid, started, expired) VALUES (%(id)s,%(userid)s,to_timestamp(%(started)s),to_timestamp(%(expired)s));",formated_session)
        result["status"] = True
        result["token_id"] = ses_id
        return result

    def db_getuser(self,login):
        result={}
        result["errors"]=[]
        if not self._connected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result

        #check
        try:
            uuid_valid = UUID(login, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect login format")
            return result

        self.cursor.execute("select name, surname, birthdate, city, sex, biography from usersdata where userid = %(id)s;",{'id':login})
        uinfo = self.cursor.fetchall()
        if len(uinfo) == 1:
            UserInfo = {}
            UserInfo["first_name"] = uinfo[0][0]
            UserInfo["second_name"] = uinfo[0][1]
            UserInfo["birthdate"] = uinfo[0][2]
            UserInfo["city"] = uinfo[0][3]
            UserInfo["sex"] = uinfo[0][4]
            UserInfo["biography"] = uinfo[0][5]
            result["status"] = True
            result["UserInfo"] = UserInfo
            return result
        elif len(uinfo) > 1:
            result["status"] = False
            result["errors"].append("DB Errors non unique userid")
            return result
        elif len(uinfo) < 1:
            result["status"] = False
            result["errors"].append("User not found")
            return result

    def db_search(self,find_fname, find_sname):
        result={}
        result["errors"]=[]
        
        if not self._connected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result

        formated_query= {
            "fname": find_fname+"%",
            "fsurname": find_sname+"%",
        }

        self.cursor.execute("select userid, name, surname, sex, birthdate, biography, city from usersdata where name LIKE %(fname)s and surname LIKE %(fsurname)s order by userid;",formated_query)
        fusers = self.cursor.fetchall()
        if len(fusers) == 0:
            result["status"] = False
            result["errors"].append("Not found")
            return result
        finds = []
        for t_user in fusers:
            userinfo = {
                        "id" : t_user[0],
                        "first_name" : t_user[1],
                        "second_name": t_user[2],
                        "sex": t_user[3],
                        "birthdate":datetime.strftime(t_user[4],"%d.%m.%Y"),
                        "biography": t_user[5],
                        "city": t_user[6]
                    }
            finds.append(userinfo)
        
        result["status"] = True
        result["finds"] = finds
        return result