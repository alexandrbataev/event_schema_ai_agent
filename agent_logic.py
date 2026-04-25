import copy
import json
import os
import re
from typing import Any, Optional

from dotenv import load_dotenv
from openai import APIError
from openai import OpenAI


class TrackingAgent:
    def __init__(
        self,
        agent_md_path: str = "agent.md",
        model: Optional[str] = None,
    ) -> None:
        load_dotenv()

        self.agent_md_path = agent_md_path
        self.system_prompt = self._read_text_file(agent_md_path)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )

    def get_suggestions(
        self,
        requirements: Any,
        existing_events: Any,
    ) -> dict[str, Any]:
        explicitly_mentioned_events = self._find_explicit_event_mentions(
            requirements=requirements,
            existing_events=existing_events,
        )
        relevant_existing_events = self._select_relevant_existing_events(
            requirements=requirements,
            existing_events=explicitly_mentioned_events or existing_events,
        )

        user_prompt = (
            "Проанализируй требования и существующие события. "
            "Верни только валидный JSON без markdown.\n"
            "Сначала мысленно выполни 4 шага:\n"
            "1. Выдели из текста только реально упомянутые экраны, UI-элементы, действия пользователя и важные исходы.\n"
            "2. Определи, какие продуктовые метрики действительно можно измерить по этим действиям.\n"
            "3. Сопоставь это с существующими событиями и переиспользуй их, если смысл совпадает.\n"
            "4. Создай новые события только там, где без них нельзя покрыть сценарий.\n\n"
            "Запрещено:\n"
            "- придумывать экраны, кнопки, флоу или метрики, которых нет в требованиях;\n"
            "- предлагать абстрактные события без конкретного UI-контекста;\n"
            "- добавлять параметры без явной аналитической пользы;\n"
            "- перечислять все текущие параметры уже существующего события.\n\n"
            "Правила отбора:\n"
            "- включай только действительно полезные события для понимания поведения, конверсии, выбора, ошибок и ключевых состояний фичи;\n"
            "- если событие уже существует, верни его только если нужно добавить новые параметры именно под эту фичу;\n"
            "- для существующего события в parameters перечисляй только новые параметры, а не весь текущий набор;\n"
            "- если для существующего события ничего добавлять не нужно, не включай его в ответ.\n\n"
            "Если в требованиях явно указано существующее событие по имени и перечислено, что нужно добавить, "
            "не предлагай другие события без прямой необходимости.\n\n"
            f"Явно упомянутые существующие события: {self._to_pretty_json(explicitly_mentioned_events)}\n\n"
            "Правила для типов массивов:\n"
            "- используй `array[string]`, `array[number]`, `array[boolean]` для простых массивов;\n"
            "- используй `array[ref:DefinitionName]` для массива объектов через existing definition;\n"
            "- используй `array[object]` только если реально нужен новый inline-объект;\n"
            "- для вложенных массивов используй запись вида `array[array[ref:DefinitionName]]`;\n"
            "- для `array[object]` обязательно возвращай родительский параметр и дочерние поля в dot notation.\n\n"
            "Пример ожидаемого формата для существующего события с новым массивом объектов:\n"
            "{\n"
            '  "events": [\n'
            "    {\n"
            '      "exists": "Да",\n'
            '      "event_name": "Returns Page Opened",\n'
            '      "description": "Просмотр экрана со списком оформленных возвратов",\n'
            '      "parameters": [\n'
            "        {\n"
            '          "name": "items",\n'
            '          "type": "array[object]",\n'
            '          "description": "Список отображенных возвратов"\n'
            "        },\n"
            "        {\n"
            '          "name": "items.lineItemUuid",\n'
            '          "type": "string",\n'
            '          "description": "UUID позиции возврата"\n'
            "        },\n"
            "        {\n"
            '          "name": "items.shipmentNumber",\n'
            '          "type": "string",\n'
            '          "description": "Номер заказа или доставки, связанный с возвратом"\n'
            "        },\n"
            "        {\n"
            '          "name": "items.status",\n'
            '          "type": "string",\n'
            '          "description": "Статус возврата"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Используй строго такую структуру:\n"
            "{\n"
            '  "events": [\n'
            "    {\n"
            '      "exists": "Да" или "Нет",\n'
            '      "event_name": "Название события в Title Case",\n'
            '      "description": "Описание события",\n'
            '      "parameters": [\n'
            "        {\n"
            '          "name": "parameter_name",\n'
            '          "type": "string",\n'
            '          "description": "Описание параметра",\n'
            '          "possible_values": "value1,value2,value3"\n'
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"Требования:\n{self._to_pretty_json(requirements)}\n\n"
            "Релевантные существующие события из репозитория "
            f"(отфильтрованные по тексту требований, {len(relevant_existing_events)} шт.):\n"
            f"{self._to_pretty_json(relevant_existing_events)}"
        )

        return self._request_json(user_prompt)

    def generate_json(
        self,
        final_table: Any,
        readme_content: str,
        array_examples: Optional[Any] = None,
        existing_events: Optional[Any] = None,
    ) -> dict[str, Any]:
        return self._build_json_schemas(
            final_table=final_table,
            existing_events=existing_events,
        )

    def _request_json(self, user_prompt: str) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except APIError:
            # Some proxy/model combinations do not support json_object mode.
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Model returned an empty response")

        return self._parse_json_response(content)

    @staticmethod
    def _to_pretty_json(payload: Any) -> str:
        if isinstance(payload, str):
            return payload

        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _read_text_file(path: str) -> str:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()

    @staticmethod
    def _parse_json_response(content: str) -> dict[str, Any]:
        candidates = [content.strip()]

        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3:
                candidates.append("\n".join(lines[1:-1]).strip())

        start_index = stripped.find("{")
        end_index = stripped.rfind("}")
        if start_index != -1 and end_index != -1 and end_index > start_index:
            candidates.append(stripped[start_index : end_index + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                return parsed

        raise ValueError(f"Model did not return valid JSON: {content}")

    @staticmethod
    def _tokenize_text(value: Any) -> set[str]:
        text = str(value).lower()
        return {
            token
            for token in re.findall(r"[a-zA-Zа-яА-Я0-9_]+", text)
            if len(token) >= 3
        }

    def _select_relevant_existing_events(
        self,
        requirements: Any,
        existing_events: Any,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        if not isinstance(existing_events, list):
            return []

        requirement_tokens = self._tokenize_text(requirements)
        if not requirement_tokens:
            return existing_events[:limit]

        scored_events = []
        for event in existing_events:
            if not isinstance(event, dict):
                continue

            event_tokens = self._tokenize_text(event.get("event_name", ""))
            for parameter in event.get("parameters", []):
                event_tokens.update(self._tokenize_text(parameter))

            overlap = len(requirement_tokens & event_tokens)
            name = str(event.get("event_name", "")).lower()

            # Boost common analytics verbs and UI concepts often present in feature texts.
            for token in requirement_tokens:
                if token in name:
                    overlap += 2

            if overlap > 0:
                scored_events.append((overlap, event))

        scored_events.sort(key=lambda item: item[0], reverse=True)
        relevant = [event for _, event in scored_events[:limit]]

        if relevant:
            return relevant

        return existing_events[: min(limit, 30)]

    @staticmethod
    def _find_explicit_event_mentions(
        requirements: Any,
        existing_events: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(existing_events, list):
            return []

        requirements_text = str(requirements).lower()
        mentioned = []

        for event in existing_events:
            if not isinstance(event, dict):
                continue

            event_name = str(event.get("event_name", "")).strip()
            if event_name and event_name.lower() in requirements_text:
                mentioned.append(event)

        return mentioned

    def _build_json_schemas(
        self,
        final_table: Any,
        existing_events: Any,
    ) -> dict[str, Any]:
        event_map = self._build_existing_event_map(existing_events)
        result_events = []

        for event in final_table or []:
            if not isinstance(event, dict):
                continue

            event_name = str(event.get("event_name", "")).strip()
            if not event_name:
                continue

            exists = str(event.get("exists", "")).strip().lower() == "да"
            base_schema = self._load_existing_schema(event_map.get(event_name)) if exists else None
            schema = base_schema or {
                "description": str(event.get("description", "")).strip(),
                "properties": {},
                "title": event_name,
                "type": "object",
            }

            if not schema.get("description"):
                schema["description"] = str(event.get("description", "")).strip()

            schema.setdefault("properties", {})
            schema.setdefault("type", "object")
            schema.setdefault("title", event_name)
            schema.setdefault("required", [])

            self._merge_parameters_into_schema(
                schema=schema,
                parameters=event.get("parameters", []),
            )

            ordered_schema = self._order_schema_keys(schema, is_root=True)

            result_events.append(
                {
                    "event_name": event_name,
                    "mode": "update_existing" if exists else "create_new",
                    "suggested_file_name": self._slugify_event_name(event_name) + ".json",
                    "source_file": (event_map.get(event_name) or {}).get("source_file"),
                    "schema": ordered_schema,
                    "json_content": json.dumps(
                        ordered_schema,
                        ensure_ascii=False,
                        indent=2,
                    ),
                }
            )

        return {"events": result_events}

    @staticmethod
    def _build_existing_event_map(existing_events: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(existing_events, list):
            return {}

        event_map = {}
        for event in existing_events:
            if not isinstance(event, dict):
                continue

            event_name = str(event.get("event_name", "")).strip()
            if event_name:
                event_map[event_name] = event

        return event_map

    @staticmethod
    def _load_existing_schema(event: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not event:
            return None

        source_file = event.get("source_file")
        if not source_file or not os.path.exists(source_file):
            return None

        with open(source_file, "r", encoding="utf-8") as file:
            return copy.deepcopy(json.load(file))

    def _merge_parameters_into_schema(
        self,
        schema: dict[str, Any],
        parameters: Any,
    ) -> None:
        tree = self._build_parameter_tree(parameters)
        for parameter_name, node in tree.items():
            schema["properties"][parameter_name] = self._node_to_schema(node)

    @staticmethod
    def _build_parameter_tree(parameters: Any) -> dict[str, dict[str, Any]]:
        tree: dict[str, dict[str, Any]] = {}

        if not isinstance(parameters, list):
            return tree

        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue

            name = str(parameter.get("name", "")).strip()
            if not name:
                continue

            parts = name.split(".")
            current_level = tree
            current_node: dict[str, Any] = {}

            for index, part in enumerate(parts):
                if part not in current_level:
                    current_level[part] = {
                        "name": part,
                        "full_name": ".".join(parts[: index + 1]),
                        "type": "",
                        "description": "",
                        "children": {},
                    }

                current_node = current_level[part]
                current_level = current_node["children"]

            current_node["type"] = str(parameter.get("type", "")).strip()
            current_node["description"] = str(parameter.get("description", "")).strip()
            current_node["possible_values"] = str(parameter.get("possible_values", "")).strip()

        return tree

    def _node_to_schema(self, node: dict[str, Any]) -> dict[str, Any]:
        type_value = node.get("type", "")
        description = node.get("description", "")
        children = node.get("children", {})
        possible_values = node.get("possible_values", "")

        if type_value.startswith("array["):
            schema = {
                "type": "array",
                "description": description,
                "items": self._array_items_schema(type_value, children),
            }
            return self._cleanup_schema(schema)

        if type_value.startswith("ref:"):
            return self._cleanup_schema(
                {
                    "description": description,
                    "$ref": "#/definitions/" + type_value.split("ref:", 1)[1],
                }
            )

        if type_value == "object" or children:
            properties = {
                child_name: self._node_to_schema(child_node)
                for child_name, child_node in children.items()
            }
            schema = {
                "type": "object",
                "description": description,
                "properties": properties,
            }
            return self._cleanup_schema(schema)

        schema = {
            "type": type_value or "string",
            "description": description,
        }

        enum_values = self._parse_possible_values(possible_values, schema["type"])
        if enum_values:
            schema["enum"] = enum_values

        return self._cleanup_schema(schema)

    def _array_items_schema(
        self,
        type_value: str,
        children: dict[str, Any],
    ) -> dict[str, Any]:
        inner_type = type_value[len("array[") : -1].strip()

        if inner_type.startswith("ref:"):
            return {
                "$ref": "#/definitions/" + inner_type.split("ref:", 1)[1],
            }

        if inner_type == "object":
            return self._cleanup_schema(
                {
                    "type": "object",
                    "properties": {
                        child_name: self._node_to_schema(child_node)
                        for child_name, child_node in children.items()
                    },
                }
            )

        if inner_type.startswith("array["):
            return {
                "type": "array",
                "items": self._array_items_schema(inner_type, children),
            }

        return {"type": inner_type}

    @staticmethod
    def _cleanup_schema(schema: dict[str, Any]) -> dict[str, Any]:
        cleaned = {}
        for key, value in schema.items():
            if key == "required" and value == []:
                cleaned[key] = value
                continue

            if value in ("", None, {}, []):
                if key == "description" and value == "":
                    continue
                if key == "items" and value == {}:
                    continue
                continue
            cleaned[key] = value

        return cleaned

    @staticmethod
    def _parse_possible_values(raw_value: str, type_value: str) -> list[Any]:
        if not raw_value:
            return []

        values = [item.strip() for item in raw_value.split(",") if item.strip()]
        if not values:
            return []

        if type_value == "number":
            parsed = []
            for item in values:
                try:
                    parsed.append(int(item) if item.isdigit() else float(item))
                except ValueError:
                    parsed.append(item)
            return parsed

        if type_value == "boolean":
            parsed = []
            for item in values:
                lowered = item.lower()
                if lowered in ("true", "1", "yes"):
                    parsed.append(True)
                elif lowered in ("false", "0", "no"):
                    parsed.append(False)
                else:
                    parsed.append(item)
            return parsed

        return values

    @staticmethod
    def _slugify_event_name(event_name: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", event_name.lower())
        return normalized.strip("_")

    def _order_schema_keys(
        self,
        value: Any,
        is_root: bool = False,
    ) -> Any:
        if isinstance(value, list):
            return [self._order_schema_keys(item) for item in value]

        if not isinstance(value, dict):
            return value

        ordered: dict[str, Any] = {}
        preferred_order = (
            ["description", "properties", "required", "title", "type", "$comment"]
            if is_root
            else ["description", "$ref", "type", "enum", "properties", "items", "required"]
        )

        for key in preferred_order:
            if key in value:
                if key == "properties":
                    ordered[key] = {
                        prop_name: self._order_schema_keys(prop_value)
                        for prop_name, prop_value in value[key].items()
                    }
                else:
                    ordered[key] = self._order_schema_keys(value[key])

        for key, item in value.items():
            if key in ordered:
                continue

            ordered[key] = self._order_schema_keys(item)

        return ordered
