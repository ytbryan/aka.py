# Command parity and problem audit

## Baseline and scope

Reviewed [ytbryan/aka at 747bf0ccedd375dc5713aec4b734796161a2b249](https://github.com/ytbryan/aka/tree/747bf0ccedd375dc5713aec4b734796161a2b249),
whose source version is 0.1.11, and the published [aka2 0.1.10 gem](https://rubygems.org/gems/aka2/versions/0.1.10).
The gem's core/helpers match this repository; the repository moves most commands into
`lib/commands`. The user's initially supplied aka3 URL returned 404; the user confirmed
aka as the Ruby source. This Python package is a new 0.1.0 port.

Every public Ruby CLI command is represented below. Internal Ruby helper methods,
commented-out experiments, ANSI styling, and broken behavior are not a Python API
compatibility promise. The port implements the intended workflows and documents
deviations; it is not byte-for-byte output or unrestricted shell-syntax parity.

## Command coverage

| Ruby command / short form | Python behavior and differences |
| --- | --- |
| default, `list` / `l` | Recent definitions, count, `--number`, summary; includes functions; never reloads. `--group` now displays groups through rendered commands. |
| `generate` / `g` | `NAME=COMMAND`, `--group/-g`, `--last/-l`, `--no/-n`, `--empty/-e`; preserves embedded `=` and quotes. |
| `function` / `func` | Same flags; `--last` works; functions can be found, edited, listed, exported, imported, and removed. Single-line bodies without braces only. |
| `destroy` / `d` | Multiple names, `--no/-n`, `--nounalias/-u`; all names checked before one write. `--force` retained as legacy no-op. |
| `edit` / `e` | Inline or interactive edits, `--name`, `--group/-g`; preserves body/group; validates before replacing. Adds `--no/-n/--noreload`; `--force` skips interactive confirmation. |
| `find` / `f` | Exact names or `--group/-g`; default group is exact, not all groups. Missing names fail. `--force` retained as legacy no-op. |
| `usage` / `u` | Default/explicit count and working `--least`; counts first tokens of all saved commands, as Ruby intended. Percentages use floating point. |
| `setup` | Existing YAML path, explicit `--dotfile`, shell-based default, safe `--reset`, user startup file only, shell wrapper instead of traps. |
| `init` | All declared path/metadata/count options, `--config`, `--bashrc`, `--zshrc`, `--bash`; counts must be nonnegative integers; no `/etc` writes. |
| `proj` | Display project definitions, `--group/-g`, legacy `--load/-l` export and `--save/-s` import, `--force/-f`. Adds documented `p` alias and `--no/-n`. |
| `download` / `dl` | HTTP(S) file download, no shell, no execution; adds output and force flags, 30-second network timeout and 10 MiB limit. |
| `clean` / `c` | Remove blank lines conservatively; preserve quoted multiline data; refuse heredocs. Backup and syntax check before write. |
| `config`, `groups`, `where` | Configuration, group names, configured dotfile path. |
| `version` / `v`, `help` / `h` | Python version and command-specific help; also `--version` and `--help`. |
| README's `export` | Implemented as a real command, with `--output/-o` and `--force/-f`. Adds explicit `import` to clarify project direction. |

The undeclared Ruby `usage --clear` branch and `init --count` branch are not supported;
they are unreachable through the strict Ruby CLI and do not implement working features.
Unknown options are rejected. `list --force` and `list --no` remain accepted for old
scripts but have no effect; list is read-only. Source config keys `home`, `profile`,
`install`, and `remote` are retained as metadata, not claims of remote management.

## Problems to fix, in priority order

### P1: Unexpected shell execution while importing or downloading

[helpers.rb:715](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/helpers.rb#L715)
turns project definitions into command strings, changes quote styles, and executes
them with `system(line)`. A quoted alias containing `$()` can execute while importing,
before the user invokes that alias. This is reachable when consuming an untrusted
project file. [aka.rb:26](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka.rb#L26)
also interpolates a URL into `curl -O ...`; shell metacharacters in the URL can become
commands. Fix: parse project definitions as data and avoid shell interpolation.
Implemented in Python; tests check that import/substitution and URL metacharacters
do not create marker files. Downloaded definitions are never automatically imported.

### P1: Reload can signal the wrong process or terminate the shell

[core.rb](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/core.rb)
sends SIGUSR1/SIGUSR2 to the parent without checking that it is an initialized shell.
Without the trap, these signals can terminate the recipient. `exec zsh` runs in the
child and cannot replace or update the parent shell. A `.zshrc` path is also treated
as proof of Oh My Zsh, although these are different things. Fix: a parent-shell
wrapper sources changes after the CLI succeeds; direct invocation prints instructions.
Implemented, tested in Bash and Zsh. Old traps require manual removal during migration.

### P1: Alias bodies are truncated or broken by ordinary characters

[helpers.rb:120–173](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/helpers.rb#L120)
and the editing/export paths split on every `=` and retain only the next field.
For example, `x=echo a=b` stores `echo a`. Single quotes are embedded without escaping,
and newlines are silently removed. Fix: split once, quote shell literals correctly,
and reject unsupported multiline definitions. Implemented and regression-tested.

### P1: Inline rename destroys the command; edits can lose groups or data

[edit.rb](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/commands/edit.rb)
passes the old alias name to `edit_alias_name` as its second argument.
[helpers.rb:395](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/helpers.rb#L395)
then uses that name as the new command: renaming `hello` to `hi` produces `hi='hello'`
instead of keeping the original body. Inline command edits drop group metadata.
Interactive paths remove the old definition before rebuilding it; nil group handling
uses `!group.nil? || !group.empty?`, which can call `empty?` on nil. Fix: validate the
replacement first and replace exactly one record atomically, preserving metadata.
Implemented; a conflicting rename leaves the file unchanged.

### P1: Setup can write system profiles and reset fails to remove integration

[config.rb:152](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/config.rb#L152)
selects `/etc/profile` for `.bash_profile` / `.profile`, then appends its autosource
hook there. This creates permission errors and invites unnecessary sudo use.
[helpers.rb:334](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/helpers.rb#L334)
removes only a hardcoded `/home/ryan/.aka/autosource` source line. No startup files
also leaves placeholder `/home/user` paths. Fix: select/create a user startup file,
make installation idempotent, preserve aliases on reset, and use real user paths.
Implemented; no user configuration was changed while building this port.

### P2: `usage` crashes, exposes unreachable options, and computes wrong percentages

[usage.rb](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/commands/usage.rb)
calls nonexistent `Aka.howlast` without a count. `--least` / `--clear` are tested but
not declared, and the default least path calls `showlast` with the wrong signature.
[helpers.rb:568](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/helpers.rb#L568)
divides rounded integers, so 3/4 becomes 0%; least-used indexing can use the wrong
count or nil. Fix: one counting path, declared options, stable sorting, floating-point
ratios, empty-history handling. Implemented. This measures saved first command tokens,
not exact runtime alias invocations; pipelines and unsaved session history remain
outside scope. It intentionally does not add a destructive history-clear command.

### P2: Project documentation, names, and overwrite rules disagree

The [README](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/README.md)
documents `aka export`, which has no registered command. `proj --load` exports while
`--save` imports; help claims a `p` alias absent from the map. The import/export
parameter routing makes `proj --load basic` use `basic` as the filename stem rather
than the group. Named exports overwrite existing files without `--force`, unlike
`proj.aka`. Fix: explicit export/import, retain documented legacy directions, require
force consistently. Implemented; use `aka export basic` as the clear default.

### P2: Functions, groups, and history flags are inconsistent

Function generation declares `--last` and `--empty` but ignores them. Most helpers
only recognize `alias`, so functions cannot be reliably edited, found, removed, or
exported and can be duplicated. Alias `--last` calls `add_with_group` without the
required group argument. Group regex `[a-zA-z]*` truncates digits/hyphens and admits
punctuation in the ASCII gap. Default-group find lists all aliases. `list --group`
is passed through but never used. Fix: shared entry model, consistent flags,
validated full group names, explicit default group. Implemented for the supported
single-line definitions.

### P2: File rewrites lack transactional protection

The Ruby helpers truncate and rewrite dotfiles without backups or writer locks.
`clean` removes every blank line, including meaningful heredoc/quoted data. Alias
listing's `print_the_aliases` accesses `value[1]` before checking line length and can
crash on blank/comment lines. Fix: preserve unrelated text, lock cooperating writers,
validate syntax, write through a temporary file, keep a backup, parse defensively.
Implemented. Locks do not protect against editors that ignore them; complex shell
files still warrant manual review.

### P3: Release and test coverage do not match the project claims

The repository advertises 0.1.11 but the fetched published gem is 0.1.10. Its two
[specs](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/spec/aka_spec.rb)
depend on real user shell configuration, and the generation example expects a
different alias spelling from its input. Fix: isolated homes, actual CLI/shell tests,
clean-install checks, and build validation. Implemented for Python; the Ruby source
and published Ruby gem have not been modified by this work.

## Remaining limits and release work

- Confirm PyPI ownership/name availability, then publish from the intended account.
  The initial implementation built local artifacts. Pushing source to GitHub does not publish a PyPI release.
- The port is POSIX-only. Windows shells, Fish, complex/multiline function bodies,
  dynamically generated definitions, arbitrary sourced-file traversal, and exact
  Ruby terminal formatting are not implemented.
- The parser is conservative, not a shell interpreter. Multiple definitions on one
  line and conditional/dynamic aliases should be edited manually. Rewriting a
  double-quoted alias as a literal can change expansion timing; keep such aliases
  outside this tool if that timing is intentional.
- Setup/reload sources the configured startup file, so its normal side effects run
  again. Use `--no` if you want to defer this; startup scripts should be idempotent.
- `init` retains legacy metadata keys without promising remote/install workflows
  absent from the Ruby implementation. Old signal traps must be removed manually.
- Local verification runs on Python 3.9/macOS with Bash and Zsh. CI is configured
  for Python 3.9, 3.12, and 3.14 on Linux; those remote jobs have not run here.

## Verification

The suite covers quote/equals/group round-trips; aliases and functions; edit and
rename metadata; duplicates and all-or-nothing imports/deletes; non-executing imports;
legacy project directions; usage defaults/least/Zsh timestamps; saved last-command
generation; setup/reset, symlinks, mode and backups; syntax failures; multiline data;
quiet mode; and a real local HTTP download including overwrite rejection. The shell
integration test creates, edits, renames, and removes shortcuts in both Bash and Zsh.
Ruby expressions were also checked directly to confirm truncation, group truncation,
and integer percentage division. The report's other Ruby findings are source analysis,
not a claim that the upstream Ruby integration suite passed.
