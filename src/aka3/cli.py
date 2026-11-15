"""The aka command line interface."""
import argparse
from dataclasses import replace
import os
from pathlib import Path
import shlex
import sys
from urllib.parse import unquote, urlparse
from urllib.request import urlopen
import yaml

from . import __version__
from .core import (AkaError, Entry, Manager, atomic_write, check_shell, locked, parse_line,
                   read_text, validate)


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def parser():
    root = argparse.ArgumentParser(prog="aka", description="Manage permanent Bash and Zsh shortcuts.")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="action")
    setup = commands.add_parser("setup", help="configure paths and a shell wrapper")
    setup.add_argument("--reset", action="store_true")
    setup.add_argument("--dotfile")
    for name, aliases in (("generate", ["g"]), ("function", ["func"])):
        command = commands.add_parser(name, aliases=aliases, help="create a shortcut")
        command.add_argument("definition", help="NAME=COMMAND, or NAME with --last")
        command.add_argument("-g", "--group", default="default")
        command.add_argument("-l", "--last", action="store_true")
        command.add_argument("-e", "--empty", action="store_true", help="suppress output")
        command.add_argument("-n", "--no", "--noreload", action="store_true")
    destroy = commands.add_parser("destroy", aliases=["d"], help="remove shortcuts")
    destroy.add_argument("names", nargs="+")
    destroy.add_argument("-n", "--no", "--noreload", action="store_true")
    destroy.add_argument("-u", "--nounalias", action="store_true")
    destroy.add_argument("--force", action="store_true", help="legacy compatibility option")
    edit = commands.add_parser("edit", aliases=["e"], help="edit command, name, or group")
    edit.add_argument("definition")
    edit.add_argument("--name", action="store_true")
    edit.add_argument("-g", "--group")
    edit.add_argument("--force", action="store_true", help="skip interactive confirmation")
    edit.add_argument("-n", "--no", "--noreload", action="store_true")
    find = commands.add_parser("find", aliases=["f"], help="find exact shortcut names")
    find.add_argument("names", nargs="*")
    find.add_argument("-g", "--group")
    find.add_argument("--force", action="store_true", help="legacy compatibility option")
    listing = commands.add_parser("list", aliases=["l"], help="list recent shortcuts")
    listing.add_argument("count", nargs="?", type=nonnegative)
    listing.add_argument("--number", action="store_true")
    listing.add_argument("-g", "--group", action="store_true", help="show group names")
    listing.add_argument("-n", "--no", action="store_true", help="legacy compatibility; list never reloads")
    listing.add_argument("--force", action="store_true", help="legacy compatibility option")
    usage = commands.add_parser("usage", aliases=["u"], help="count commands in saved shell history")
    usage.add_argument("count", nargs="?", type=nonnegative)
    usage.add_argument("--least", action="store_true")
    init = commands.add_parser("init", help="inspect or update configuration")
    for key in ("dotfile", "history", "install", "profile", "remote", "home"):
        init.add_argument("--" + key)
    for key in ("list", "usage"):
        init.add_argument("--" + key, type=nonnegative)
    shell = init.add_mutually_exclusive_group()
    for key in ("bashrc", "zshrc", "bash"):
        shell.add_argument("--" + key, action="store_true")
    init.add_argument("--config", action="store_true")
    proj = commands.add_parser("proj", aliases=["p"], help="list, export, or import project shortcuts")
    proj.add_argument("group_name", nargs="?")
    operation = proj.add_mutually_exclusive_group()
    operation.add_argument("-l", "--load", nargs="?", const="load", help="legacy export; optional output stem")
    operation.add_argument("-s", "--save", nargs="?", const="proj.aka", help="legacy import; optional input file")
    proj.add_argument("-g", "--group", action="store_true", help="list project groups")
    proj.add_argument("-f", "--force", action="store_true")
    proj.add_argument("-n", "--no", action="store_true")
    export = commands.add_parser("export", help="export a group (or all shortcuts)")
    export.add_argument("group_name", nargs="?")
    export.add_argument("-o", "--output", default="proj.aka")
    export.add_argument("-f", "--force", action="store_true")
    imp = commands.add_parser("import", help="import project definitions without executing them")
    imp.add_argument("path", nargs="?", default="proj.aka")
    imp.add_argument("-n", "--no", action="store_true")
    download = commands.add_parser("download", aliases=["dl"], help="download an HTTP(S) file without executing it")
    download.add_argument("url")
    download.add_argument("-o", "--output")
    download.add_argument("-f", "--force", action="store_true")
    for name, aliases, help_text in (
        ("clean", ["c"], "remove blank top-level dotfile lines"),
        ("config", [], "show configuration"), ("groups", [], "list groups"),
        ("where", [], "print dotfile path"), ("version", ["v"], "print version")):
        commands.add_parser(name, aliases=aliases, help=help_text)
    help_command = commands.add_parser("help", aliases=["h"], help="show command help")
    help_command.add_argument("command", nargs="?")
    return root


