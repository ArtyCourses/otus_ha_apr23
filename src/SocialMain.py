#!/usr/bin/python

import fastapi
import pydantic
import uvicorn
import json
import os
import argparse
import asyncio
import httpx

from fastapi import FastAPI, Request, Response, status, APIRouter, HTTPException, WebSocket, Cookie, Depends, WebSocketException, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from websockets import exceptions as webexcept
from fastapi.routing import APIRoute
from typing import Callable

from SocialDB import SocialDB
from SocialDB import ShardDB
from SocialDB import MemoryDB
from SocialModels import UserLogin
from SocialModels import UserRegister
from SocialModels import UserSearch
from SocialDB import SocialQueue

import time
from random import randint
import base64
import logging
from asgi_correlation_id import CorrelationIdMiddleware
from asgi_correlation_id.context import correlation_id
from uuid import uuid4
import logging.config


db_master = SocialDB(
    dbhost = os.environ["APP_M_DBHOST"],
    dbport = os.environ["APP_M_DBPORT"],
    dbuser = os.environ["APP_M_DBUSER"],
    dbpassword = os.environ["APP_M_DBPWD"],
    dbname = os.environ["APP_M_DBNAME"],
    cachehost = os.environ["APP_M_CHOST"],
    cacheport = os.environ["APP_M_CPORT"],
    cacheuser = os.environ["APP_M_CUSER"],
    chachepwd = os.environ["APP_M_CPWD"],
    qhost = os.environ["QUEUE_HOST"],
    qport = os.environ["QUEUE_PORT"],
    quser = os.environ["QUEUE_USER"],
    qpwd = os.environ["QUEUE_PWD"]
    )
db_master.connect()

''' Шардированная СУБД подсистемы диалогов
db_dialogs = ShardDB(
    dbhost = os.environ["APP_M_SHARDDB"],
    dbport = os.environ["APP_M_SHARDPORT"],
    dbuser = os.environ["APP_M_DBUSER"],
    dbpassword = os.environ["APP_M_DBPWD"],
    dbname = os.environ["APP_M_DBNAME"],
)
db_dialogs.connect()
#'''
#''' in-memory СУБД подсистемы диалогов
db_dialogs = MemoryDB(
    dbhost = os.environ["IMDB_HOST"],
    dbport = os.environ["IMDB_PORT"],
    dbuser = os.environ["IMDB_USER"],
    dbpassword = os.environ["IMDB_PWD"],
)
db_dialogs.connect()
#'''
SvcAuthKey = os.environ["SVC_AUTH_KEY"]
DialogsURI = os.environ["SVC_DIALOGS"]

class TimedRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()
        async def custom_route_handler(request: Request) -> Response:
            before = time.time()
            req = request.scope
            lmsg = F"pre-route\t{req['client'][0]}:{req['client'][1]} '{request.method} {req['path']} {req['scheme'].upper()}/{req['http_version']}'" 
            logger.info(lmsg)
            response: Response = await original_route_handler(request)
            duration = time.time() - before
            response.headers["X-Response-Time"] = str(duration)
            lmsg = F"post-route\tresponse code: '{response.status_code}'; request duration: {duration}"
            logger.info(lmsg)
            return response
        return custom_route_handler

from logging.config import dictConfig
def configure_logging() -> None:
    dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': False,
            'filters': {  # correlation ID filter must be added here to make the %(correlation_id)s formatter work
                'correlation_id': {
                    '()': 'asgi_correlation_id.CorrelationIdFilter',
                    'uuid_length': 8,
                },
            },
            'formatters': {
                'console': {
                    'class': 'logging.Formatter',
                    'datefmt': '%H:%M:%S',
                    # formatter decides how our console logs look, and what info is included.
                    # adding %(correlation_id)s to this format is what make correlation IDs appear in our logs
                    #'format': '%(levelname)s:\t\b%(asctime)s %(name)s:%(lineno)d [%(correlation_id)s] %(message)s',
                    'format': '%(levelname)s:\t\b%(name)s:%(lineno)d [%(correlation_id)s] %(message)s',
                },
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    # Filter must be declared in the handler, otherwise it won't be included
                    'filters': ['correlation_id'],
                    'formatter': 'console',
                },
            },
            # Loggers can be specified to set the log-level to log, and which handlers to use
            'loggers': {
                # project logger
                'app': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': True},
                # third-party package loggers
                'databases': {'handlers': ['console'], 'level': 'WARNING'},
                'httpx': {'handlers': ['console'], 'level': 'INFO'},
                'asgi_correlation_id': {'handlers': ['console'], 'level': 'WARNING'},
            },
        }
    )

