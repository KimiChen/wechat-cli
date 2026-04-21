"""Helpers for consistent command JSON payloads."""


def normalize_failures(failures):
    if not failures:
        return None
    return [str(item) for item in failures if item]


def build_result(scope, *, count=0, limit=None, offset=None, failures=None, **fields):
    result = {
        "scope": scope,
        "count": count,
        "failures": normalize_failures(failures),
    }
    if offset is not None:
        result["offset"] = offset
    if limit is not None:
        result["limit"] = limit
    result.update(fields)
    return result


def build_collection_result(scope, item_key, items, *, limit=None, offset=None, failures=None, **fields):
    collection = list(items)
    result = build_result(
        scope,
        count=len(collection),
        limit=limit,
        offset=offset,
        failures=failures,
        **fields,
    )
    result[item_key] = collection
    return result
