from django.db import migrations


FORWARD = """
CREATE UNIQUE INDEX IF NOT EXISTS win_node_one_root_per_volume
    ON win_node (volume_id) WHERE parent_id IS NULL;

CREATE OR REPLACE FUNCTION win_node_parent_guard() RETURNS trigger AS $$
DECLARE
    walk_id integer;
    seen integer[] := ARRAY[]::integer[];
    parent_kind text;
    parent_volume integer;
BEGIN
    IF NEW.parent_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NEW.id IS NOT NULL AND NEW.parent_id = NEW.id THEN
        RAISE EXCEPTION 'win_node cannot be its own parent';
    END IF;
    SELECT kind, volume_id INTO parent_kind, parent_volume
      FROM win_node WHERE id = NEW.parent_id;
    IF parent_kind IS NULL THEN
        RAISE EXCEPTION 'win_node parent_id does not resolve';
    END IF;
    IF parent_kind <> 'folder' THEN
        RAISE EXCEPTION 'win_node parent must be a folder';
    END IF;
    IF parent_volume <> NEW.volume_id THEN
        RAISE EXCEPTION 'win_node parent must share volume_id';
    END IF;
    walk_id := NEW.parent_id;
    WHILE walk_id IS NOT NULL LOOP
        IF NEW.id IS NOT NULL AND walk_id = NEW.id THEN
            RAISE EXCEPTION 'win_node parent cycle';
        END IF;
        IF walk_id = ANY (seen) THEN
            RAISE EXCEPTION 'win_node parent cycle';
        END IF;
        seen := seen || walk_id;
        SELECT parent_id INTO walk_id FROM win_node WHERE id = walk_id;
    END LOOP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS win_node_parent_guard_trg ON win_node;
CREATE TRIGGER win_node_parent_guard_trg
    BEFORE INSERT OR UPDATE OF parent_id, volume_id, kind
    ON win_node
    FOR EACH ROW EXECUTE FUNCTION win_node_parent_guard();

CREATE OR REPLACE FUNCTION win_ace_owner_rights_guard() RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM win_sid s
        WHERE s.id = NEW.trustee_sid_id AND s.sid_string = 'S-1-3-4'
    ) THEN
        RAISE EXCEPTION 'OWNER_RIGHTS (S-1-3-4) ACE trustee is refused';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS win_ace_owner_rights_guard_trg ON win_ace;
CREATE TRIGGER win_ace_owner_rights_guard_trg
    BEFORE INSERT OR UPDATE OF trustee_sid_id
    ON win_ace
    FOR EACH ROW EXECUTE FUNCTION win_ace_owner_rights_guard();
"""

REVERSE = """
DROP TRIGGER IF EXISTS win_ace_owner_rights_guard_trg ON win_ace;
DROP FUNCTION IF EXISTS win_ace_owner_rights_guard();
DROP TRIGGER IF EXISTS win_node_parent_guard_trg ON win_node;
DROP FUNCTION IF EXISTS win_node_parent_guard();
DROP INDEX IF EXISTS win_node_one_root_per_volume;
"""


def apply_postgres(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FORWARD)


def unapply_postgres(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(REVERSE)


class Migration(migrations.Migration):

    dependencies = [
        ("winfs", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(apply_postgres, unapply_postgres),
    ]
