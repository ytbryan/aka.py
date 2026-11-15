# aka3 fix report: Ruby issue → Python line → test

Prepared 15 November 2026. This report describes the current checkout in
`/Users/ytbryan/Documents/ChatGPT/aka3`. Line numbers refer to this version and may
move after future edits. Each source link identifies the first relevant line on GitHub; the adjacent
range states the full block to review.

The Ruby baseline is [ytbryan/aka, revision 747bf0c](https://github.com/ytbryan/aka/tree/747bf0ccedd375dc5713aec4b734796161a2b249).
The fixes below are in the Python port. The original Ruby repository has not been
patched. This is a new implementation, so the links identify the replacement logic
rather than corresponding lines in a Ruby diff.

## Where each fix lives

| # | Issue | Primary Python fix | Verification |
| --- | --- | --- | --- |
| 1 | Commands lose text after a second `=` | [cli.py:107](../src/aka3/cli.py#L107), [core.py:84](../src/aka3/core.py#L84) | [test:45](../tests/test_aka3.py#L45) |
| 2 | Single quotes break persisted aliases | [core.py:56](../src/aka3/core.py#L56) | [test:45](../tests/test_aka3.py#L45) |
| 3 | Rename replaces the command with the old alias name | [cli.py:234](../src/aka3/cli.py#L234) | [test:54](../tests/test_aka3.py#L54), [shell test:168](../tests/test_aka3.py#L168) |
| 4 | Edits lose groups or remove the old entry before validation | [core.py:255](../src/aka3/core.py#L255) | [test:54](../tests/test_aka3.py#L54) |
| 5 | Import unexpectedly executes shell commands | [cli.py:125](../src/aka3/cli.py#L125) | [test:89](../tests/test_aka3.py#L89) |
| 6 | Download URL is interpolated into a shell command | [cli.py:137](../src/aka3/cli.py#L137) | [test:195](../tests/test_aka3.py#L195) |
| 7 | Reload signals may terminate the parent process | [core.py:302](../src/aka3/core.py#L302), [wrapper:319](../src/aka3/core.py#L319) | [test:168](../tests/test_aka3.py#L168) |
| 8 | Setup chooses placeholders/system profiles; reset duplicates integration | [core.py:210](../src/aka3/core.py#L210) | [test:135](../tests/test_aka3.py#L135) |
| 9 | `usage` crashes by default and computes wrong percentages | [core.py:290](../src/aka3/core.py#L290), [cli.py:261](../src/aka3/cli.py#L261) | [test:111](../tests/test_aka3.py#L111) |
| 10 | `--last` fails; Zsh timestamps pollute commands | [core.py:279](../src/aka3/core.py#L279), [cli.py:193](../src/aka3/cli.py#L193) | [test:111](../tests/test_aka3.py#L111) |
| 11 | Functions cannot be managed consistently | [core.py:41](../src/aka3/core.py#L41), [cli.py:202](../src/aka3/cli.py#L202) | [test:76](../tests/test_aka3.py#L76), [test:168](../tests/test_aka3.py#L168) |
| 12 | Group names truncate; default-group find returns everything | [core.py:23](../src/aka3/core.py#L23), [cli.py:245](../src/aka3/cli.py#L245) | [test:45](../tests/test_aka3.py#L45), [test:123](../tests/test_aka3.py#L123) |
| 13 | Documented export and `p` alias are missing; load/save are confusing | [cli.py:71](../src/aka3/cli.py#L71), [cli.py:297](../src/aka3/cli.py#L297) | [test:76](../tests/test_aka3.py#L76) |
| 14 | Named exports silently overwrite files | [cli.py:117](../src/aka3/cli.py#L117) | [test:81](../tests/test_aka3.py#L81) |
| 15 | Duplicate imports/multi-delete can leave partial changes | [core.py:239](../src/aka3/core.py#L239), [core.py:260](../src/aka3/core.py#L260) | [test:66](../tests/test_aka3.py#L66), [test:102](../tests/test_aka3.py#L102) |
| 16 | Direct rewrites risk losing dotfile contents | [core.py:154](../src/aka3/core.py#L154), [lock:173](../src/aka3/core.py#L173) | [test:66](../tests/test_aka3.py#L66), [test:135](../tests/test_aka3.py#L135) |
| 17 | Invalid function syntax can corrupt startup files | [core.py:144](../src/aka3/core.py#L144) | [test:147](../tests/test_aka3.py#L147) |
| 18 | `clean` removes meaningful blank lines | [cli.py:267](../src/aka3/cli.py#L267) | [test:152](../tests/test_aka3.py#L152) |
| 19 | Blank/comment lines and embedded alias-looking data confuse parsing | [core.py:64](../src/aka3/core.py#L64), [records:108](../src/aka3/core.py#L108) | [test:152](../tests/test_aka3.py#L152) |
| 20 | `--empty` is declared but ignored | [cli.py:204](../src/aka3/cli.py#L204) | [test:163](../tests/test_aka3.py#L163) |

## What the lines actually change

### 1–2. Preserve complete commands and quote them correctly

Ruby [helpers.rb:139](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/helpers.rb#L139)
splits the definition on every equals sign and places the selected field inside raw
single quotes. `x=echo a=b` can become `x='echo a'`; apostrophes can break the shell syntax.

Python CLI line 107 and parser line 84 use `split("=", 1)`. Edit line 220 uses
`partition("=")` for the same reason. Core lines 55–57 escape apostrophes before
rendering the alias. Core lines 27–37 validate names, nonempty bodies, groups, and
unsupported newlines instead of silently stripping data.

### 3–4. Keep the command and group when editing or renaming

Ruby [edit.rb:19](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/commands/edit.rb#L19)
passes the old name to [helpers.rb:395](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/helpers.rb#L395),
which uses it as the new body. Other edit paths delete first and rebuild later.

Python CLI lines 224–235 copy the existing entry with only the requested field
changed: `replace(old, name=value)`, `replace(old, command=...)`, or
`replace(old, group=...)`. Core lines 260–266 check that the original is unambiguous
and the replacement name is available. Lines 267–277 replace the record in place
only after validation. A failed rename leaves the original file untouched.

### 5–6. Remove unexpected execution from import and download

Ruby [helpers.rb:715](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/helpers.rb#L715)
rewrites quotes and runs imported command strings through `system`.
[aka.rb:26](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka.rb#L26)
interpolates the download URL into a shell command.

Python CLI lines 125–134 accept definitions and comments only. Lines 303–306 parse
the whole import before passing entries to one validated write. Alias bodies are
rendered as literals. CLI lines 137–154 use `urlopen`, validate HTTP(S), set a timeout
and size cap, and write the response directly. There is no shell command to interpolate.

These fixes prevent execution during parsing/downloading. They do not make arbitrary
alias/function bodies trustworthy: invoking an imported shortcut runs its body.

### 7. Update the invoking shell without sending signals

Ruby [core.rb:2](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/core.rb#L2)
sends parent-process signals or launches a child Zsh.

Python core lines 302–316 produce shell update instructions. Lines 319–331 define
the wrapper: create a temporary file, run the CLI, source updates only after exit
status zero, then remove the temporary file. Lines 307–309 remove old definitions
when appropriate. No SIGUSR1/SIGUSR2 is sent.

Without the wrapper, line 316 prints a reload instruction. Sourcing a dotfile alone
does not unset a removed alias; direct CLI users must also remove the old shell
definition or restart their shell. `--no` currently suppresses all shell updates,
including unalias/unset; it is not identical to Ruby's destroy flag behavior.

### 8. Use real user paths and avoid automatic system-profile selection

Ruby [config.rb:92](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/aka/config.rb#L92)
writes placeholder paths. Its Bash-profile setup chooses `/etc/profile`.

Python core lines 213–220 derive user paths. Lines 223–229 add one marked source
line only if it is absent, with syntax validation. Reset preserves the dotfile's
aliases. CLI lines 180–183 map the legacy shell selectors to user startup files.

This is a partial migration fix: the old Ruby traps/source hooks are not automatically
removed, and setup is not one transaction spanning all three generated files.
An explicitly supplied `--dotfile` path is honored; this is not a prohibition against
someone deliberately selecting a system file they can write.

### 9–10. Make usage and last-command generation work consistently

Ruby [usage.rb:18](https://github.com/ytbryan/aka/blob/747bf0ccedd375dc5713aec4b734796161a2b249/lib/commands/usage.rb#L18)
calls nonexistent `howlast`. Its least-used branch and integer percentage division
also produce incorrect behavior. Ruby's `--last` path omits a required group argument.

Python CLI lines 59–61 declare the usage arguments. Core lines 279–288 remove Bash
timestamp records and Zsh timestamp prefixes. Lines 290–300 count and sort first
command tokens. CLI lines 261–266 use the configured default and floating-point
division. Lines 193–202 handle the last saved command, reject empty history, and
carry the requested group into the new entry.

The counter measures saved history, not in-memory history or exact alias execution.
Multiline history and full shell command analysis remain unsupported.

### 11–12. Use one entry model for aliases, functions, and groups

Ruby helpers mostly recognize `alias`; generated functions cannot use the same
management workflows. Group matching uses `[a-zA-z]*`, which truncates many names.

Python core lines 41–61 store name, body, group, and kind together. Lines 67–72 parse
the supported function format. CLI line 202 chooses the kind; both kinds use the same
mutation/export code. Core lines 23 and 32–33 validate full group names; lines 104–105
read group metadata. CLI line 245 performs exact group matching, including `default`.

This supports single-line aka-style functions only. Core lines 36–37 reject braces
anywhere in a function body, including `${variable}` or braces inside quoted text.
That conservative restriction is a remaining compatibility gap.

### 13–14. Make project commands explicit and protect output files

Ruby documents an unregistered `export` command and an unmapped `p` alias. Its legacy
load/save names describe the opposite direction from what many users expect.

Python CLI lines 71–85 register `p`, `export`, and `import`. Lines 297–308 route
operations while retaining legacy `proj --load` as export and `--save` as import.
Lines 117–119 reject existing export files without force, including named exports.
Download line 152 separately uses exclusive file creation unless force is supplied.

The legacy directions remain confusing; prefer `aka export GROUP` and `aka import FILE`.

### 15–17. Validate before writing and make individual replacements safer

Python core lines 240–248 validate all incoming entries and reject duplicate names
before constructing output. Lines 260–266 validate all deletion targets and rename
conflicts before mutation. This makes a duplicate import or missing delete target
fail without partial changes to that dotfile.

Core lines 154–170 resolve symlinks, keep a rolling backup, write through a temporary
file, flush it, preserve mode bits, and replace the destination atomically. Lines
173–179 lock cooperating aka3 writers. Lines 144–151 run Bash/Zsh with `-n` to check
syntax; calls at 252 and 276 prevent invalid generated definitions from being written.

The guarantees apply to individual managed file updates. They do not cover external
editors, configuration read-modify-write races, filesystem ownership/ACL preservation,
or transactions across multiple files. Syntax checks do not prove semantic equivalence.

### 18–19. Preserve supported shell data during cleanup and parsing

Ruby cleanup removes blank lines indiscriminately. Its project alias printer also
indexes a token before checking whether that token exists.

Python CLI lines 273–279 refuse heredocs and unmatched quotes. Lines 282–292 preserve
blank lines inside tracked quoted text and after a line continuation; lines 293–295
check syntax before writing. Core lines 73–86 check token counts before reading
assignment fields. Lines 108–141 skip tracked heredoc, quoted, and brace-block content
when finding managed entries.

This is a conservative parser, not a complete Bash/Zsh parser. The existing test
covers one heredoc, one nested function, and multiline quoted content. Conditional
definitions, complex nesting, and alternate heredoc forms still need broader handling.
The cleanup heredoc test deliberately rejects any line containing `<<`, even inside
a comment or a literal; that is conservative rather than exact syntax recognition.

### 20. Honor quiet generation

Python CLI lines 204–211 suppress the creation message and direct-process reload
hint under `--empty`, while still writing wrapper updates when the wrapper is active.
The quiet-mode test exercises alias generation. The same branch serves functions,
but there is no separate quiet-function regression case yet. Output from sourcing
the user's own startup file is outside the CLI's quiet-output control.

## Packaging and evidence

The package definition is in [pyproject.toml:5](../pyproject.toml#L5).
Lines 26–28 install both executables. The isolated test environment starts at
[test_aka3.py:21](../tests/test_aka3.py#L21).
The CI matrix is configured at [test.yml:8](../.github/workflows/test.yml#L8).

Verification completed in the implementation turn:

- All 14 test methods passed against the installed wheel on Python 3.9/macOS.
- The shell integration test passed with both local Bash and Zsh.
- The wheel installed into a fresh temporary environment with PyYAML.
- Wheel and source archive passed `twine check`.
- Ruby expressions confirmed equals-sign truncation, group truncation, and integer
  percentage division. Other Ruby findings are source analysis, not a passed Ruby suite.

Those checks do not establish Windows compatibility, arbitrary shell-syntax support,
or successful execution of the remote Python 3.12/3.14 CI jobs. This reporting turn
adds documentation only; it does not rerun those earlier checks or change code.

## What still needs work

1. **Shell compatibility:** expand parsing and tests before managing complex startup
   files; support function braces and explicitly model dynamic alias expansion timing.
2. **Migration and shell behavior:** automate old Ruby hook cleanup, cover direct
   invocation deletion/rename instructions, and decide/document exact `--no` semantics.
3. **Configuration reliability:** make setup rollback across files possible, validate
   proposed config values before saving, and lock configuration updates consistently.
4. **More targeted tests:** function-specific quiet/last flags, failed setup rollback,
   alternate heredocs, shell-update flags, concurrent writers, download redirects,
   timeout/size-limit failures, and custom Zsh startup filenames. Shell checking
   currently selects Zsh only when the basename is `.zshrc` (core line 145).
5. **Release:** review these compatibility limits and verify PyPI account/name access
   before publishing to PyPI. A GitHub source push does not publish a PyPI release.

The earlier [command audit](../docs/COMMAND_AUDIT.md)
contains the complete command matrix and broader Ruby problem descriptions. This
report provides the exact implementation locations and narrows any claims that would
otherwise imply complete shell compatibility or universal transactional protection.
