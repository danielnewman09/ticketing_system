"""
JSON Schema utilities for tool definition conversion across backends.
"""

import re


def collect_all_defs(schema):
    """Collect all $defs from every level of a JSON Schema."""
    all_defs = {}
    if isinstance(schema, dict):
        if "$defs" in schema:
            all_defs.update(schema["$defs"])
        for v in schema.values():
            all_defs.update(collect_all_defs(v))
    elif isinstance(schema, list):
        for item in schema:
            all_defs.update(collect_all_defs(item))
    return all_defs


def resolve_refs(schema, defs=None):
    """Recursively inline all $ref references in a JSON Schema."""
    if defs is None:
        defs = collect_all_defs(schema)

    if isinstance(schema, dict):
        if "$ref" in schema:
            ref_name = schema["$ref"].rsplit("/", 1)[-1]
            return resolve_refs(defs[ref_name], defs)
        result = {}
        for k, v in schema.items():
            if k == "$defs":
                continue
            result[k] = resolve_refs(v, defs)
        return result
    elif isinstance(schema, list):
        return [resolve_refs(item, defs) for item in schema]
    return schema


def convert_tool_anthropic_to_openai(tool):
    """Convert an Anthropic tool definition to OpenAI format."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": resolve_refs(tool["input_schema"]),
        },
    }


def strip_think_tags(text):
    """Extract useful content from model output that may contain <think> blocks.

    If there is content outside the think tags, return that.
    If the entire response is inside think tags (common with reasoning models),
    return the think content itself — for a reasoner, the thinking IS the output.
    """
    # Try stripping think tags first
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if stripped:
        return stripped

    # Everything was inside think tags — extract the thinking content
    think_match = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
    if think_match:
        return think_match.group(1).strip()

    # No think tags at all, return as-is
    return text.strip()
