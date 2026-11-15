# aka.py / aka3

An alias manager for your terminal. A Python port of [Bryan Lim's aka / aka2 RubyGem](https://github.com/ytbryan/aka).
Manage permanent Bash and Zsh aliases, functions, groups, and project shortcuts.
Python 3.9+ on macOS or Linux, with Bash or Zsh installed. Runtime dependency: PyYAML.

## Install

The GitHub repository is `ytbryan/aka.py`; the Python distribution and import name
are `aka3`. Use Python 3.9+ on macOS or Linux with Bash or Zsh installed.

Install from PyPI in an isolated environment:

```sh
python3 -m venv ~/.venvs/aka3
source ~/.venvs/aka3/bin/activate
python -m pip install aka3
aka --version
aka setup
```

To install the current GitHub source instead, use
`python -m pip install 'git+https://github.com/ytbryan/aka.py.git'` in the activated
environment. Git must be installed for that method. For development, clone first:

```sh
git clone https://github.com/ytbryan/aka.py.git
cd aka.py
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
aka setup
```

From an existing checkout:

```sh
python3 -m pip install .
aka setup
```

Setup prints a `source` command. Run it once to enable the shell wrapper and automatic
reload. New shells load it from your startup file. `aka3` is also an executable.
Activate the same virtual environment in each new shell before using `aka`, or add
its `bin` directory to your PATH. Do not run setup with sudo.
The `aka` executable shares its name with the Ruby gem; use a dedicated Python
environment and put its `bin` directory first in PATH when migrating.

```sh
aka g 'hello=echo hello world' --group basic
aka func 'greet=printf "%s\n" "$1"' -g basic
aka list 20 --number
aka find hello
aka find --group basic
aka edit 'hello=echo goodbye'
aka edit 'hello=welcome' --name
aka edit welcome --group greetings
aka destroy welcome
aka usage 10
aka usage --least
```

Quote the entire `NAME=COMMAND` argument to prevent your invoking shell from expanding
variables or substitutions before aka receives them. Alias names use portable shell
identifiers; functions accept single-line bodies without braces. Groups support
letters, digits, `_`, `-`, and `.`. `#{pwd}` in a command becomes the quoted current
directory. `aka g NAME --last` saves the last command already written to the configured
history file. Flush history first (`history -a` in Bash, `fc -AI` in Zsh); a child process
cannot read the parent's in-memory history. Zsh extended timestamps are supported;
multiline history and full shell pipeline analysis are outside the history counter.

## Projects

```sh
aka export basic                    # writes proj.aka
aka export basic -o team.aka
aka proj                            # inspect proj.aka
aka proj --group                    # inspect project groups
aka import team.aka                 # persist definitions, without executing the file
aka proj basic --load team          # legacy export to team.aka
aka proj basic --load               # legacy export to proj.aka
aka proj --save team.aka            # legacy import
```

Export without a group includes all managed shortcuts. Existing output requires
`--force`. Imports validate the entire file and all duplicate names before writing;
conflicts fail without changing your dotfile. Files contain alias/function definitions,
not `aka g` command lines. Imported alias bodies are stored literally, including `$()`;
functions run when explicitly invoked. As with your own aliases, review definitions
before invoking them.

## Configuration and migration

```sh
aka setup --dotfile ~/.zshrc
aka setup --reset --dotfile ~/.bashrc
aka config
aka where
aka init --history ~/.bash_history --list 30 --usage 10
aka groups
aka download https://example.org/team.aka
aka help
aka help edit
```

Configuration uses the original YAML path `~/.aka/.config` and reads existing aka2
keys. `AKA3_HOME` overrides the config directory for isolated installations and tests.
`init --bashrc`, `--zshrc`, and `--bash` select `.bashrc`, `.zshrc`, and `.bash_profile`.
`init` changes paths only; run `setup --reset --dotfile PATH` to install the wrapper
in a different startup file. `home`, `install`, `profile`, and `remote` are retained
metadata; they do not install files, move the config directory, or contact a server.

When migrating from Ruby, remove the old aka2 `autosource` source line and SIGUSR1/
SIGUSR2 traps manually. The Python setup installs no signal traps. Reset preserves
your aliases and does not remove old shell integrations or startup files.

Without the wrapper, mutations print the `source` command needed to reload. `-n` /
`--no` suppresses reload. `destroy --nounalias` keeps the removed alias in the current
shell until it exits. Listing, searching, and usage never reload the shell. With the
wrapper, renaming/removing also clears the old shell definition. The wrapper sources
your configured dotfile after a successful mutation, so its normal startup commands
run again. `--empty` suppresses generate/function output.

Files are updated atomically with mode preservation and a rolling `.aka3.bak` backup.
A sibling `.aka3.lock` coordinates aka3 writers (other editors do not take this lock).
Unrelated lines are retained. This is a conservative editor for single-line literal
aliases and aka-style functions, not a full shell parser. Multiline definitions,
multiple aliases per line, dynamic shell-generated aliases, conditional definitions,
and aliases in sourced files should be managed manually. Editing/exporting a double-
quoted alias normalizes it to a literal single-quoted definition; expansion timing
can therefore change. `clean` refuses heredocs and preserves multiline quoted data.
Back up complex startup files before migration.

See [the command parity and audit report](https://github.com/ytbryan/aka.py/blob/main/docs/COMMAND_AUDIT.md) for all commands,
upstream findings, and intentional compatibility changes.
See [the fix report](https://github.com/ytbryan/aka.py/blob/main/docs/FIX_REPORT.md) for exact Python fix lines, test locations,
and remaining work.

## Development and release

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e . build twine
python -m unittest discover -s tests -v
python -m build
python -m twine check dist/*
```

After verifying ownership/availability of `aka3` on PyPI and reviewing the release,
publish with `python -m twine upload dist/*` using your own account. No publishing
credentials or automatic release upload are configured. MIT licensed; original
copyright is retained in LICENSE.
