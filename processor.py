import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv


ENV_PATHS = ("WEB_REPO_PATH", "MOBILE_REPO_PATH")


def load_repo_paths() -> Dict[str, str]:
    """Load repository paths from .env and expand '~' into the user home directory."""
    load_dotenv()

    repo_paths: Dict[str, str] = {}
    for env_name in ENV_PATHS:
        raw_path = os.getenv(env_name)
        if not raw_path:
            continue

        repo_paths[env_name] = os.path.expanduser(raw_path)

    return repo_paths


def read_readme(repo_path: str) -> str:
    """Return README.md contents from the repository root, if present."""
    if not os.path.isdir(repo_path):
        return ""

    readme_path = os.path.join(repo_path, "README.md")
    if not os.path.exists(readme_path):
        return ""

    with open(readme_path, "r", encoding="utf-8") as readme_file:
        return readme_file.read()


def extract_event_payload(json_path: str) -> Dict[str, Any]:
    """Build a compact event description from a schema JSON file."""
    with open(json_path, "r", encoding="utf-8") as json_file:
        data = json.load(json_file)

    if not isinstance(data, dict):
        return {}

    # Keep only schema-like JSON files and skip service configs such as package.json.
    if "properties" not in data and "title" not in data:
        return {}

    properties = data.get("properties") or {}
    parameters = list(properties.keys())
    event_name = data.get("title") or os.path.splitext(os.path.basename(json_path))[0]

    return {
        "event_name": event_name,
        "parameters": parameters,
        "parameter_schemas": {
            name: summarize_schema(schema) for name, schema in properties.items()
        },
        "source_file": json_path,
    }


def summarize_schema(schema: Any) -> Dict[str, Any]:
    if not isinstance(schema, dict):
        return {}

    summary: Dict[str, Any] = {}

    if "description" in schema:
        summary["description"] = schema["description"]

    if "$ref" in schema:
        summary["ref"] = schema["$ref"]
        return summary

    schema_type = schema.get("type")
    if schema_type:
        summary["type"] = schema_type

    if schema_type == "array":
        summary["items"] = summarize_array_items(schema.get("items"))
    elif schema_type == "object" and isinstance(schema.get("properties"), dict):
        summary["properties"] = {
            name: summarize_schema(value)
            for name, value in schema["properties"].items()
        }

    if "enum" in schema:
        summary["enum"] = schema["enum"]

    return summary


def summarize_array_items(items: Any) -> Dict[str, Any]:
    if not isinstance(items, dict):
        return {}

    if "$ref" in items:
        return {"ref": items["$ref"]}

    item_type = items.get("type")
    summary: Dict[str, Any] = {}

    if "description" in items:
        summary["description"] = items["description"]

    if item_type:
        summary["type"] = item_type

    if item_type == "array":
        summary["items"] = summarize_array_items(items.get("items"))
    elif item_type == "object":
        summary["properties"] = {
            name: summarize_schema(value)
            for name, value in (items.get("properties") or {}).items()
        }

    return summary


def collect_json_schemas(repo_path: str) -> List[Dict[str, Any]]:
    """Recursively find all JSON files in a repository and extract event data."""
    collected: List[Dict[str, Any]] = []

    if not os.path.isdir(repo_path):
        return collected

    for root, _, files in os.walk(repo_path):
        for file_name in files:
            if not file_name.endswith(".json"):
                continue

            json_path = os.path.join(root, file_name)
            try:
                payload = extract_event_payload(json_path)
            except (json.JSONDecodeError, OSError):
                # Skip unreadable or invalid JSON files so one bad file does not stop processing.
                continue

            if payload:
                collected.append(payload)

    return collected


def collect_repositories_data() -> Dict[str, Dict[str, Any]]:
    """Collect README text and JSON schema summaries for repositories from .env."""
    repositories_data: Dict[str, Dict[str, Any]] = {}

    for env_name, repo_path in load_repo_paths().items():
        events = collect_json_schemas(repo_path)
        repositories_data[env_name] = {
            "repo_path": repo_path,
            "path_exists": os.path.isdir(repo_path),
            "readme_text": read_readme(repo_path),
            "events": events,
            "array_examples": collect_array_examples(events),
        }

    return repositories_data


def collect_array_examples(events: List[Dict[str, Any]], limit: int = 30) -> List[Dict[str, Any]]:
    examples: List[Dict[str, Any]] = []

    for event in events:
        for parameter_name, schema in (event.get("parameter_schemas") or {}).items():
            if schema.get("type") != "array":
                continue

            examples.append(
                {
                    "event_name": event.get("event_name", ""),
                    "parameter_name": parameter_name,
                    "schema": schema,
                }
            )

            if len(examples) >= limit:
                return examples

    return examples


if __name__ == "__main__":
    print(
        json.dumps(
            collect_repositories_data(),
            ensure_ascii=False,
            indent=2,
        )
    )