ALIASES = dict(g="generate", func="function", d="destroy", e="edit", f="find", l="list",
               u="usage", p="proj", dl="download", c="clean", v="version", h="help")


def definition(text, group, kind):
    if "=" not in text:
        raise AkaError("Expected NAME=COMMAND. Quote the whole definition if it contains spaces.")
    name, command = text.split("=", 1)
    command = command.replace("#{pwd}", shlex.quote(str(Path.cwd())))
    return validate(Entry(name, command, group, kind))


def export_project(manager, group, output, force=False):
    entries = [e for e in manager.entries() if group is None or e.group == group]
    if group is not None and not entries:
        raise AkaError(f"No shortcuts found in group {group}.")
    path = Path(output).expanduser()
    with locked(path):
        if path.exists() and not force:
            raise AkaError(f"{path} exists; use --force to overwrite.")
        atomic_write(path, "# Generated with aka3; shell definitions, not a script to run.\n\n" +
                     "".join(e.render() + "\n" for e in entries))
    print(f"Exported {len(entries)} shortcuts to {path}")


def project_entries(path):
    entries = []
    for number, line in enumerate(read_text(path).splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        entry = parse_line(line)
        if entry is None:
            raise AkaError(f"{path}:{number}: expected a single-line alias or function definition.")
        entries.append(validate(entry))
    return entries


def download_file(args):
    parsed = urlparse(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise AkaError("Download requires an HTTP or HTTPS URL.")
    filename = Path(unquote(parsed.path)).name
    if not filename or filename in (".", ".."):
        raise AkaError("Specify an output filename with --output.")
    output = Path(args.output or filename)
    # No shell interpolation; downloaded content is never sourced by this command.
    with urlopen(args.url, timeout=30) as response:
        if urlparse(response.geturl()).scheme not in ("http", "https"):
            raise AkaError("Download redirected to an unsupported protocol.")
        content = response.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise AkaError("Download exceeds the 10 MiB limit.")
    with output.open("wb" if args.force else "xb") as stream:
        stream.write(content)
    print(f"Downloaded {output}")


def run(args, root):
    action = ALIASES.get(args.action, args.action) or "list"
    if action == "help":
        if args.command:
            root.parse_args([args.command, "--help"])
        else:
            root.print_help()
        return
    if action == "version":
        print(__version__)
        return
    if action == "download":
        download_file(args)
        return
    manager = Manager()
    if action == "setup":
        path = manager.setup(args.dotfile, args.reset)
        print(f"Configured {path}. Run: source {shlex.quote(str(path))}")
    elif action in ("config", "where", "init"):
        data = manager.config()
        if action == "init":
            original = dict(data)
            for flag, filename in (("bashrc", ".bashrc"), ("zshrc", ".zshrc"), ("bash", ".bash_profile")):
                if getattr(args, flag):
                    data.update(dotfile=str(manager.home / filename), profile=str(manager.home / filename),
                                history=str(manager.home / (".zsh_history" if flag == "zshrc" else ".bash_history")))
            for key in data:
                if getattr(args, key, None) is not None and key != "config":
                    data[key] = getattr(args, key)
            if data != original:
                manager.save_config(data)
        if action == "where":
            print(data["dotfile"])
        else:
            for key, value in data.items():
                print(f"{key} -> {value}")
    elif action in ("generate", "function"):
        text = args.definition
        if args.last:
            history = manager.history()
            if not history:
                raise AkaError("Saved history is empty; flush your shell history first.")
            if "=" in text:
                raise AkaError("With --last, provide only a shortcut name.")
            text += "=" + history[-1]
        entry = definition(text, args.group, "function" if action == "function" else "alias")
        manager.add_many([entry])
        if not args.empty:
            print("Created: " + entry.display())
        if not args.empty:
            manager.notify_shell(no=args.no)
        else:
            # Quiet mode also suppresses the plain-process reload hint.
            if os.environ.get("AKA3_SHELL_UPDATES"):
                manager.notify_shell(no=args.no)
    elif action in ("destroy", "edit"):
        entries = manager.entries()
        if action == "destroy":
            removed = [e for e in entries if e.name in args.names]
            manager.change(args.names)
            print("Removed: " + ", ".join(args.names))
            manager.notify_shell(removed, no=args.no, nounalias=args.nounalias)
        else:
            name, sep, value = args.definition.partition("=")
            matches = [e for e in entries if e.name == name]
            if len(matches) != 1:
                raise AkaError(f"Expected exactly one definition of {name}.")
            old = matches[0]
            if args.group:
                if args.name or sep:
                    raise AkaError("Use a name alone with --group.")
                new = replace(old, group=args.group)
            else:
                if not sep:
                    value = input("New name: " if args.name else "New command: ")
                    if not args.force and input("Confirm? (y/N) ").lower() not in ("y", "yes"):
                        return
                new = replace(old, name=value) if args.name else replace(old, command=value.replace("#{pwd}", shlex.quote(str(Path.cwd()))))
            manager.change([name], new)
            print("Edited: " + new.display())
            manager.notify_shell([old] if new.name != old.name else [], no=args.no)
    elif action in ("list", "find", "groups"):
        entries = manager.entries()
        if action == "groups":
            print("\n".join(sorted({e.group for e in entries})))
        elif action == "find":
            if not args.names and args.group is None:
                raise AkaError("Provide a name or --group.")
            selected = [e for e in entries if (e.group == args.group if args.group is not None else e.name in args.names)]
            missing = set(args.names) - {e.name for e in selected} if args.group is None else set()
            if missing or not selected:
                raise AkaError("No match for " + ", ".join(sorted(missing or {args.group})))
            for entry in selected:
                print(entry.display())
        else:
            count = args.count if args.count is not None else manager.config()["list"]
            selected = entries[-count:] if count else []
            for index, entry in enumerate(selected, len(entries) - len(selected) + 1):
                prefix = f"{index}. " if args.number else ""
                print(prefix + entry.display())
            print(f"A total of {sum(e.kind == 'alias' for e in entries)} aliases, "
                  f"{len({e.group for e in entries})} groups, "
                  f"{sum(line.lstrip().startswith('export ') for line in read_text(manager.path()).splitlines())} exports and "
                  f"{sum(e.kind == 'function' for e in entries)} functions from {manager.path()}")
    elif action == "usage":
        count = args.count if args.count is not None else manager.config()["usage"]
        items, total = manager.usage(count, args.least)
        for name, frequency in items:
            print(f"{name}\t{frequency}\t{frequency / total:.1%}")
        print(f"A total of {total} saved commands.")
    elif action == "clean":
        # Shell blank lines can be data in heredocs or multiline quotes. Refuse
        # ambiguous constructs rather than changing their contents.
        path = manager.path()
        with locked(path):
            content = read_text(path)
            for line in content.splitlines():
                if "<<" in line:
                    raise AkaError("Cleanup refuses files containing heredocs; edit these manually.")
            try:
                shlex.split(content, comments=True)
            except ValueError as error:
                raise AkaError("Cleanup refuses unmatched quotes.") from error
            # Preserve multiline quoted text by tracking whether each physical
            # blank line is inside an accumulated shell token.
            kept, prefix, continued = [], "", False
            for line in content.splitlines(keepends=True):
                inside = False
                try:
                    shlex.split(prefix, comments=True)
                except ValueError:
                    inside = True
                if line.strip() or inside or continued:
                    kept.append(line)
                prefix += line
                continued = line.rstrip("\r\n").endswith("\\")
            updated = "".join(kept)
            check_shell(updated, path)
            atomic_write(path, updated)
        print("Removed blank top-level lines.")
    elif action in ("proj", "export", "import"):
        if action == "export":
            export_project(manager, args.group_name, args.output, args.force)
        elif action == "proj" and args.load is not None:
            output = "proj.aka" if args.load == "load" else args.load + ".aka"
            export_project(manager, args.group_name, output, args.force)
        elif action == "import" or (action == "proj" and args.save is not None):
            path = args.path if action == "import" else (args.save or "proj.aka")
            entries = project_entries(path)
            manager.add_many(entries)
            print(f"Imported {len(entries)} shortcuts from {path}")
            manager.notify_shell(no=args.no)
        else:
            entries = project_entries("proj.aka")
            if args.group:
                print("\n".join(sorted({e.group for e in entries})))
            else:
                for entry in entries:
                    if args.group_name is None or entry.group == args.group_name:
                        print(entry.display())


def main(argv=None):
    root = parser()
    values = list(sys.argv[1:] if argv is None else argv)
    args = root.parse_args(values or ["list"])
    try:
        run(args, root)
        return 0
    except (AkaError, OSError, ValueError, yaml.YAMLError, EOFError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
