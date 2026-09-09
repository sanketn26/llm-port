# JSON-Schema primitive type -> (isinstance check, human label for errors).
from dataclasses import dataclass


_TYPE_CHECKS: dict[str, tuple[type | tuple[type, ...], str]] = {
    "string": (str, "a string"),
    "integer": (int, "an integer"),
    "number": ((int, float), "a number"),
    "boolean": (bool, "a boolean"),
    "object": (dict, "an object"),
}

# Item-type label matching the legacy "list of str" phrasing.
_ITEM_LABEL = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}

def _is_array_of(value: object, item_type: str) -> bool:
    if not isinstance(value, list):
        return False
    py_type = _TYPE_CHECKS.get(item_type, (object, ""))[0]
    return all(isinstance(item, py_type) for item in value)


@dataclass(frozen=True)
class ArgSpec:
    """One top-level argument of a tool: its declared type, enum, and whether
    it is required. Derived from the tool's JSON-Schema ``properties`` entry."""

    name: str
    type: str = ""
    description: str = ""
    required: bool = False
    enum: tuple = ()
    item_type: str | None = None  # element type when ``type == "array"``

    def type_error(self, value: object) -> str | None:
        """A human message if ``value`` violates this arg's type/enum, else None."""
        # array check
        if self.type == "array":
            item = self.item_type or "string"
            if not _is_array_of(value, item):
                return f"argument '{self.name}' must be a list of {_ITEM_LABEL.get(item, item)}"
        # primitive type check
        elif self.type in _TYPE_CHECKS:
            py_type, label = _TYPE_CHECKS[self.type]
            # bool is an int subclass — reject it where a number is asked.
            if not isinstance(value, py_type) or (
                self.type in ("integer", "number") and isinstance(value, bool)
            ):
                return f"argument '{self.name}' must be {label}"
        # enum check
        if self.enum and value not in self.enum:
            allowed = ", ".join(repr(v) for v in self.enum)
            return f"argument '{self.name}' must be one of: {allowed}"
        return None

@dataclass(frozen=True)
class ToolSpec:
    """A tool definition as a typed object — the single source of truth.

    ``parameters`` keeps the full (possibly deeply nested) JSON-Schema so
    ``to_wire`` reproduces the exact provider schema; ``args`` is the flattened
    top-level view used for validation and instruction rendering.
    """

    name: str
    description: str = ""
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    args: tuple[ArgSpec, ...] = ()
    guidance: str = ""
