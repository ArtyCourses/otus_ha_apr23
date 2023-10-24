#!/usr/bin/python

import uvicorn
import json
import os
import socket
import argparse
import asyncio

from fastapi import FastAPI, Request, status, WebSocket, Cookie, Depends, WebSocketException, WebSocketDisconnect
from websockets import exceptions as webexcept
from fastapi.responses import JSONResponse
import base64
import httpx

from SocialDB import CounterDB




#var from env
MainAppURI = os.environ["MAINAPP_URI"]
SvcAuthKey = os.environ["SVC_AUTH_KEY"]
SessionAPI = os.environ["MA_SESSIONAPI"]

db_counters = CounterDB(
    dbhost = os.environ["IMDB_HOST"],
    dbport = os.environ["IMDB_PORT"],
    dbuser = os.environ["IMDB_USER"],
    dbpassword = os.environ["IMDB_PWD"],
)
db_counters.connect()

dbro_counters = CounterDB(
    dbhost = os.environ["RODB_HOST"],
    dbport = os.environ["RODB_PORT"],
    dbuser = os.environ["RODB_USER"],
    dbpassword = os.environ["RODB_PWD"],
)
dbro_counters.connect()

async def check_usersession(token):
    result = {}
    result["errors"] = []
    ses_id = token.split(' ')[1]
    b_type = token.split(' ')[0]
    if b_type != 'Bearer':
        result["status"] = False
        result["errors"].append("Incorect auth type")
        return result
    rurl = F"{MainAppURI}{SessionAPI}"
    svckey = base64.b64encode(bytes(SvcAuthKey, 'utf-8')).decode('utf-8')
    rhead = {
        "Authorization": "Bearer " + str(svckey)
    }
    rdata = {
        "session": ses_id
    }
    async with httpx.AsyncClient() as rses:
        request_auth = await rses.post(rurl, headers=rhead, json=rdata)

    if request_auth.status_code == 200:
        result["status"] = True
        result["userid"] = request_auth.json()["userid"]
    elif request_auth.status_code == 401:
        result["status"] = False
        result["errors"] = request_auth.json()["ERROR"]
    elif request_auth.status_code == 403:
        result["status"] = False
        result["errors"] = "Incorrect dialog service deployment"
    else:
        result["status"] = False
        result["errors"] = "samething goes wrong"
    return result

app = FastAPI()

@app.get("/")
def read_root():
    return JSONResponse(status_code=403, content={"INFO":"Forbidden"})

@app.get("/counters", status_code=200)
async def get_counter(request: Request):
    headers = request.headers
    counter_par = dict(request.query_params)
    if not 'sender' in counter_par or not 'recipient' in counter_par:
        return JSONResponse(status_code=400, content={"ERROR":"Missing requered params"})
    p_send = counter_par['sender']
    p_recep = counter_par['recipient']
    if "Authorization" in headers:
        session = headers['Authorization']
        ses_id = session.split(' ')[1]
        b_type = session.split(' ')[0]
        if b_type != 'Bearer':
            print(F"403:\tIncorect svc auth type")
            return JSONResponse(status_code=403, content={"ERROR":"Incorect svc auth type"})
        if base64.b64decode(bytes(ses_id, 'utf-8')).decode('utf-8') != SvcAuthKey:
            print(F"403:\tIncorect svc auth key")
            return JSONResponse(status_code=403, content={"ERROR":"Incorect svc auth key"})
        tek_count = db_counters.get_counter(p_send,p_recep)
        if not tek_count is None:
            return tek_count
        else:
            return(F"400:\tNull return of get_counter")
    else:
        print(F"403:\tEmpty svc key")
        return JSONResponse(status_code=403, content={"ERROR":"Empty svc key"})

@app.put("/counters",status_code=201)
async def create_counter(request: Request):
    headers = request.headers
    counter_par = dict(request.query_params)
    if not 'sender' in counter_par or not 'recipient' in counter_par:
        return JSONResponse(status_code=400, content={"ERROR":"Missing requered params"})
    p_send = counter_par['sender']
    p_recep = counter_par['recipient']
    if "Authorization" in headers:
        session = headers['Authorization']
        ses_id = session.split(' ')[1]
        b_type = session.split(' ')[0]
        if b_type != 'Bearer':
            print(F"403:\tIncorect svc auth type")
            return JSONResponse(status_code=403, content={"ERROR":"Incorect svc auth type"})
        if base64.b64decode(bytes(ses_id, 'utf-8')).decode('utf-8') != SvcAuthKey:
            print(F"403:\tIncorect svc auth key")
            return JSONResponse(status_code=403, content={"ERROR":"Incorect svc auth key"})
        tek_count = db_counters.create_counter(p_send,p_recep)
        if not tek_count is None:
            return tek_count
        else:
            return(F"400:\tNull return of create_counter")
    else:
        print(F"403:\tEmpty svc key")
        return JSONResponse(status_code=403, content={"ERROR":"Empty svc key"})

