import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def call(*args, cwd=None, env=None, input=None):
    return subprocess.run(args, cwd=cwd, env=env, input=input, text=True, capture_output=True)


class FcomTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        self.bin = Path(self.tmp.name) / 'bin'
        self.bin.mkdir()
        fx = self.bin / 'fx'
        fx.write_text('#!/usr/bin/env python3\nimport json,os,sys,time\np=sys.stdin.read()\nassert "Diff" in p\ntime.sleep(float(os.environ.get("FX_DELAY", "0")))\nif os.environ.get("FX_FAIL"):\n sys.exit(1)\nmessages=json.loads(os.environ.get("FX_MESSAGES", "[\\"feat: first\\",\\"docs: second\\"]"))\nprint(json.dumps({"final_output":json.dumps({"commits":[{"message":messages[0],"changes":[1]},{"message":messages[1],"changes":[2]}]})}))\n')
        fx.chmod(0o755)
        self.env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}',
                        GIT_AUTHOR_NAME='Tester', GIT_AUTHOR_EMAIL='test@example.org',
                        GIT_COMMITTER_NAME='Tester', GIT_COMMITTER_EMAIL='test@example.org')
        self.git('init', '-q')
        (self.repo / 'one.txt').write_text('old\n')
        self.git('add', 'one.txt')
        self.git('commit', '-qm', 'initial')

    def git(self, *args):
        result = call('git', *args, cwd=self.repo, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_split_including_staged_and_untracked(self):
        (self.repo / 'one.txt').write_text('new\n')
        self.git('add', 'one.txt')
        (self.repo / 'two.txt').write_text('untracked\n')
        result = call(str(ROOT / 'fcom'), cwd=self.repo, env=self.env, input='y\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('log', '-2', '--format=%s').splitlines(), ['docs: second', 'feat: first'])
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertIn('one.txt (+1/-1 lines)', result.stdout)
        self.assertIn('two.txt (+1/-0 lines)', result.stdout)
        self.assertIn('Generating commit plan...', result.stderr)
        self.assertNotIn('diff --git', result.stdout)
        self.assertNotIn('untracked', result.stdout)

    def test_reject_keeps_staged_data(self):
        (self.repo / 'one.txt').write_text('new\n')
        self.git('add', 'one.txt')
        (self.repo / 'two.txt').write_text('untracked\n')
        before = self.git('status', '--porcelain')
        result = call(str(ROOT / 'fcom'), cwd=self.repo, env=self.env, input='n\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('status', '--porcelain'), before)
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'initial')

    def test_one_prompt_message_edit(self):
        (self.repo / 'one.txt').write_text('new\n')
        (self.repo / 'two.txt').write_text('untracked\n')
        result = call(str(ROOT / 'fcom'), cwd=self.repo, env=self.env,
                      input='{"1":"fix: custom","2":"chore: other"}\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('log', '-2', '--format=%s').splitlines(), ['chore: other', 'fix: custom'])
        self.assertEqual(result.stdout.count('Commit these changes?'), 1)

    def test_separate_hunks_in_one_file(self):
        (self.repo / 'one.txt').write_text(''.join(f'line {i}\n' for i in range(30)))
        self.git('add', 'one.txt')
        self.git('commit', '-qm', 'long file')
        lines = (self.repo / 'one.txt').read_text().splitlines(keepends=True)
        lines[1] = 'first change\n'
        lines[25] = 'second change\n'
        (self.repo / 'one.txt').write_text(''.join(lines))
        result = call(str(ROOT / 'fcom'), cwd=self.repo, env=self.env, input='y\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('log', '-2', '--format=%s').splitlines(), ['docs: second', 'feat: first'])
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(result.stdout.count('one.txt (+1/-1 lines)'), 2)

    def test_invalid_fx_message_cannot_be_committed(self):
        (self.repo / 'one.txt').write_text('new\n')
        (self.repo / 'two.txt').write_text('untracked\n')
        env = dict(self.env, FX_MESSAGES='["first", "docs: second"]')
        result = call(str(ROOT / 'fcom'), cwd=self.repo, env=env, input='y\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'initial')

    def test_invalid_edited_message_aborts(self):
        (self.repo / 'one.txt').write_text('new\n')
        (self.repo / 'two.txt').write_text('untracked\n')
        result = call(str(ROOT / 'fcom'), cwd=self.repo, env=self.env,
                      input='{"1":"untyped message"}\n')
        self.assertEqual(result.returncode, 0)
        self.assertIn('Cancelled.', result.stdout)
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'initial')

    def test_fx_failure_clears_progress_without_committing(self):
        (self.repo / 'one.txt').write_text('new\n')
        env = dict(self.env, FX_FAIL='1', FX_DELAY='0.1')
        result = call(str(ROOT / 'fcom'), cwd=self.repo, env=env, input='y\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Generating commit plan...', result.stderr)
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'initial')

    def test_reverted_staged_change_is_not_silently_dropped(self):
        (self.repo / 'one.txt').write_text('new\n')
        self.git('add', 'one.txt')
        (self.repo / 'one.txt').write_text('old\n')
        result = call(str(ROOT / 'fcom'), cwd=self.repo, env=self.env, input='y\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('staged', result.stderr)
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'initial')

    def test_staged_setting(self):
        (self.repo / 'one.txt').write_text('new\n')
        self.git('add', 'one.txt')
        (self.repo / 'two.txt').write_text('untracked\n')
        self.assertEqual(call(str(ROOT / 'fcom-config'), 'staged', cwd=self.repo, env=self.env).returncode, 0)
        # fx returns an invalid plan for one unit, so nothing can be committed.
        result = call(str(ROOT / 'fcom'), cwd=self.repo, env=self.env, input='y\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'initial')
        self.assertIn('two.txt', self.git('status', '--porcelain'))


if __name__ == '__main__':
    unittest.main()