app = FastAPI()
router = APIRouter(route_class=TimedRoute)
app.add_middleware(
    CorrelationIdMiddleware,
    header_name='X-Request-ID',
    generator=lambda: uuid4().hex,
    validator=None,
    transformer=lambda a: a,
)

@app.on_event("startup")
async def startup_event():
    configure_logging()

logger = logging.getLogger('app')

@app.get("/")
def read_root():
    return JSONResponse(status_code=403, content={"INFO":"Forbidden"})

@router.post("/sessioncheck", status_code=200)
async def svc_checksession(request: Request):
    logger.info(F"call 'checksession'")
    headers = request.headers
    raw_body = await request.body()
    try:
        content = json.loads(raw_body)
        if 'session' not in content:
            raise json.decoder.JSONDecodeError("wrong dialog error model","post data",1)
    except json.decoder.JSONDecodeError:
        return JSONResponse(status_code=400, content={"ERROR":F"Invalid checksession format"})
    if "Authorization" in headers:
        session = headers['Authorization']
        ses_id = session.split(' ')[1]
        b_type = session.split(' ')[0]
        if b_type != 'Bearer':
            logger.error(F"403:\tIncorect svc auth type")
            return JSONResponse(status_code=403, content={"ERROR":"Incorect svc auth type"})
        if base64.b64decode(bytes(ses_id, 'utf-8')).decode('utf-8') != SvcAuthKey:
            logger.error(F"403:\tIncorect svc auth key")
            return JSONResponse(status_code=403, content={"ERROR":"Incorect svc auth key"})
        auth = db_master.db_check_session(F"Bearer {content['session']}")
        if auth["status"]:
            return auth
        else:
            logger.error(F"401:\t{auth['errors']}")
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        logger.error(F"403:\tEmpty svc key")
        return JSONResponse(status_code=403, content={"ERROR":"Empty svc key"})

@app.post("/login", status_code=200)
async def post_login(request: Request):
    reqs = await request.form()
    creds = UserLogin.parse_obj(dict(reqs))
    usercheck = db_master.db_chklogin(creds.id, creds.password)
    if not usercheck["status"]:
        if "User not found" in usercheck["errors"]:
            return JSONResponse(status_code=404, content={"ERROR":"User not found"})
        else:
            return JSONResponse(status_code=400, content={"ERROR":"Incorrect username or password","MSG":usercheck["errors"]})
    else:
        session = db_master.db_create_session(creds.id)
        if session["status"]:
            return {session["token_id"]}
        else:
            return JSONResponse(status_code=500, content={"ERROR":"Error while create session"})

@app.post("/user/register",status_code=201)
async def post_register(request: Request):
    reqs = await request.form()
    UserData = UserRegister.parse_obj(dict(reqs))
    UserID =  db_master.db_registeruser(UserData.dict())
    if UserID["status"]:
        return {UserID["userid"]}
    else:
        return JSONResponse(status_code=400, content={"ERROR":UserID["errors"]})

@app.get("/user/get/{userid}")
def get_userinfo(userid):
    #UserData = db_slave.db_getuser(userid)
    UserData = db_master.db_getuser(userid)
    if UserData["status"]:
        return UserData["UserInfo"]
    else:
        if "User not found" in UserData["errors"]:
            return JSONResponse(status_code=404, content={"ERROR":"User not found"})            
        else:
            return JSONResponse(status_code=400, content={"ERROR":"Incorrect data"})

@app.get("/user/search",status_code=200)
async def post_register(request: Request):
    reqs = request.query_params
    UserData = UserSearch.parse_obj(dict(reqs))
    SearchData =  db_master.db_search(UserData.first_name, UserData.second_name)
    if SearchData["status"]:
        return SearchData["finds"]
    else:
        return JSONResponse(status_code=400, content={"ERROR":SearchData["errors"]})


@app.put("/friend/add/{userid}")
async def put_friend_add(userid, request: Request):
    headers = request.headers
    if "Authorization" in headers:
        session = request.headers['Authorization']
        auth = db_master.db_check_session(session)
        if auth["status"]:
            fadd = db_master.db_friend_add(auth["userid"],userid)
            if fadd["status"]:
                return "Пользователь успешно указал своего друга"
            else:
                return JSONResponse(status_code=400, content={"ERROR":fadd["errors"]})
        else:
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"})

@app.put("/friend/delete/{userid}")
async def put_friend_del(userid, request: Request):
    headers = request.headers
    if "Authorization" in headers:
        session = request.headers['Authorization']
        auth = db_master.db_check_session(session)
        if auth["status"]:
            fdel = db_master.db_friend_del(auth["userid"],userid)
            if fdel["status"]:
                return "Пользователь успешно удалил из друзей пользователя"
            else:
                return JSONResponse(status_code=400, content={"ERROR":fdel["errors"]})
        else:
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"})

