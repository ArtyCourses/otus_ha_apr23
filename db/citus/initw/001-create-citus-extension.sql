-- wrap in transaction to ensure Docker flag always visible
alter system set wal_level = logical;

BEGIN;
CREATE EXTENSION citus;

-- add Docker flag to node metadata
UPDATE pg_dist_node_metadata SET metadata=jsonb_insert(metadata, '{docker}', 'true');
COMMIT;
