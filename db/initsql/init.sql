BEGIN;

CREATE TABLE IF NOT EXISTS public.sessions
(
    id uuid NOT NULL,
    userid uuid NOT NULL,
    started timestamp without time zone,
    expired timestamp without time zone,
    CONSTRAINT sessions_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.users
(
    id uuid NOT NULL,
    login text COLLATE pg_catalog."default" NOT NULL,
    pwd text COLLATE pg_catalog."default" NOT NULL,
    registred timestamp without time zone,
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT users_login_key UNIQUE (login)
);

CREATE TABLE IF NOT EXISTS public.usersdata
(
    userid uuid NOT NULL,
    name text COLLATE pg_catalog."default",
    surname text COLLATE pg_catalog."default",
    sex text COLLATE pg_catalog."default",
    biography text COLLATE pg_catalog."default",
    city text COLLATE pg_catalog."default",
    birthdate date,
    CONSTRAINT usersdata_pkey PRIMARY KEY (userid)
);

ALTER TABLE IF EXISTS public.sessions
    ADD CONSTRAINT fk_users_to_sessions FOREIGN KEY (userid)
    REFERENCES public.users (id) MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE NO ACTION;


ALTER TABLE IF EXISTS public.usersdata
    ADD CONSTRAINT fk_users_to_usersdata FOREIGN KEY (userid)
    REFERENCES public.users (id) MATCH SIMPLE
    ON UPDATE NO ACTION
    ON DELETE NO ACTION;
CREATE INDEX IF NOT EXISTS usersdata_pkey
    ON public.usersdata(userid);

END;