@app.post("/post/create", status_code=200)
async def post_posts_create(request: Request):
    headers = request.headers
    raw_body = await request.body()
    try:
        content = json.loads(raw_body)
        if 'text' not in content:
            raise json.decoder.JSONDecodeError("wrong post model","post data",1)
    except json.decoder.JSONDecodeError:
        return JSONResponse(status_code=400, content={"ERROR":F"Invalid request format, need valid post model"})
    if "Authorization" in headers:
        session = headers['Authorization']
        auth = db_master.db_check_session(session)
        if auth["status"]:
            fpost = db_master.db_posts_create(auth["userid"],content['text'])
            if fpost["status"]:
                return fpost['postid']
            else:
                return JSONResponse(status_code=400, content={"ERROR":fpost["errors"]})
        else:
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"})

@app.get("/post/get/{postid}", status_code=200)
async def get_posts_read(postid):
    gpost = db_master.db_posts_read(postid)
    if gpost["status"]:
        return gpost['content']
    else:
        return JSONResponse(status_code=400, content={"ERROR":gpost["errors"]})

@app.put("/post/update", status_code=200)
async def put_posts_update(request: Request):
    headers = request.headers
    raw_body = await request.body()
    try:
        content = json.loads(raw_body)
        if ('text' not in content) or ('id' not in content):
            raise json.decoder.JSONDecodeError("wrong post model","post data",1)
    except json.decoder.JSONDecodeError:
        return JSONResponse(status_code=400, content={"ERROR":F"Invalid request format, need valid post model"})
    if "Authorization" in headers:
        session = headers['Authorization']
        auth = db_master.db_check_session(session)
        if auth["status"]:
            fpost = db_master.db_posts_update(auth["userid"], content['text'], content['id'])
            if fpost["status"]:
                return fpost['postid']
            else:
                return JSONResponse(status_code=400, content={"ERROR":fpost["errors"]})
        else:
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"})

@app.put("/post/delete/{postid}", status_code=200)
async def put_posts_delete(postid, request: Request):
    headers = request.headers
    if "Authorization" in headers:
        session = headers['Authorization']
        auth = db_master.db_check_session(session)
        if auth["status"]:
            fpost = db_master.db_posts_delete(postid)
            if fpost["status"]:
                return "Deleted"
            else:
                return JSONResponse(status_code=400, content={"ERROR":fpost["errors"]})
        else:
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"})

@app.get("/post/feed", status_code=200)
async def get_posts_feed(request: Request):
    headers = request.headers
    feed_par = dict(request.query_params)
    fOffset = 0
    if 'offset' in feed_par:
        if feed_par['offset'].isdigit():
            fOffset = feed_par['offset']
    fLimit = 10
    if 'limit' in feed_par:
        if feed_par['limit'].isdigit():
            fLimit = feed_par['limit']
    if "Authorization" in headers:
        session = headers['Authorization']
        auth = db_master.db_check_session(session)
        if auth["status"]:
            gfeed = db_master.cache_postsfeed(auth["userid"],fOffset,fLimit)
            if gfeed["status"]:
                return gfeed["feed"]
            else:
                return JSONResponse(status_code=400, content={"ERROR":gfeed["errors"]})
        else:
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"})
''' old release (monolith)
@app.post("/dialog/{userid}/send", status_code=200)
async def post_dialog_send(userid, request: Request):
    headers = request.headers
    raw_body = await request.body()
    try:
        content = json.loads(raw_body)
        if 'text' not in content:
            raise json.decoder.JSONDecodeError("wrong dialog error model","post data",1)
    except json.decoder.JSONDecodeError:
        return JSONResponse(status_code=400, content={"ERROR":F"Invalid request format, need valid post model"})
    if "Authorization" in headers:
        session = headers['Authorization']
        auth = db_master.db_check_session(session)
        if auth["status"]:
            fpost = db_dialogs.db_dialogs_send(auth["userid"], userid, content['text'])
            if fpost["status"]:
                return fpost['dialogid']
            else:
                return JSONResponse(status_code=400, content={"ERROR":fpost["errors"]})
        else:
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"})

@app.get("/dialog/{userid}/list", status_code=200)
async def get_dialog_list(userid, request: Request):
    headers = request.headers
    raw_body = await request.body()
    if "Authorization" in headers:
        session = headers['Authorization']
        auth = db_master.db_check_session(session)
        if auth["status"]:
            fpost = db_dialogs.db_dialogs_list(auth["userid"], userid)
            if fpost["status"]:
                return fpost['dialog_content']
            else:
                return JSONResponse(status_code=400, content={"ERROR":fpost["errors"]})
        else:
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"})
#'''
#''' new realese, backport for old clients
@router.post("/dialog/{userid}/send", status_code=200)
async def post_dialog_send(userid, request: Request):
    logger.warning(F"call 'dialog/.../send': deprecated")
    DeprecatedHeader = {"Warning": '299 - "Deprecated API"'}
    headers={"Warning": '299 - "Deprecated API"'}
    headers = request.headers
    raw_body = await request.body()
    try:
        content = json.loads(raw_body)
        if 'text' not in content:
            raise json.decoder.JSONDecodeError("wrong dialog error model","post data",1)
    except json.decoder.JSONDecodeError:
        logger.error(F"400:\tInvalid request format, need valid post model")
        return JSONResponse(status_code=400, content={"ERROR":F"Invalid request format, need valid post model"},headers=DeprecatedHeader)
    if "Authorization" in headers:
        rhead = {
            "Authorization": headers['Authorization']
        }
        rdata = content
        svc_dialogs = F"{DialogsURI}{userid}"
        logger.info(F"redirect to version 2 of service: deprecated")
        async with httpx.AsyncClient() as rses:
            request_auth = await rses.post(svc_dialogs, headers=rhead, json=rdata)
        return JSONResponse(status_code=request_auth.status_code, content=request_auth.json(),headers=DeprecatedHeader)
    else:
        logger.error(F"401:\tNot authorized")
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"},headers=DeprecatedHeader)