@app.post("/counters",status_code=202)
async def increment_counter(request: Request):
    headers = request.headers
    counter_par = dict(request.query_params)
    if not 'sender' in counter_par or not 'recipient' in counter_par or not 'count' in counter_par:
        return JSONResponse(status_code=400, content={"ERROR":"Missing requered params"})
    p_send = counter_par['sender']
    p_recep = counter_par['recipient']
    p_count = counter_par['count']
    if "Authorization" in headers:
        session = headers['Authorization']
        ses_id = session.split(' ')[1]
        b_type = session.split(' ')[0]
        if b_type != 'Bearer':
            print(F"403:\tIncorect svc auth type")
            return JSONResponse(status_code=403, content={"ERROR":"Incorect svc auth type"})
        if base64.b64decode(bytes(ses_id, 'utf-8')).decode('utf-8') != SvcAuthKey:
            print(F"403:\tIncorect svc auth key")
            return JSONResponse(status_code=403, content={"ERROR":"Incorect svc auth key"})
        tek_count = db_counters.inc_counter(p_send,p_recep,p_count)
        if not tek_count is None:
            return tek_count
        else:
            return(F"400:\tNull return of create_counter")
    else:
        print(F"403:\tEmpty svc key")
        return JSONResponse(status_code=403, content={"ERROR":"Empty svc key"})

@app.delete("/counters",status_code=200)
async def decrement_counter(request: Request):
    headers = request.headers
    counter_par = dict(request.query_params)
    if not 'sender' in counter_par or not 'recipient' in counter_par or not 'count' in counter_par:
        return JSONResponse(status_code=400, content={"ERROR":"Missing requered params"})
    p_send = counter_par['sender']
    p_recep = counter_par['recipient']
    p_count = counter_par['count']
    if "Authorization" in headers:
        session = headers['Authorization']
        ses_id = session.split(' ')[1]
        b_type = session.split(' ')[0]
        if b_type != 'Bearer':
            print(F"403:\tIncorect svc auth type")
            return JSONResponse(status_code=403, content={"ERROR":"Incorect svc auth type"})
        if base64.b64decode(bytes(ses_id, 'utf-8')).decode('utf-8') != SvcAuthKey:
            print(F"403:\tIncorect svc auth key")
            return JSONResponse(status_code=403, content={"ERROR":"Incorect svc auth key"})
        tek_count = db_counters.dec_counter(p_send,p_recep,p_count)
        if not tek_count is None:
            return tek_count
        else:
            return(F"400:\tNull return of create_counter")
    else:
        print(F"403:\tEmpty svc key")
        return JSONResponse(status_code=403, content={"ERROR":"Empty svc key"})

async def ws_auth(ws:WebSocket, userid: str|None = Cookie(default=None)):
    shead = ws.headers
    if "Authorization" in shead:
        session = shead['Authorization']
        auth = check_usersession(session)
        print(auth)
        if auth["status"]:
            ws.cookies["userid"] = auth["userid"]
            return auth["userid"]
        else:
            if userid is None:
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
            else:
                return userid

@app.websocket("/counters")
async def feed_posted(socws:WebSocket,chsession: str = Depends(ws_auth)):
    await socws.accept()
    print(F"connected {chsession}")
    try:
        while True:
            ping = await socws.receive_text()
            lst_conters = dbro_counters.get_user_counters(chsession)
            if lst_conters['status']:
                pong = lst_conters['counters']
                await socws.send_json(pong)
            else:
                await socws.send_text(lst_conters['errors'])
            await asyncio.sleep(1)
    except webexcept.ConnectionClosed:
        print(F"disconnected {chsession}")
    except WebSocketDisconnect:
        print(F"disconnected {chsession}")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Otus course HA Arch: Counter service', prog='CountersTest')
    parser.add_argument('--port','-p', dest='port', metavar='P', type=int, help='Service port', default=8080, required=False)
    parser.add_argument('--loglevel','-l', dest='loglevel', metavar='L', type=str, help='Service log level', default="info", required=False)
    args = parser.parse_args()
    svc_port = args.port
    svc_loglevel = args.loglevel
    selfip = socket.gethostbyname(socket.gethostname())
    print(F"Actual IP Addr: {selfip}")
    uvicorn.run("SocialCounter:app", host=selfip, port=svc_port, log_level=svc_loglevel)

