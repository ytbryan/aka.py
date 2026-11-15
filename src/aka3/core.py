"""Configuration and conservative, non-executing shell-file editing."""
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

import yaml


class AkaError(Exception):
    """An actionable user error."""


NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
GROUP = re.compile(r"^[A-Za-z0-9_.-]+$")
RESERVED = set("if then else elif fi case esac for select while until do done in function time coproc ! { } aka aka3".split())


def validate(entry):
    if not NAME.fullmatch(entry.name) or entry.name in RESERVED:
        raise AkaError("Use a shell identifier that is not reserved for the name.")
    if not entry.command.strip() or any(c in entry.command for c in "\r\n\0"):
        raise AkaError("Commands must be nonempty and on one line.")
    if not GROUP.fullmatch(entry.group):
        raise AkaError("Groups may contain letters, digits, underscores, dots, and hyphens.")
    if entry.kind not in ("alias", "function"):
        raise AkaError("Unknown entry kind.")
    if entry.kind == "function" and any(c in entry.command for c in "{}"):
        raise AkaError("Function bodies containing braces require manual editing.")
    return entry


@dataclass(frozen=True)
class Entry:
    name: str
    command: str
    group: str = "default"
    kind: str = "alias"

    def render(self):
        validate(self)
        if self.kind == "function":
            body = self.command.rstrip()
            if not body.endswith((";", "&")):
                body += ";"
            return f"function {self.name}() {{ {body} }} # => {self.group}"
        # Always quote, even simple words, so export/import is unambiguous.
        quoted = "'" + self.command.replace("'", "'\"'\"'") + "'"
        return f"alias {self.name}={quoted} # => {self.group}"

    def display(self):
        verb = "func" if self.kind == "function" else "g"
        return f"aka {verb} {shlex.quote(self.name + '=' + self.command)} -g {shlex.quote(self.group)}"


def parse_line(line):
    """Read single-line definitions without running shell code."""
    text = line.strip()
    match = re.fullmatch(r"(?:function\s+)([A-Za-z_]\w*)\s*\(\)\s*\{ (.*) \}\s*(?:# => ([\w.-]+))?", text)
    if match:
        body = match[2].rstrip()
        if body.endswith(";"):
            body = body[:-1]
        return Entry(match[1], body, match[3] or "default", "function")
    if not text.startswith("alias "):
        return None
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    if len(tokens) != 2 or "=" not in tokens[1]:
        return None
    name, command = tokens[1].split("=", 1)
    if not NAME.fullmatch(name):
        return None
    # A marker counts only if it is outside the alias token's shell quotes.
    quote = None
    escaped = False
    comment = ""
    for i, char in enumerate(text):
        if escaped:
            escaped = False
        elif char == "\\" and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "#" and (i == 0 or text[i - 1].isspace()):
            comment = text[i:]
            break
    group = re.fullmatch(r"# => ([\w.-]+)\s*", comment)
    return Entry(name, command, group[1] if group else "default")


def records(text):
    result = []
    prefix = ""
    heredocs = []
    depth = 0
    for index, line in enumerate(text.splitlines(keepends=True)):
        if heredocs:
            delimiter, tabs = heredocs[0]
            candidate = line.rstrip("\r\n")
            if (candidate.lstrip("\t") if tabs else candidate) == delimiter:
                heredocs.pop(0)
            continue
        try:
            shlex.split(prefix, comments=True)
            inside_quote = False
        except ValueError:
            inside_quote = True
        entry = parse_line(line) if not inside_quote and depth == 0 else None
        if entry:
            result.append((index, entry))
        elif not inside_quote:
            # Conservatively exclude definitions nested in functions/blocks.
            lexer = shlex.shlex(line, posix=True, punctuation_chars="{};<>")
            lexer.whitespace_split = True
            try:
                tokens = list(lexer)
            except ValueError:
                tokens = []
            for position, token in enumerate(tokens):
                if token in ("<<", "<<-") and position + 1 < len(tokens):
                    heredocs.append((tokens[position + 1], token == "<<-"))
            depth = max(0, depth + tokens.count("{") - tokens.count("}"))
        prefix += line
    return result


def check_shell(text, path):
    shell = "zsh" if Path(path).name == ".zshrc" else "bash"
    executable = shutil.which(shell)
    if not executable:
        raise AkaError(f"{shell} is required to check shell syntax before writing.")
    checked = subprocess.run([executable, "-n"], input=text, text=True, capture_output=True)
    if checked.returncode:
        raise AkaError(f"Shell syntax check failed: {checked.stderr.strip()}")