@router.get("/dialog/{userid}/list", status_code=200)
async def get_dialog_list(userid, request: Request):
    logger.warning(F"call 'dialog/.../list': deprecated")
    DeprecatedHeader = {"Warning": '299 - "Deprecated API"'}
    headers = request.headers
    if "Authorization" in headers:
        rhead = {
            "Authorization": headers['Authorization']
        }
        svc_dialogs = F"{DialogsURI}{userid}"
        logger.info(F"redirect to version 2 of service: deprecated")
        async with httpx.AsyncClient() as rses:
            request_auth = await rses.get(svc_dialogs, headers=rhead)
        return JSONResponse(status_code=request_auth.status_code, content=request_auth.json(),headers=DeprecatedHeader)
    else:
        logger.error(F"401:\tNot authorized")
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"},headers=DeprecatedHeader)

#'''
async def ws_auth(ws:WebSocket, userid: str|None = Cookie(default=None)):
    shead = ws.headers
    if "Authorization" in shead:
        session = shead['Authorization']
        auth = db_master.db_check_session(session)
        if auth["status"]:
            ws.cookies["userid"] = auth["userid"]
            return auth["userid"]
        else:
            if userid is None:
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
            else:
                return userid

@app.websocket("/post/feed/posted")
async def feed_posted(socws:WebSocket,chsession: str = Depends(ws_auth)):
    await socws.accept()
    print(F"connected {chsession}")
    qsocial = SocialQueue(os.environ["QUEUE_HOST"],os.environ["QUEUE_USER"],os.environ["QUEUE_PWD"],)
    qsocial.connect()
    userq = qsocial.create_userqueue(chsession)
    qname = userq['queue']
    try:
        while True:
            frun = True
            while frun:
                msg_method, msg_header, msg_body = qsocial.channel.basic_get(qname)
                if msg_method:
                    msg = json.loads(msg_body)
                    await socws.send_json(msg)
                    qsocial.channel.basic_ack(msg_method.delivery_tag)
                else:
                    frun = False
            #workaround to check if client disconnected without sending new post
            # + asyncio.sleep(1) alter
            try:
                await asyncio.wait_for(
                    socws.receive_text(), 1#0.0001
                )
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(4)
    except webexcept.ConnectionClosed:
        print(F"disconnected {chsession}")
    except WebSocketDisconnect:
        print(F"disconnected {chsession}")
    finally:
        qsocial.delete_userqueue(chsession)
        qsocial.disconnect()

app.include_router(router)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Otus course HA Arch', prog='SocialTest')
    parser.add_argument('--port','-p', dest='port', metavar='P', type=int, help='Service port', default=8080, required=False)
    parser.add_argument('--loglevel','-l', dest='loglevel', metavar='L', type=str, help='Service log level', default="info", required=False)
    args = parser.parse_args()
    svc_port = args.port
    svc_loglevel = args.loglevel
    uvicorn.run("SocialMain:app", host="0.0.0.0", port=svc_port, log_level=svc_loglevel)

