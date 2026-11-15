import contextlib
from dataclasses import replace
import io
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, HTTPServer

from aka3.cli import main, project_entries
from aka3.core import AkaError, Entry, Manager, parse_line, read_text, records


class AkaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.env = patch.dict(os.environ, HOME=str(self.home), AKA3_HOME=str(self.home / ".aka"), SHELL="/bin/bash")
        self.env.start()
        os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
        self.cwd = Path.cwd()
        os.chdir(self.home)
        self.manager = Manager()
        self.dotfile = self.home / ".bashrc"
        self.manager.setup(self.dotfile)

    def tearDown(self):
        os.chdir(self.cwd)
        self.env.stop()
        self.temporary.cleanup()

    def cli(self, *args, status=0):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            result = main(list(args))
        self.assertEqual(result, status, error.getvalue())
        return output.getvalue(), error.getvalue()

    def test_quotes_equals_and_groups_round_trip(self):
        command = "printf '%s\\n' \"$HOME=a=b # => text\" && echo 'it works'"
        entry = Entry("hello", command, "web-v2.1")
        self.assertEqual(parse_line(entry.render()), entry)
        self.cli("g", "hello=" + command, "-g", entry.group, "-n")
        self.assertEqual(self.manager.entries(), [entry])
        self.assertIn(command, self.manager.entries()[0].command)
        self.assertIn("web-v2.1", self.cli("groups")[0])

    def test_edit_preserves_group_and_failed_rename_preserves_file(self):
        self.manager.add_many([Entry("one", "echo a=b", "team"), Entry("two", "echo 2")])
        self.cli("e", "one=echo x=y=z", "-n")
        self.assertEqual(self.manager.entries()[0], Entry("one", "echo x=y=z", "team"))
        before = read_text(self.dotfile)
        self.cli("edit", "one=two", "--name", status=1)
        self.assertEqual(read_text(self.dotfile), before)
        self.cli("edit", "one=three", "--name", "-n")
        self.assertEqual(self.manager.entries()[0].name, "three")
        self.cli("e", "three", "-g", "new-team", "-n")
        self.assertEqual(self.manager.entries()[0].group, "new-team")

    def test_duplicate_generation_and_atomic_multi_destroy(self):
        self.manager.add_many([Entry("hello", "echo hello")])
        before = read_text(self.dotfile)
        self.cli("g", "hello=oops", status=1)
        self.cli("d", "hello", "missing", status=1)
        self.assertEqual(read_text(self.dotfile), before)
        self.cli("d", "hello", "-n")
        self.assertEqual(self.manager.entries(), [])
        self.assertTrue(Path(str(self.dotfile) + ".aka3.bak").exists())

    def test_export_import_and_legacy_project_directions(self):
        entries = [Entry("hi", "echo a=b 'yes'", "basic"), Entry("fhi", 'echo "$1"', "basic", "function")]
        self.manager.add_many(entries)
        self.cli("proj", "basic", "--load", "team")
        self.assertEqual(project_entries("team.aka"), entries)
        self.cli("proj", "basic", "--load", "team", status=1)
        self.cli("export", "basic")
        self.assertIn("hi", self.cli("p")[0])
        self.assertIn("basic", self.cli("proj", "-g")[0])
        self.cli("d", "hi", "fhi", "-n")
        self.cli("proj", "--save", "team.aka", "-n")
        self.assertEqual(self.manager.entries(), entries)

    def test_import_never_executes_and_validates_before_writing(self):
        marker = self.home / "executed"
        project = self.home / "bad.aka"
        project.write_text(f"alias valid='echo ok'\ntouch {marker}\n")
        before = read_text(self.dotfile)
        self.cli("import", str(project), status=1)
        self.assertFalse(marker.exists())
        self.assertEqual(read_text(self.dotfile), before)
        project.write_text(f'alias harmless="$(touch {marker})"\n')
        self.cli("import", str(project), "-n")
        subprocess.run(["bash", "-c", 'source "$1"', "test", str(self.dotfile)], check=True)
        self.assertFalse(marker.exists())

    def test_import_duplicate_and_function_escape_rejected(self):
        project = self.home / "bad.aka"
        project.write_text("alias a='echo 1'\nalias a='echo 2'\n")
        before = read_text(self.dotfile)
        self.cli("import", str(project), status=1)
        self.assertEqual(read_text(self.dotfile), before)
        self.cli("func", "escape=echo ok; }; touch unsafe; function x(){ echo bad", status=1)
        self.assertFalse((self.home / "unsafe").exists())

    def test_usage_defaults_least_zsh_and_last(self):
        history = self.home / ".bash_history"
        history.write_text("#12345\n: 123:0;git status\necho hi\ngit diff\ngit log\n")
        output, _ = self.cli("usage")
        self.assertIn("git\t3\t75.0%", output)
        self.assertIn("echo\t1", self.cli("u", "1", "--least")[0])
        self.cli("g", "recent", "--last", "-g", "work", "-n")
        self.assertEqual(self.manager.entries(), [Entry("recent", "git log", "work")])
        history.write_text("")
        self.assertIn("0 saved", self.cli("usage")[0])
        self.cli("g", "none", "--last", status=1)

    def test_listing_find_and_config(self):
        self.manager.add_many([Entry("one", "echo 1"), Entry("two", "echo 2", "team")])
        self.assertIn("2. aka g", self.cli("l", "1", "--number")[0])
        self.assertNotIn("aka g", self.cli("list", "0")[0])
        self.assertIn("one", self.cli("f", "one")[0])
        self.assertNotIn("two=", self.cli("find", "--group", "default")[0])
        self.cli("find", "missing", status=1)
        self.cli("init", "--list", "1", "--usage", "2")
        self.assertEqual(self.manager.config()["list"], 1)
        self.assertIn(str(self.dotfile), self.cli("where")[0])
        self.assertIn("dotfile ->", self.cli("config")[0])

    def test_setup_reset_symlink_and_permissions(self):
        self.cli("setup", status=1)
        self.cli("setup", "--reset", "--dotfile", str(self.dotfile))
        self.assertEqual(read_text(self.dotfile).count("# aka3"), 1)
        actual = self.home / "actual"
        self.dotfile.rename(actual)
        self.dotfile.symlink_to(actual)
        actual.chmod(0o640)
        self.cli("g", "keep=echo yes", "-n")
        self.assertTrue(self.dotfile.is_symlink())
        self.assertEqual(actual.stat().st_mode & 0o777, 0o640)

    def test_syntax_failure_does_not_write(self):
        before = read_text(self.dotfile)
        self.cli("func", "bad=if then", status=1)
        self.assertEqual(read_text(self.dotfile), before)

    def test_non_alias_data_and_multiline_content_preserved(self):
        text = 'cat <<EOF\nalias fake=bad\nEOF\nfunction outer() {\nalias inner=bad\n}\nVAR="hello\nalias quoted=bad\n"\nalias real=ok\n'
        self.assertEqual([e.name for _, e in records(text)], ["real"])
        self.dotfile.write_text('# keep\n\nTEXT="a\n\nb"\n\nalias yes=ok\n')
        self.cli("clean")
        self.assertIn('TEXT="a\n\nb"', read_text(self.dotfile))
        self.assertTrue(read_text(self.dotfile).startswith("# keep\nTEXT"))
        self.dotfile.write_text(text)
        self.cli("clean", status=1)
        self.assertEqual(read_text(self.dotfile), text)

    def test_quiet_mode_and_literal_current_directory(self):
        output, error = self.cli("g", "quiet=echo #{pwd}", "--empty")
        self.assertEqual((output, error), ("", ""))
        self.assertIn(str(self.home), self.manager.entries()[0].command)

    def test_live_shell_wrapper_bash_and_zsh(self):
        for shell in ("bash", "zsh"):
            if not shutil.which(shell):
                continue
            with self.subTest(shell=shell):
                script = '''
source "$HOME/.aka/autosource"
aka g 'livehello=echo before' -g team || exit 11
alias livehello || exit 12
aka edit 'livehello=echo after' || exit 13
alias livehello || exit 14
aka edit 'livehello=renamed' --name || exit 15
alias livehello >/dev/null 2>&1 && exit 16
alias renamed || exit 17
aka func 'livefunc=printf "%s" "$1"' || exit 18
livefunc argument || exit 19
aka d renamed livefunc || exit 20
alias renamed >/dev/null 2>&1 && exit 21
typeset -f livefunc >/dev/null 2>&1 && exit 22
exit 0
'''
                result = subprocess.run([shell, "-c", script], text=True, capture_output=True, env=os.environ)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("echo before", result.stdout)
                self.assertIn("echo after", result.stdout)
                self.assertIn("argument", result.stdout)

    def test_download_no_overwrite_or_shell_interpolation(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"alias downloaded='echo hello'\n")

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/file.aka?x=1;touch%20PWNED"
            self.cli("download", url)
            self.cli("dl", url, status=1)
            self.assertFalse((self.home / "PWNED").exists())
            self.assertEqual(Path("file.aka").read_text(), "alias downloaded='echo hello'\n")
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
