FROM python:3.11.4

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /opt/app

RUN pip install fastapi
RUN pip install uvicorn[standard]
RUN pip install psycopg2
RUN pip install python-multipart

COPY ./src /opt/app

EXPOSE 8080
CMD ["python","SocialMain.py"]
ENV APP_DBHOST postgres_container
ENV APP_DBNAME SocialOtus
ENV APP_DBUSER otuspg
ENV APP_DBPWD learn4otus
