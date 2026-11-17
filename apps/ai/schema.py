"""A small JSON-schema subset validator (type, properties, required, items, enum) for model output.
Enough for ETqa's schemas without adding a dependency."""

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "number": (int, float), "integer": int}


def errors(value, schema: dict, path: str = "$") -> list[str]:
    out: list[str] = []
    expected = schema.get("type")
    if expected and not isinstance(value, _TYPES[expected]) or (expected in ("number", "integer") and isinstance(value, bool)):
        return [f"{path}: expected {expected}"]
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r} not in {schema['enum']}")
    if expected == "object":
        for key in schema.get("required", []):
            if key not in value:
                out.append(f"{path}.{key}: missing")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                out += errors(value[key], sub, f"{path}.{key}")
    if expected == "array" and "items" in schema:
        for i, item in enumerate(value):
            out += errors(item, schema["items"], f"{path}[{i}]")
    return out
