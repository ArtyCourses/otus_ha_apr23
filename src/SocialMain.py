#!/usr/bin/python

import fastapi
import pydantic
import uvicorn
import json
import os
import argparse

from fastapi import Form, FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse

from SocialDB import SocialDB
from SocialModels import UserLogin
from SocialModels import UserRegister


db_master = SocialDB(
    host= os.environ["APP_DBHOST"],
    db= os.environ["APP_DBNAME"],
    user= os.environ["APP_DBUSER"],
    password= os.environ["APP_DBPWD"]
)
db_master.connect()

app = fastapi.FastAPI()

@app.get("/")
def read_root():
    return JSONResponse(status_code=403, content={"INFO":"Forbidden"})

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
    UserData = db_master.db_getuser(userid)
    if UserData["status"]:
        return UserData["UserInfo"]
    else:
        if "User not found" in usercheck["errors"]:
            return JSONResponse(status_code=404, content={"ERROR":"User not found"})            
        else:
            return JSONResponse(status_code=400, content={"ERROR":"Incorrect data"})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Otus course HA Arch', prog='SocialTest')
    parser.add_argument('--port','-p', dest='port', metavar='P', type=int, help='Service port', default=8080, required=False)
    parser.add_argument('--loglevel','-l', dest='loglevel', metavar='L', type=str, help='Service log level', default="info", required=False)
    args = parser.parse_args()
    svc_port = args.port
    svc_loglevel = args.loglevel
    uvicorn.run("SocialMain:app", host="0.0.0.0", port=svc_port, log_level=svc_loglevel)

