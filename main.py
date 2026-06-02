import io
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from agent_logic import TrackingAgent
from processor import collect_repositories_data


TABLE_COLUMNS = [
    "Существует",
    "Название события",
    "Описание события",
    "Параметр",
    "Тип",
    "Описание параметра",
    "Возможные значения",
]

CSV_FORMAT_EXAMPLE = """Существует,Название события,Описание события,Параметр,Тип,Описание параметра,Возможные значения
Нет,Checkout Started,Пользователь начал оформление заказа,order_id,string,Идентификатор заказа,
,,,payment_method,string,Выбранный способ оплаты,"card,cash,sbp"
Да,Cart Viewed,Пользователь открыл корзину,,,
"""

def merge_repositories_data(repositories_data: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {
        "events": [],
        "readme_text": "",
        "array_examples": [],
        "repo_path": "",
        "path_exists": False,
    }

    for data in repositories_data.values():
        merged["events"].extend(data.get("events", []))
        merged["array_examples"].extend(data.get("array_examples", []))
        readme = data.get("readme_text", "")
        if readme:
            merged["readme_text"] += readme + "\n\n"
        if data.get("path_exists"):
            merged["path_exists"] = True
        repo_path = data.get("repo_path", "")
        if repo_path:
            merged["repo_path"] += (", " if merged["repo_path"] else "") + repo_path

    merged["readme_text"] = merged["readme_text"].strip()
    return merged


@st.cache_resource
def get_tracking_agent() -> TrackingAgent:
    return TrackingAgent()


@st.cache_data
def get_repositories_data() -> Dict[str, Dict[str, Any]]:
    return collect_repositories_data()


def ensure_table_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for column in TABLE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""

    return frame[TABLE_COLUMNS]


def build_display_rows(events: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    display_rows: List[Dict[str, str]] = []

    for event in events:
        parameters = event.get("parameters") or [{}]
        if not isinstance(parameters, list):
            parameters = [{}]

        event_exists = event.get("exists", event.get("existing", ""))
        event_name = event.get("event_name", event.get("name", ""))
        event_description = event.get("description", "")

        for index, parameter in enumerate(parameters):
            parameter = parameter or {}
            possible_values = parameter.get("possible_values", parameter.get("enum_values", ""))
            if isinstance(possible_values, list):
                possible_values = ",".join(str(value) for value in possible_values)

            display_rows.append(
                {
                    "Существует": str(event_exists) if index == 0 else "",
                    "Название события": str(event_name) if index == 0 else "",
                    "Описание события": str(event_description) if index == 0 else "",
                    "Параметр": str(parameter.get("name", parameter.get("parameter", ""))),
                    "Тип": str(parameter.get("type", "")),
                    "Описание параметра": str(
                        parameter.get("description", parameter.get("parameter_description", ""))
                    ),
                    "Возможные значения": str(possible_values),
                }
            )

    return display_rows


def normalize_suggestions_payload(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    if not isinstance(payload, dict):
        return []

    for key in ("table", "rows", "result", "events", "suggestions", "final_table"):
        value = payload.get(key)
        if isinstance(value, list):
            if value and isinstance(value[0], dict) and "Параметр" in value[0]:
                return [{column: str(row.get(column, "")) for column in TABLE_COLUMNS} for row in value]
            return build_display_rows(value)

    return []


def dataframe_from_rows(rows: List[Dict[str, str]]) -> pd.DataFrame:
    if not rows:
        return ensure_table_columns(pd.DataFrame(columns=TABLE_COLUMNS))

    return ensure_table_columns(pd.DataFrame(rows))


def empty_table_row() -> Dict[str, str]:
    return {column: "" for column in TABLE_COLUMNS}


def append_empty_row(frame: pd.DataFrame) -> pd.DataFrame:
    return ensure_table_columns(pd.concat([frame, pd.DataFrame([empty_table_row()])], ignore_index=True))


def decode_uploaded_csv(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError("Не удалось прочитать CSV. Сохраните файл в UTF-8 или CP1251.")


def dataframe_from_uploaded_csv(file_bytes: bytes) -> pd.DataFrame:
    decoded_content = decode_uploaded_csv(file_bytes)
    frame = pd.read_csv(
        io.StringIO(decoded_content),
        sep=None,
        engine="python",
        dtype=str,
        keep_default_na=False,
    )
    frame.columns = [str(column).strip() for column in frame.columns]

    if frame.columns.tolist() != TABLE_COLUMNS:
        expected_columns = ", ".join(TABLE_COLUMNS)
        raise ValueError(
            "Неверный формат CSV. "
            f"Ожидаются колонки строго в таком порядке: {expected_columns}"
        )

    return ensure_table_columns(frame.fillna(""))


def table_to_event_blocks(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    current_event: Dict[str, Any] = {}

    for row in frame.fillna("").to_dict(orient="records"):
        event_name = str(row.get("Название события", "")).strip()
        event_exists = str(row.get("Существует", "")).strip()
        event_description = str(row.get("Описание события", "")).strip()
        parameter_name = str(row.get("Параметр", "")).strip()
        parameter_type = str(row.get("Тип", "")).strip()
        parameter_description = str(row.get("Описание параметра", "")).strip()
        possible_values = str(row.get("Возможные значения", "")).strip()

        if event_name or event_exists or event_description:
            current_event = {
                "exists": event_exists,
                "event_name": event_name,
                "description": event_description,
                "parameters": [],
            }
            events.append(current_event)

        if not current_event:
            continue

        if any([parameter_name, parameter_type, parameter_description, possible_values]):
            current_event["parameters"].append(
                {
                    "name": parameter_name,
                    "type": parameter_type,
                    "description": parameter_description,
                    "possible_values": possible_values,
                }
            )

    return events


def main() -> None:
    st.set_page_config(page_title="AI agent for event-schema", layout="wide")
    st.markdown(
        """
        <style>
        .stAppDeployButton, [data-testid="stToolbar"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("AI agent for event-schema")

    if "analysis_table" not in st.session_state:
        st.session_state.analysis_table = dataframe_from_rows([])
    if "json_result" not in st.session_state:
        st.session_state.json_result = None

    repositories_data = get_repositories_data()
    agent = get_tracking_agent()

    repo_labels = {
        "WEB_REPO_PATH": "web-rudderstack",
        "MOBILE_REPO_PATH": "mobile",
    }
    repo_options = list(repo_labels.values())
    selected_repo = st.radio(
        "Репозиторий",
        options=repo_options,
        horizontal=True,
        key="repo_selector",
    )

    env_key = {v: k for k, v in repo_labels.items()}[selected_repo]
    filtered_repos = {env_key: repositories_data[env_key]} if env_key in repositories_data else {}

    repository_data = merge_repositories_data(filtered_repos)

    if repository_data.get("repo_path"):
        st.caption(f"Схемы: {repository_data['repo_path']}")

    requirements = st.text_area(
        "требования",
        height=220,
        placeholder="Вставьте сюда описание фичи, бизнес-логики и требований к трекингу...",
    )

    if st.button("Анализировать", type="primary"):
        if not requirements.strip():
            st.warning("Добавьте текст требований перед анализом.")
        else:
            try:
                with st.spinner("Анализирую требования и сравниваю с текущими событиями..."):
                    suggestions = agent.get_suggestions(
                        requirements=requirements,
                        existing_events=repository_data.get("events", []),
                    )
                    rows = normalize_suggestions_payload(suggestions)
                    st.session_state.analysis_table = dataframe_from_rows(rows)
                    st.session_state.json_result = None
                    st.session_state.suggestions_raw = suggestions

                if not rows:
                    st.info("Модель вернула JSON, но я не нашел в нем табличных строк. Проверьте структуру ответа.")
            except Exception as error:
                st.error(f"Не удалось выполнить анализ: {error}")

    edited_table = st.data_editor(
        st.session_state.analysis_table,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        key="tracking_table_editor",
    )

    st.caption(
        "Формат CSV для загрузки: первая строка должна содержать колонки "
        "`Существует,Название события,Описание события,Параметр,Тип,Описание параметра,Возможные значения` "
        "строго в таком порядке. Пустые значения в колонках события у следующих строк означают, "
        "что параметр относится к предыдущему событию. "
        "Колонка `Возможные значения` используется для построения `enum`: "
        "указывайте значения через запятую, например `order,profile`, "
        "или оставляйте пустой, если `enum` не нужен."
    )
    st.caption(
        "Удаление строк: отметьте строки через чекбоксы и нажмите **Backspace** "
        "или **Delete**, либо используйте кнопку с корзиной в таблице."
    )
    with st.expander("Показать пример CSV"):
        st.code(CSV_FORMAT_EXAMPLE, language="csv")

    uploaded_csv = st.file_uploader("Загрузить CSV", type=["csv"], key="tracking_csv_uploader")
    import_column, add_column = st.columns([1.2, 1])

    with import_column:
        if st.button("Импортировать CSV", use_container_width=True):
            if uploaded_csv is None:
                st.warning("Сначала выберите CSV-файл.")
            else:
                try:
                    st.session_state.analysis_table = dataframe_from_uploaded_csv(uploaded_csv.getvalue())
                    st.session_state.json_result = None
                    st.rerun()
                except Exception as error:
                    st.error(f"Не удалось загрузить CSV: {error}")

    st.markdown("""
<script>
if (!window.__es_backspace_handler) {
    window.__es_backspace_handler = true;
    document.addEventListener('keydown', function(e) {
        if (e.key !== 'Backspace' && e.key !== 'Delete') return;
        if (e.target.closest('input, textarea, [contenteditable]')) return;
        if (document.querySelector('.ag-cell-editing')) return;

        var editor = document.querySelector('[data-testid="stDataEditor"]');
        if (!editor) return;
        if (!editor.querySelector('.ag-row-selected')) return;

        var deleteIcon = editor.querySelector('[data-testid="DeleteIcon"]');
        if (!deleteIcon) return;

        var btn = deleteIcon.closest('button');
        if (btn && !btn.disabled && btn.offsetParent !== null) {
            e.preventDefault();
            e.stopPropagation();
            btn.click();
        }
    });
}
</script>
""", unsafe_allow_html=True)

    if st.button("Сформировать JSON"):
        final_table = table_to_event_blocks(edited_table)
        if not final_table:
            st.warning("Таблица пуста. Добавьте хотя бы одно событие или выполните анализ.")
        else:
            try:
                with st.spinner("Формирую JSON по правилам README..."):
                    st.session_state.json_result = agent.generate_json(
                        final_table=final_table,
                        readme_content=repository_data.get("readme_text", ""),
                        array_examples=repository_data.get("array_examples", []),
                        existing_events=repository_data.get("events", []),
                    )
            except Exception as error:
                st.error(f"Не удалось сформировать JSON: {error}")

    if st.session_state.json_result is not None:
        st.subheader("Итоговый JSON")
        generated_events = st.session_state.json_result.get("events", [])

        if not generated_events:
            st.json(st.session_state.json_result)
        else:
            for event_payload in generated_events:
                event_name = event_payload.get("event_name", "Event")
                mode = event_payload.get("mode", "")
                source_file = event_payload.get("source_file") or event_payload.get("suggested_file_name", "")

                st.markdown(f"**{event_name}**")
                st.caption(f"{mode} • {source_file}")
                st.code(event_payload.get("json_content", ""), language="json")


if __name__ == "__main__":
    main()
