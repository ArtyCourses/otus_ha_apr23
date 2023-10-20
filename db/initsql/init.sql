BEGIN;

create user haproxycheck with password 'haproxycheck';
create role replicator with login replication password 'pass';

CREATE TABLE IF NOT EXISTS public.sessions
(
    id uuid NOT NULL,
    userid uuid NOT NULL,
    started timestamp without time zone,
    expired timestamp without time zone,
    CONSTRAINT sessions_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.friendships
(
    userid uuid NOT NULL,
    friendid uuid NOT NULL
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

CREATE TABLE IF NOT EXISTS public.posts
(
    id uuid NOT NULL,
	author_userid uuid NOT NULL,
    content text COLLATE pg_catalog."default",
    post_date int8 NULL,
    CONSTRAINT posts_pkey PRIMARY KEY (id),
    CONSTRAINT fk_users_to_posts FOREIGN KEY (author_userid)
        REFERENCES public.users (id) MATCH SIMPLE
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
);

CREATE INDEX IF NOT EXISTS search_posts_by_author
    ON public.posts USING btree
    (author_userid ASC NULLS LAST)
    TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS sort_posts_by_date
    ON public.posts USING btree
    (post_date DESC NULLS LAST)
    TABLESPACE pg_default;

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

CREATE INDEX IF NOT EXISTS search_user
    ON public.usersdata USING btree
    (name COLLATE pg_catalog."default" ASC NULLS LAST, surname COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;

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