from typing import Annotated
from pydantic import BaseModel
from fastapi import Form

class UserLogin(BaseModel):
    id: str
    password: str
    
class UserRegister(BaseModel):
    first_name: str
    second_name: str
    sex: str
    birthdate: str
    biography: str
    city: str
    password: str

class UserSearch(BaseModel):
    first_name: str
    second_name: str


