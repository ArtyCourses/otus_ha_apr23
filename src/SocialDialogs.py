#!/usr/bin/python

import uvicorn
import json
import os
import socket
import argparse

from fastapi import FastAPI, Request, Response, status, APIRouter
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from typing import Callable
import base64

from SocialDB import MemoryDB

import httpx
from asgi_correlation_id import CorrelationIdMiddleware
from asgi_correlation_id.context import correlation_id
from uuid import uuid4
import logging.config
import time

class TimedRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()
        async def custom_route_handler(request: Request) -> Response:
            before = time.time()
            if "HTTP_X_FORWARDED_FOR" in request.META:
                request.META["HTTP_X_PROXY_REMOTE_ADDR"] = request.META["REMOTE_ADDR"]
                parts = request.META["HTTP_X_FORWARDED_FOR"].split(",", 1)
                request.META["REMOTE_ADDR"] = parts[0]
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


#var from env
MainAppURI = os.environ["MAINAPP_URI"]
SvcAuthKey = os.environ["SVC_AUTH_KEY"]
SessionAPI = os.environ["MA_SESSIONAPI"]

#''' in-memory СУБД подсистемы диалогов
db_dialogs = MemoryDB(
    dbhost = os.environ["IMDB_HOST"],
    dbport = os.environ["IMDB_PORT"],
    dbuser = os.environ["IMDB_USER"],
    dbpassword = os.environ["IMDB_PWD"],
)
db_dialogs.connect()
#'''

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
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'correlation_id': {
            '()': 'asgi_correlation_id.CorrelationIdFilter',
            'uuid_length': 32,
        },
    },
    'formatters': {
        'web': {
            'class': 'logging.Formatter',
            'datefmt': '%H:%M:%S',
            'format': '%(levelname)s ... [%(correlation_id)s] %(name)s %(message)s',
        },
    },
    'handlers': {
        'web': {
            'class': 'logging.StreamHandler',
            'filters': ['correlation_id'],
            'formatter': 'web',
        },
    },
    'loggers': {
        'my_project': {
            'handlers': ['web'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}

@app.on_event("startup")
async def startup_event():
    configure_logging()

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger('app')

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
    logger.info(F"call monolit to checksession")
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


@router.get("/")
def read_root():
    return JSONResponse(status_code=403, content={"INFO":"Forbidden"})

@router.post("/v2/dialogs/{userid}", status_code=201)
async def post_dialog_send(userid, request: Request):
    logger.info(F"call 'v2/dialogs/<userid> send message")
    headers = request.headers
    raw_body = await request.body()
    try:
        content = json.loads(raw_body)
        if 'text' not in content:
            raise json.decoder.JSONDecodeError("wrong dialog error model","post data",1)
    except json.decoder.JSONDecodeError:
        logger.error(F"400:\tInvalid request format, need valid post model")
        return JSONResponse(status_code=400, content={"ERROR":F"Invalid request format, need valid post model"})
    if "Authorization" in headers:
        session = headers['Authorization']
        #auth = db_master.db_check_session(session)
        auth = await check_usersession(session)
        if auth["status"]:
            logger.info(F"call dialogs db function")
            fpost = db_dialogs.db_dialogs_send(auth["userid"], userid, content['text'])
            if fpost["status"]:
                return fpost['dialogid']
            else:
                logger.error(F"400:\t{fpost['errors']}")
                return JSONResponse(status_code=400, content={"ERROR":fpost["errors"]})
        else:
            logger.error(F"401:\t{auth['errors']}")
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        logger.error(F"401:\tNot authorized")
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"})


@router.get("/v2/dialogs/{userid}", status_code=200)
async def get_dialog_list(userid, request: Request):
    logger.info(F"call 'v2/dialogs/<userid> get dialog list")
    headers = request.headers
    raw_body = await request.body()
    if "Authorization" in headers:
        session = headers['Authorization']
        auth = await check_usersession(session)
        if auth["status"]:
            logger.info(F"call dialogs db function")
            fpost = db_dialogs.db_dialogs_list(auth["userid"], userid)
            if fpost["status"]:
                return fpost['dialog_content']
            else:
                logger.error(F"400:\t{fpost['errors']}")
                return JSONResponse(status_code=400, content={"ERROR":fpost["errors"]})
        else:
            logger.error(F"401:\t{auth['errors']}")
            return JSONResponse(status_code=401, content={"ERROR":auth["errors"]})
    else:
        logger.error(F"401:\tNot authorized")
        return JSONResponse(status_code=401, content={"ERROR":"Not authorized"})

app.include_router(router)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Otus course HA Arch: Dialogs service', prog='DialogsTest')
    parser.add_argument('--port','-p', dest='port', metavar='P', type=int, help='Service port', default=8080, required=False)
    parser.add_argument('--loglevel','-l', dest='loglevel', metavar='L', type=str, help='Service log level', default="info", required=False)
    args = parser.parse_args()
    svc_port = args.port
    svc_loglevel = args.loglevel
    selfip = socket.gethostbyname(socket.gethostname())
    print(F"Actual IP Addr: {selfip}")
    uvicorn.run("SocialDialogs:app", host=selfip, port=svc_port, log_level=svc_loglevel)

