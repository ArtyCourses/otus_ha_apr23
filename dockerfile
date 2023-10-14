FROM python:3.11.4

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /opt/app

RUN pip install fastapi
RUN pip install uvicorn[standard]
RUN pip install psycopg2
RUN pip install python-multipart
RUN pip install tarantool
RUN pip install pika

COPY SocialMain.py /opt/app/SocialMain.py
COPY SocialDB.py /opt/app/SocialDB.py
COPY SocialModels.py /opt/app/SocialModels.py

EXPOSE 8080
CMD ["python","SocialMain.py"]
