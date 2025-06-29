"""Parameter loading and translation utilities for Stiebel Eltron integration."""

import json
import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
json_path = Path(__file__).resolve().parent / "data" / "parameters.json"


def convert_value(value_str, scale_str):
    if value_str is None or scale_str is None:
        return None
    try:
        value_float = float(value_str)
        scale_int = int(scale_str)
        converted = value_float * (10**scale_int)
        if converted == int(converted):
            return int(converted)
        return converted
    except (ValueError, TypeError):
        return value_str


def load_parameters(language="en", json_file_path=json_path):
    with Path(json_file_path).open("r", encoding="utf-8") as f:
        data = json.load(f)

    all_translations = {
        key: value.get(language, value.get("en", key))
        for key, value in data.get("texts", {}).items()
        if isinstance(value, dict)
    }
    choice_list_map = {}
    for cl in data.get("choice_lists", []):
        translated_choices = {
            str(choice["value"]): all_translations.get(choice["text"], choice["text"])
            for choice in cl["choices"]
        }
        choice_list_map[cl["id"]] = translated_choices

    parameter_to_group_map = {}
    user_friendly_fields = []

    def process_group(group):
        group_id = group.get("id")
        if group_id == "MY_STIEBEL":
            user_friendly_fields.extend(group.get("parameters", []))
        for param_number in group.get("parameters", []):
            parameter_to_group_map[param_number] = group_id
        for subgroup_number in group.get("subgroups", []):
            subgroup_data = next(
                (
                    g
                    for g in data.get("groups", [])
                    if g.get("number") == subgroup_number
                ),
                None,
            )
            if subgroup_data:
                process_group(subgroup_data)

    for group in data.get("groups", []):
        process_group(group)

    parameter_map = {}
    for param in data.get("parameters", []):
        param_number = param.get("number")
        name_key, scale_factor, choicelist_id = (
            param.get("name"),
            param.get("scale"),
            param.get("choicelist_id"),
        )
        translated_name = all_translations.get(name_key, name_key)
        entry = {
            "id": param.get("id"),
            "name": name_key,
            "translated_name": translated_name,
            "display_name": translated_name,
            "data_type": param.get("data_type"),
            "unit": param.get("unit"),
            "scale": scale_factor,
            "access": [p["access"] for p in param.get("access_permissions", [])],
            "choicelist_id": choicelist_id,
            "choices": choice_list_map.get(choicelist_id, {}) if choicelist_id else {},
            "min": convert_value(param.get("min_value"), scale_factor),
            "max": convert_value(param.get("max_value"), scale_factor),
            "group_id": parameter_to_group_map.get(param_number),
        }
        parameter_map[param_number] = entry

    alarm_map = {
        alarm.get("code"): all_translations.get(alarm.get("name"), alarm.get("name"))
        for alarm in data.get("alarms", [])
    }

    return {
        "parameters": parameter_map,
        "alarms": alarm_map,
        "user_fields": user_friendly_fields,
        "all_fields": list(parameter_map.keys()),
    }
