"""Resolve an explicit Git object without guessing an interpretation winner."""


def object_context(store, context, object_id, object_type):
    if context.get("historical"):
        return context
    table, key = {
        "commit": ("commits", "git_object_id"),
        "tree": ("root_manifests", "tree_git_object_id"),
        "tag": ("tag_objects", "git_object_id"),
        "blob": ("text_facts", "git_object_id"),
    }[object_type]
    if store.one(
        f"SELECT 1 FROM current_git_{table} WHERE repository_uuidv4=? AND parsed_result_uuidv4=? AND {key}=?",
        (context["repository_uuidv4"], context["parsed_result_uuidv4"], object_id),
    ):
        return context
    candidates = store.all(
        f"SELECT DISTINCT f.parsed_result_uuidv4 FROM eligible_git_{table} f JOIN selected_git_acquisition_results a ON a.repository_uuidv4=f.repository_uuidv4 AND a.parsed_result_uuidv4=f.parsed_result_uuidv4 AND a.git_acquisition_id=f.git_acquisition_id WHERE f.repository_uuidv4=? AND f.{key}=? LIMIT 2",
        (context["repository_uuidv4"], object_id),
    )
    return {
        **context,
        "parsed_result_uuidv4": candidates[0][0] if len(candidates) == 1 else None,
        "historical": True,
        "selection_unresolved": len(candidates) > 1,
    }
