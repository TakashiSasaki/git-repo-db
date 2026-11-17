"""Revalidate only the selected collection's stored membership authority."""

from repo_catalog.domain.collection_members import validate_collection_members


def validate_stored_collection_members(db, owner, kind, encoded):
    validate_collection_members(owner, kind, encoded)
    bad = db.execute(
        """SELECT 1 FROM json_each(?) j WHERE NOT EXISTS(
          SELECT 1 FROM resources r WHERE r.service_instance_uuidv4=json_extract(j.value,'$[0]')
          AND r.resource_kind=json_extract(j.value,'$[1]')
          AND r.provider_resource_id=json_extract(j.value,'$[2]')
          AND (? NOT IN ('reviews','comments','threads','documents') OR
           (r.identifier_namespace_kind=? AND r.identifier_namespace_id=?))) LIMIT 1""",
        (encoded, kind, owner.resource_kind, owner.provider_resource_id),
    ).fetchone()
    if bad is not None:
        raise ValueError(
            "Stored collection member namespace/resource is absent or mismatched"
        )
