-- wrap in transaction to ensure Docker flag always visible
alter system set wal_level = logical;

BEGIN;
CREATE EXTENSION citus;

-- add Docker flag to node metadata
UPDATE pg_dist_node_metadata SET metadata=jsonb_insert(metadata, '{docker}', 'true');
COMMIT;

BEGIN;
CREATE TABLE IF NOT EXISTS public.dialogs
(
	dialogid text NULL,
	sender uuid NOT NULL,
	recepient uuid NOT NULL,
	msgtext text NULL,
	msgtime int8 NULL,
	CONSTRAINT dialogs_pk PRIMARY KEY (dialogid,msgtime)
);

COMMIT;