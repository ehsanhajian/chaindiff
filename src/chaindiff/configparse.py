"""Read a node config without changing it.

Operators keep CLI flags, TOML, JSON, or YAML. Each parser returns the keys
they set. Dashes and underscores match dots, so --http.port and http_port
are the same key.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from chaindiff.models import Setting

_FLAG = re.compile(
    r"^(?P<dashes>--?)(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:=(?P<value>.*))?$"
)
_FLAG_HINT = re.compile(r"(?m)(?:^|[\s\"'=])--?[A-Za-z][A-Za-z0-9._-]+")


def normalize_flag(name: str) -> str:
    text = name.strip()
    if text.startswith("--"):
        text = text[2:]
    elif text.startswith("-"):
        text = text[1:]
    text = text.replace("_", ".").replace("-", ".").lower()
    return ".".join(part for part in text.split(".") if part)


def parse_config(path: Path, fmt: str | None = None) -> tuple[str, list[Setting]]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError(f"{path} is empty")
    chosen = fmt or _detect(path, text)
    settings = _PARSERS[chosen](text)
    if not settings:
        raise ValueError(f"{path} has no settings")
    return chosen, _dedupe(settings)


def parse_cli(text: str) -> list[Setting]:
    settings: list[Setting] = []
    for lineno, line in _logical_lines(text):
        try:
            tokens = _tokens(line)
        except ValueError as exc:
            raise ValueError(f"line {lineno}: {exc}") from exc
        index = 0
        while index < len(tokens):
            matched = _FLAG.match(tokens[index])
            if matched is None:
                index += 1
                continue
            name = matched.group("name")
            if matched.group("dashes") == "-" and len(name) < 2:
                index += 1
                continue
            inline = matched.group("value")
            if inline is not None:
                value = inline
                index += 1
            elif index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
                value = tokens[index + 1]
                index += 2
            else:
                value = ""
                index += 1
            settings.append(Setting(name, value, lineno))
    return settings


def parse_json(text: str) -> list[Setting]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON config: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON config must be an object")
    settings: list[Setting] = []
    _flatten(payload, "", None, settings)
    return settings


def parse_toml(text: str) -> list[Setting]:
    try:
        payload = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"TOML config: {exc}") from exc
    settings: list[Setting] = []
    _flatten(payload, "", None, settings)
    return settings


def parse_yaml(text: str) -> list[Setting]:
    root = _YamlBox({}, None)
    stack: list[tuple[int, _YamlBox]] = [(-1, root)]
    for lineno, raw in enumerate(text.splitlines(), start=1):
        indent_text = raw[: len(raw) - len(raw.lstrip(" \t"))]
        if "\t" in indent_text:
            raise ValueError(f"line {lineno}: YAML config indentation must use spaces")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(indent_text)
        if stripped.startswith("- "):
            _yaml_list_item(stack, indent, _strip_comment(stripped[2:]).strip(), lineno)
            continue
        if stripped.startswith("-"):
            raise ValueError(f"line {lineno}: YAML list items need a space after '-'")
        key, value = _yaml_key(stripped, lineno)
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if not isinstance(parent.data, dict):
            raise ValueError(f"line {lineno}: nested keys under a list are not supported")
        if value == "":
            child = _YamlBox({}, lineno)
            parent.data[key] = child
            stack.append((indent, child))
            continue
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            raise ValueError(f"line {lineno}: multiline YAML values are not supported")
        parent.data[key] = (_unquote(value), lineno)
    if not isinstance(root.data, dict):
        raise ValueError("YAML config must be a mapping")
    settings: list[Setting] = []
    _flatten_yaml(root, "", settings)
    return settings


class _YamlBox:
    def __init__(self, data: dict | list, line: int | None) -> None:
        self.data = data
        self.line = line


def _yaml_key(stripped: str, lineno: int) -> tuple[str, str]:
    text = _strip_comment(stripped).strip()
    if text.startswith(("&", "*", "<<")):
        raise ValueError(f"line {lineno}: YAML aliases are not supported")
    if ":" not in text:
        raise ValueError(f"line {lineno}: expected 'key: value'")
    key, _, value = text.partition(":")
    key = _unquote(key.strip())
    if not key:
        raise ValueError(f"line {lineno}: missing a key")
    return key, value.strip()


def _yaml_list_item(stack: list[tuple[int, _YamlBox]], indent: int, item: str, lineno: int) -> None:
    while len(stack) > 1 and stack[-1][0] >= indent:
        stack.pop()
    current = stack[-1][1]
    if isinstance(current.data, dict):
        if current.data:
            raise ValueError(f"line {lineno}: a list item cannot follow keys at the same level")
        if stack[-1][0] < 0:
            raise ValueError("YAML config must be a mapping")
        current.data = []
    if not isinstance(current.data, list):
        raise ValueError(f"line {lineno}: a list item is not under a key")
    if item.startswith("-"):
        raise ValueError(f"line {lineno}: nested YAML lists are not supported")
    current.data.append((_unquote(item), lineno))


def _flatten_yaml(node: _YamlBox | tuple, prefix: str, settings: list[Setting]) -> None:
    if isinstance(node, tuple):
        settings.append(Setting(prefix, node[0], node[1]))
        return
    data = node.data
    if isinstance(data, dict):
        if not data and prefix:
            settings.append(Setting(prefix, "", node.line))
            return
        for key, item in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            _flatten_yaml(item, path, settings)
        return
    if isinstance(data, list):
        if not data:
            settings.append(Setting(prefix, "", node.line))
            return
        parts: list[str] = []
        line = node.line
        for item in data:
            if not isinstance(item, tuple):
                raise ValueError(f"{prefix or 'YAML config'} has a nested value this parser does not read")
            parts.append(item[0])
            if line is None:
                line = item[1]
        settings.append(Setting(prefix, ", ".join(parts), line))
        return
    raise ValueError(f"{prefix or 'YAML config'} has a value this parser does not read")


def _flatten(value: object, prefix: str, line: int | None, settings: list[Setting]) -> None:
    if isinstance(value, dict):
        if not value and prefix:
            settings.append(Setting(prefix, "", line))
            return
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            _flatten(item, path, line, settings)
        return
    settings.append(Setting(prefix, _render(value), line))


def _render(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, list):
        return ", ".join(_render(item) for item in value)
    if isinstance(value, dict):
        raise ValueError("nested config value could not be flattened")
    return str(value)


def _detect(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".toml":
        return "toml"
    if suffix in (".yaml", ".yml"):
        return "yaml"
    if text.lstrip().startswith("{"):
        return "json"
    if _FLAG_HINT.search(text):
        return "cli"
    toml_ok = False
    try:
        toml_ok = bool(parse_toml(text))
    except ValueError:
        toml_ok = False
    if toml_ok:
        return "toml"
    try:
        if parse_yaml(text):
            return "yaml"
    except ValueError:
        pass
    raise ValueError(f"{path} could not be read as CLI flags, TOML, JSON, or YAML")


def _dedupe(settings: list[Setting]) -> list[Setting]:
    seen: set[str] = set()
    unique: list[Setting] = []
    for setting in settings:
        key = normalize_flag(setting.flag)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(setting)
    return unique


def _logical_lines(text: str) -> list[tuple[int, str]]:
    logical: list[tuple[int, str]] = []
    buffer = ""
    start = 1
    continued = False
    for index, line in enumerate(text.splitlines(), start=1):
        if not continued:
            start = index
            buffer = ""
        piece = line.rstrip()
        if piece.endswith("\\"):
            buffer += piece[:-1] + " "
            continued = True
            continue
        buffer += piece
        logical.append((start, _strip_comment(buffer)))
        continued = False
        buffer = ""
    if continued and buffer:
        logical.append((start, _strip_comment(buffer)))
    return logical


def _strip_comment(line: str) -> str:
    out: list[str] = []
    quote = ""
    for char in line:
        if quote:
            out.append(char)
            if char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
            out.append(char)
            continue
        if char == "#":
            break
        out.append(char)
    return "".join(out)


def _tokens(line: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    quote = ""
    for char in line:
        if quote:
            if char == quote:
                quote = ""
            else:
                current.append(char)
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char.isspace():
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)
    if quote:
        raise ValueError("a quote is missing its closer")
    if current:
        tokens.append("".join(current))
    return tokens


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


_PARSERS = {
    "cli": parse_cli,
    "json": parse_json,
    "toml": parse_toml,
    "yaml": parse_yaml,
}