def atomic_write(path, text, backup=True):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    if exists and backup:
        shutil.copy2(path, str(path) + ".aka3.bak")
    fd, temporary = tempfile.mkstemp(prefix=".aka3-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777 if exists else 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(path):
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".aka3.lock", "a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def read_text(path):
    with Path(path).expanduser().open(encoding="utf-8", newline="") as stream:
        return stream.read()


class Manager:
    def __init__(self):
        self.home = Path.home()
        self.directory = Path(os.environ.get("AKA3_HOME", self.home / ".aka" )).expanduser()
        self.config_path = self.directory / ".config"

    def config(self):
        if not self.config_path.exists():
            raise AkaError("Run `aka setup` first.")
        data = yaml.safe_load(read_text(self.config_path))
        if not isinstance(data, dict):
            raise AkaError("The config must be a YAML mapping; run `aka setup --reset`.")
        for key in ("dotfile", "history", "profile"):
            if not isinstance(data.get(key), str) or not data[key]:
                raise AkaError(f"Config {key} must be a nonempty path.")
        for key in ("list", "usage"):
            if type(data.get(key)) is not int or data[key] < 0:
                raise AkaError(f"Config {key} must be a nonnegative integer.")
        return data

    def save_config(self, data):
        atomic_write(self.config_path, yaml.safe_dump(data, sort_keys=False))

    def setup(self, dotfile=None, reset=False):
        if self.config_path.exists() and not reset:
            raise AkaError("Already configured; use `aka setup --reset` to configure again.")
        if dotfile is None:
            filename = ".zshrc" if Path(os.environ.get("SHELL", "/bin/bash")).name == "zsh" else ".bashrc"
            dotfile = self.home / filename
        path = Path(dotfile).expanduser().resolve()
        # Reset preserves aliases and old startup integration; the wrapper reads current config.
        data = dict(dotfile=str(path), history=str(self.home / (".zsh_history" if path.name == ".zshrc" else ".bash_history")),
                    home=str(self.directory.resolve()), install=str(self.home / ".local/bin"),
                    profile=str(path), list=20, usage=20, remote="")
        self.directory.mkdir(parents=True, exist_ok=True)
        atomic_write(self.directory / "autosource", SHELL_WRAPPER)
        with locked(path):
            content = read_text(path) if path.exists() else ""
            source = f"source {shlex.quote(str((self.directory / 'autosource').resolve()))} # aka3"
            if source not in content.splitlines():
                updated = content + ("\n" if content and not content.endswith("\n") else "") + source + "\n"
                check_shell(updated, path)
                atomic_write(path, updated)
        self.save_config(data)
        return path

    def path(self):
        return Path(self.config()["dotfile"]).expanduser()

    def entries(self, path=None):
        return [entry for _, entry in records(read_text(path or self.path()))]

    def add_many(self, entries):
        entries = [validate(e) for e in entries]
        path = self.path()
        with locked(path):
            content = read_text(path)
            names = {e.name for _, e in records(content)}
            for entry in entries:
                if entry.name in names:
                    raise AkaError(f"{entry.name} already exists; use `aka edit`.")
                names.add(entry.name)
            rendered = "\n".join(e.render() for e in entries)
            if rendered:
                updated = content + ("\n" if content and not content.endswith("\n") else "") + rendered + "\n"
                check_shell(updated, path)
                atomic_write(path, updated)

    def change(self, names, replacement=None):
        path = self.path()
        with locked(path):
            content = read_text(path)
            found = records(content)
            for name in names:
                if sum(e.name == name for _, e in found) != 1:
                    raise AkaError(f"Expected exactly one definition of {name}; inspect your dotfile.")
            if replacement:
                validate(replacement)
                if any(e.name == replacement.name and e.name not in names for _, e in found):
                    raise AkaError(f"{replacement.name} already exists.")
            lines = content.splitlines(keepends=True)
            for index, entry in reversed(found):
                if entry.name in names:
                    if replacement:
                        newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
                        lines[index] = replacement.render() + newline
                    else:
                        del lines[index]
            updated = "".join(lines)
            check_shell(updated, path)
            atomic_write(path, updated)

    def history(self):
        lines = read_text(self.config()["history"]).splitlines()
        result = []
        for line in lines:
            if re.fullmatch(r"#\d+", line):
                continue
            line = re.sub(r"^: \d+:\d+;", "", line)
            if line.strip():
                result.append(line)
        return result

    def usage(self, count, least=False):
        names = []
        for line in self.history():
            try:
                tokens = shlex.split(line)
            except ValueError:
                continue
            if tokens:
                names.append(tokens[0])
        counts = Counter(names)
        return sorted(counts.items(), key=lambda item: (item[1] if least else -item[1], item[0]))[:count], len(names)

    def notify_shell(self, removed=(), no=False, nounalias=False):
        if no:
            return
        script = ""
        if not nounalias:
            for entry in removed:
                command = "unset -f" if entry.kind == "function" else "unalias"
                script += f"{command} {shlex.quote(entry.name)} 2>/dev/null || :\n"
        script += f"source {shlex.quote(str(self.path().resolve()))}\n"
        destination = os.environ.get("AKA3_SHELL_UPDATES")
        if destination:
            with open(destination, "a", encoding="utf-8") as stream:
                stream.write(script)
        else:
            print(f"Reload with: source {shlex.quote(str(self.path()))}", file=sys.stderr)


SHELL_WRAPPER = '''# Generated by aka3. Source from Bash or Zsh.
aka() {
    local _aka3_updates _aka3_status
    _aka3_updates=$(mktemp) || return 1
    AKA3_SHELL_UPDATES="$_aka3_updates" command aka "$@"
    _aka3_status=$?
    if [ "$_aka3_status" -eq 0 ] && [ -s "$_aka3_updates" ]; then
        source "$_aka3_updates"
    fi
    command rm -f -- "$_aka3_updates"
    return "$_aka3_status"
}
aka3() { aka "$@"; }
'''
