import psycopg2
import json
from uuid import uuid4, UUID
from datetime import datetime,timedelta #, timezone #,timedelta
import time
import hashlib
import tarantool
import pika

class SocialDB:
    "DB class for OTUS Laerning project Social"
    _pghost = None
    _pgport = None
    _db = None
    _chost = None
    _cport = None
    _cuser = None
    _cpwd = None
    _user = None
    _password = None
    _dbconnected = False
    _cacheconnected = False
    _connection = None
    _qhost = None
    _qport = None
    _quser = None
    _qpwd = None
    cursor = None
    cache = None
    cache_posts = None
    cache_feeds = None

    def __init__(self, dbhost, dbport, dbuser, dbpassword, dbname, cachehost, cacheport, cacheuser, chachepwd,qhost,qport,quser,qpwd):
        self._pghost = dbhost
        self._pgport = dbport
        self._db = dbname
        self._user = dbuser
        self._password = dbpassword
        self._chost = cachehost
        self._cport = cacheport
        self._cuser = cacheuser
        self._cpwd = chachepwd
        self._qhost = qhost
        self._qport = qport
        self._quser = quser
        self._qpwd = qpwd

    def __del__(self):
        if self._dbconnected or self._cacheconnected:
            self.disconnect()

    def connect(self):
        if self._dbconnected and self._cacheconnected:
            return
        if not self._dbconnected:
            self._connection = psycopg2.connect(
                host = self._pghost,
                port = self._pgport,
                user = self._user,
                password = self._password,
                database = self._db#,
                #async_ = True,
            )
            self._connection.set_session(autocommit = True)
            self._dbconnected = True
            self.cursor = self._connection.cursor()
        if not self._cacheconnected:
            self.cache = tarantool.connect(
                host = self._chost, 
                port = self._cport, 
                user = self._cuser,
                password = self._cpwd
                )
            self._cacheconnected = True
            self.cache_posts = self.cache.space('post_cache')
            self.cache_feeds = self.cache.space('feed_cache')

    def disconnect(self):
        if not self._dbconnected:
            return
        self._dbconnected = False
        self.cursor.close()
        self._connection.close()

    def db_registeruser(self,userdata):
        result={}
        result["errors"]=[]
        
        if not self._dbconnected:
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
        
        if not self._dbconnected:
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
        if not self._dbconnected:
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
        if not self._dbconnected:
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
        
        if not self._dbconnected:
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

    def db_check_session(self, sessionid):
        result={}
        result["errors"]=[]
        if not self._dbconnected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result
        #check
        ses_id = sessionid.split(' ')[1]
        b_type = sessionid.split(' ')[0]
        if b_type != 'Bearer':
            result["status"] = False
            result["errors"].append("Incorect auth type")
            return result
        try:
            uuid_valid = UUID(ses_id, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect session format")
            return result
        
        self.cursor.execute("select id, userid, started, expired from sessions where id = %(id)s;",{'id':ses_id})
        sesinfo = self.cursor.fetchall()
        if len(sesinfo) == 1:
            startat = int(time.mktime(sesinfo[0][2].timetuple())) - time.timezone
            expire = int(time.mktime(sesinfo[0][3].timetuple())) - time.timezone
            t_now = time.time()
            if startat > t_now:
                result["status"] = False
                result["errors"].append("Used before session start")
                return result
            if expire  < t_now:
                result["status"] = False
                result["errors"].append("Session expired")
                return result
            result["status"] = True
            result["userid"] = sesinfo[0][1]
            return result
        else:
            result["status"] = False
            result["errors"].append("Session not found")
            return result

    def db_friend_add(self,selfid,friendid):
        result={}
        result["errors"]=[]    
        if not self._dbconnected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result
        try:
            uuid_valid = UUID(selfid, version=4)
            uuid_valid = UUID(friendid, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect id format")
            return result
        formated_q = {
            "u_id": selfid,
            "f_id": friendid
        }
        self.cursor.execute("select * from friendships where userid = %(u_id)s and friendid = %(f_id)s",formated_q)
        chf = self.cursor.fetchall()
        if len(chf) == 0:
            self.cursor.execute("insert into friendships (userid,friendid) VALUES (%(u_id)s,%(f_id)s);",formated_q)
            result["status"] = True
            return result   
        else:
            result["status"] = False
            result["errors"].append("frienship already exist")
            return result
                
    def db_friend_del(self,selfid,friendid):
        result={}
        result["errors"]=[]
        
        if not self._dbconnected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result

        try:
            uuid_valid = UUID(selfid, version=4)
            uuid_valid = UUID(friendid, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect id format")
            return result
        formated_q = {
            "u_id": selfid,
            "f_id": friendid
        }
        self.cursor.execute("select * from friendships where userid = %(u_id)s and friendid = %(f_id)s",formated_q)
        chf = self.cursor.fetchall()
        if len(chf) == 1:
            self.cursor.execute("delete from friendships where userid = %(u_id)s and friendid = %(f_id)s",formated_q)
            result["status"] = True
            return result    
        elif len(chf) == 0:
            result["status"] = False
            result["errors"].append("Friendship not exist")
            return result
        else:
            result["status"] = False
            result["errors"].append("DB Error friendship not unique")
            return result

    def db_posts_create(self,selfid,posttext):
        result={}
        result["errors"]=[]    
        if not self._dbconnected or not self._cacheconnected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result
        try:
            uuid_valid = UUID(selfid, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect id format")
            return result
        formated_q = {
            "p_id": str(uuid4()),
            "u_id": selfid,
            "post": posttext,
            "p_date": int(time.time())
        }
        #self.cursor.execute("insert into posts (id, author_userid, content, post_date) VALUES (%(p_id)s,%(u_id)s,%(post)s,to_timestamp(%(p_date)s));",formated_q)
        self.cursor.execute("insert into posts (id, author_userid, content, post_date) VALUES (%(p_id)s,%(u_id)s,%(post)s,%(p_date)s);",formated_q)
        result["status"] = True
        result["postid"] = formated_q["p_id"]

        #add post to followers
        self.cursor.execute("select userid from friendships where friendid = %(u_id)s;",{"u_id":selfid})
        updfeed = self.cursor.fetchall()
        if len(updfeed) > 0:
            qsocial = SocialQueue(
                qhost = self._qhost,
                qport = self._qport,
                quser = self._quser,
                qpassword = self._qpwd
            )
            qsocial.connect()
            post={
                "id": formated_q["p_id"],
                "text": formated_q["post"],
                "author_user_id": formated_q["u_id"],
                "created": datetime.fromtimestamp(formated_q["p_date"] - time.timezone).strftime("%H:%M:%S %d.%m.%Y")
            }
            print(F"timezone offset: {time.timezone}")
            for follower in updfeed:
                #add to feed cache    
                self.cache.call('add_postfeed',(follower[0],formated_q["p_id"]))
                #add to existing websocket
                qsocial.addpost2feed(follower[0],post)
            qsocial.disconnect()
        return result      
        
    def db_posts_read(self,postid):
        result={}
        result["errors"]=[]    
        if not self._dbconnected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result
        try:
            uuid_valid = UUID(postid, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect id format")
            return result
        formated_q = {
            "p_id": postid,
        }
        self.cursor.execute("select id, author_userid, content, post_date from posts where id = %(p_id)s;",formated_q)
        ch_post = self.cursor.fetchall()
        if len(ch_post) == 1:
            result["status"] = True
            result["content"] = {
                "id": ch_post[0][0],
                "text": ch_post[0][2],
                "author_user_id": ch_post[0][1],
                "created": int(time.mktime(ch_post[0][3].timetuple())) - time.timezone
            }
            return result
        elif len(ch_post) == 0:
            result["status"] = False
            result["errors"].append("Post not found")
            return result
        else:
            result["status"] = False
            result["errors"].append("DB Error post id not unique")
            return result
  
    def db_posts_update(self,selfid,posttext,postid):
        result={}
        result["errors"]=[]    
        if not self._dbconnected or not self._cacheconnected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result
        try:
            uuid_valid = UUID(selfid, version=4)
            uuid_valid = UUID(postid, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect id format")
            return result
        formated_q = {
            "p_id": postid,
            "u_id": selfid,
            "post": posttext
        }
        self.cursor.execute("select author_userid from posts where id = %(p_id)s;",{"p_id": postid})
        ch_post = self.cursor.fetchall()
        if len(ch_post) == 1:
            if ch_post[0][0] == selfid:
                self.cursor.execute("update posts set content = %(post)s where id = %(p_id)s;",formated_q)
                result["status"] = True
                result["postid"] = formated_q["p_id"]
                #update_cachepost
                self.cache.call('update_cachepost',(result["postid"]))
                return result
            else:
                result["status"] = False
                result["errors"].append("Only author can edit post")
                return result                
        elif len(ch_post) == 0:
            result["status"] = False
            result["errors"].append("Friendship not exist")
            return result
        else:
            result["status"] = False
            result["errors"].append("DB Error friendship not unique")
            return result
           
    def db_posts_delete(self,postid):
        result={}
        result["errors"]=[]    
        if not self._dbconnected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result
        try:
            uuid_valid = UUID(postid, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect id format")
            return result
        formated_q = {
            "p_id": postid,
        }
        self.cursor.execute("select id from posts where id = %(p_id)s;",formated_q)
        сh_post = self.cursor.fetchall()
        if len(сh_post) == 1:
            self.cursor.execute("delete from posts where id = %(p_id)s;",formated_q)
            result["status"] = True
            return result
        elif len(сh_post) == 0:
            result["status"] = False
            result["errors"].append("Post not found")
            return result
        else:
            result["status"] = False
            result["errors"].append("DB Error post id not unique")
            return result

    def cache_postsfeed(self,userid,offset,limit):
        result={}
        result["errors"]=[]    
        if not self._dbconnected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result
        try:
            uuid_valid = UUID(userid, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect id format")
            return result
        
        userfeed = []
        user_feed = self.cache.call('get_feed',(userid,int(limit),int(offset)))
        for tpost in user_feed[0]:
            jpost = json.loads(tpost)
            jpost['created'] = datetime.fromtimestamp(jpost['created']).strftime("%H:%M:%S %d.%m.%Y")
            userfeed.append(jpost)

        result["status"] = True
        result["feed"] = userfeed 
        return result

class ShardDB:
    _pghost = None
    _pgport = None
    _db = None
    _user = None
    _password = None
    _dbconnected = False
    _connection = None
    cursor = None

    def __init__(self, dbhost, dbport, dbuser, dbpassword, dbname):
        self._pghost = dbhost
        self._pgport = dbport
        self._db = dbname
        self._user = dbuser
        self._password = dbpassword

    def __del__(self):
        if self._dbconnected:
            self.disconnect()

    def connect(self):
        if self._dbconnected:
            return
        if not self._dbconnected:
            self._connection = psycopg2.connect(
                host = self._pghost,
                user = self._user,
                password = self._password,
                database = self._db,
                port = self._pgport #,
                #async_ = True,
            )
            self._connection.set_session(autocommit = True)
            self._dbconnected = True
            self.cursor = self._connection.cursor()

    def disconnect(self):
        if not self._dbconnected:
            return
        self._dbconnected = False
        self.cursor.close()
        self._connection.close()

    def gen_dialogid(self, sender, recipient):
        if sender > recipient:
            d_id = sender + '-' + recipient
        else:
            d_id = recipient + '-' + sender
        return d_id

    def db_dialogs_send(self, sender, recipient, message):
        result={}
        result["errors"]=[]    
        if not self._dbconnected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result
        try:
            uuid_valid = UUID(sender, version=4)
            uuid_valid = UUID(recipient, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect user id format")
            return result
        
        formated_q = {
            "d_id": self.gen_dialogid(sender,recipient),
            "sender": sender,
            "recepient": recipient,
            "msgtext": message,
            "msgtime": int(time.time())
        }
        self.cursor.execute("insert into dialogs (dialogid, sender, recepient, msgtext, msgtime) VALUES (%(d_id)s,%(sender)s,%(recepient)s,%(msgtext)s,%(msgtime)s);",formated_q)
        result["status"] = True
        result["dialogid"] = formated_q["d_id"]
        return result      
    
    def db_dialogs_list(self, sender, recipient):
        result={}
        result["errors"]=[]    
        if not self._dbconnected:
            result["status"] = False
            result["errors"].append("DB not conneted")
            return result
        try:
            uuid_valid = UUID(sender, version=4)
            uuid_valid = UUID(recipient, version=4)
        except ValueError:
            result["status"] = False
            result["errors"].append("Incorect id format")
            return result
        formated_q = {
            "dialogid": self.gen_dialogid(sender,recipient),
        }
        self.cursor.execute("select sender, recepient, msgtext, msgtime from dialogs where dialogid = %(dialogid)s order by msgtime desc;",formated_q)
        dialoglist = self.cursor.fetchall()
        reslst=[]
        if len(dialoglist) > 0:
            for tmsg in dialoglist:
                reslst.append({
                    "from": tmsg[0],
                    "to": tmsg[1],
                    "in": datetime.fromtimestamp(tmsg[3]).strftime("%H:%M:%S %d.%m.%Y"),
                    "text": tmsg[2]
                })
        elif len(dialoglist) == 0:
            result["status"] = False
            result["errors"].append("Post not found")
            return result
        
        result["status"] = True
        result["dialog_content"] = reslst
        return result
    

class SocialQueue:
    _host = None
    _port = None
    _exchange = None
    _exchangetype = None
    _user = None
    _password = None
    _connected = False
    uqprefix = "feed-"
    connection = None
    channel = None

    def __init__(self, qhost, quser, qpassword, qport = 5672, qexchange = 'postedfeed', qextype = 'topic'):
        self._host = qhost
        self._port = qport
        self._user = quser
        self._password = qpassword
        self._exchange = qexchange
        self._exchangetype = qextype

    def __del__(self):
        if self._connected:
            self.connection.close()

    def connect(self):
        if self._connected:
            return
        rabcreds = pika.PlainCredentials(username=self._user,password=self._password)
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=self._host,port=self._port,credentials=rabcreds))
        #self.connection = pika.SelectConnection(pika.ConnectionParameters(host=self._host,port=self._port,credentials=rabcreds))
        self.channel = self.connection.channel()
        self.channel.exchange_declare(self._exchange,self._exchangetype,False,True,False)
        self.connected = True

    def disconnect(self):
        if not self._connected:
            return
        self.channel.close()    
        self.connection.close()
        self._connected = False

    def create_userqueue(self,userid):
        result={}
        result["errors"]=[]    
        if not self.connected:
            result["status"] = False
            result["errors"].append("rabbitmq not conneted")
            return result
        qname = F"{self.uqprefix}{userid}"
        self.channel.queue_declare(queue=qname,durable=True)
        self.channel.queue_bind(queue=qname,exchange=self._exchange,routing_key=userid)
        result["status"] = True
        result["queue"] = qname
        return result
    
    def delete_userqueue(self,userid):
        result={}
        result["errors"]=[]    
        if not self.connected:
            result["status"] = False
            result["errors"].append("rabbitmq not conneted")
            return result
        qname = F"{self.uqprefix}{userid}"
        self.channel.queue_unbind(queue=qname,exchange=self._exchange,routing_key=userid)
        self.channel.queue_delete(queue=qname)
        result["status"] = True
        return result
    
    def addpost2feed(self, userid, post):
        result={}
        result["errors"]=[]    
        if not self.connected:
            result["status"] = False
            result["errors"].append("rabbitmq not conneted")
            return result
        self.channel.basic_publish(exchange=self._exchange,routing_key=userid,body=json.dumps(post))
        result["status"] = True
        return result