# Copyright 2016 Rackspace
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the
#    License. You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing,
#    software distributed under the License is distributed on an "AS
#    IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
#    express or implied. See the License for the specific language
#    governing permissions and limitations under the License.

import errno
import inspect
import json
import subprocess
import unittest

import github
import mock
import timid

import timid_github


class TestException(Exception):
    pass


class TestGit(unittest.TestCase):
    def make_child(self, stdout=b'stdout', stderr=b'stderr', returncode=0):
        return mock.Mock(**{
            'communicate.return_value': (stdout, stderr),
            'returncode': returncode,
        })

    def make_ctxt(self, *children, **kwargs):
        if not children:
            children = [self.make_child(**kwargs)]
        else:
            children = list(children)

        return mock.Mock(**{
            'environment.call.side_effect': children,
        })

    @mock.patch.object(timid_github.time, 'sleep')
    def test_base(self, mock_sleep):
        ctxt = self.make_ctxt()

        result = timid_github._git(ctxt, 'spam', 'arg1', 'arg2')

        self.assertEqual(result, b'stdout')
        ctxt.environment.call.assert_called_once_with(
            ['git', 'spam', 'arg1', 'arg2'], close_fds=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertFalse(mock_sleep.called)

    @mock.patch.object(timid_github.time, 'sleep')
    def test_base_failure(self, mock_sleep):
        ctxt = self.make_ctxt(returncode=1)

        self.assertRaises(timid_github.GitException,
                          timid_github._git, ctxt, 'spam', 'arg1', 'arg2')
        ctxt.environment.call.assert_called_once_with(
            ['git', 'spam', 'arg1', 'arg2'], close_fds=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertFalse(mock_sleep.called)

    @mock.patch.object(timid_github.time, 'sleep')
    def test_base_failure_noraise(self, mock_sleep):
        ctxt = self.make_ctxt(returncode=1)

        result = timid_github._git(ctxt, 'spam', 'arg1', 'arg2',
                                   do_raise=False)

        self.assertEqual(result, b'stdout')
        ctxt.environment.call.assert_called_once_with(
            ['git', 'spam', 'arg1', 'arg2'], close_fds=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertFalse(mock_sleep.called)

    @mock.patch.object(timid_github.time, 'sleep')
    def test_retries_base(self, mock_sleep):
        ctxt = self.make_ctxt(
            self.make_child(stdout=timid_github.SSH_ERROR, returncode=1),
            self.make_child(stderr=timid_github.SSH_ERROR, returncode=1),
            self.make_child(stdout=b'final success'),
        )

        result = timid_github._git(ctxt, 'spam', 'arg1', 'arg2',
                                   ssh_retries=5)

        self.assertEqual(result, b'final success')
        ctxt.environment.call.assert_has_calls([
            mock.call(['git', 'spam', 'arg1', 'arg2'], close_fds=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE),
            mock.call(['git', 'spam', 'arg1', 'arg2'], close_fds=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE),
            mock.call(['git', 'spam', 'arg1', 'arg2'], close_fds=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE),
        ])
        self.assertEqual(ctxt.environment.call.call_count, 3)
        mock_sleep.assert_has_calls([
            mock.call(1),
            mock.call(2),
        ])
        self.assertEqual(mock_sleep.call_count, 2)

    @mock.patch.object(timid_github.time, 'sleep')
    def test_retries_too_many(self, mock_sleep):
        ctxt = self.make_ctxt(
            self.make_child(stdout=timid_github.SSH_ERROR, returncode=1),
            self.make_child(stderr=timid_github.SSH_ERROR, returncode=1),
            self.make_child(stdout=b'final success'),
        )

        self.assertRaises(timid_github.GitException,
                          timid_github._git, ctxt, 'spam', 'arg1', 'arg2',
                          ssh_retries=2)
        ctxt.environment.call.assert_has_calls([
            mock.call(['git', 'spam', 'arg1', 'arg2'], close_fds=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE),
            mock.call(['git', 'spam', 'arg1', 'arg2'], close_fds=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE),
        ])
        self.assertEqual(ctxt.environment.call.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @mock.patch.object(timid_github.time, 'sleep')
    def test_retries_exponential_sleep(self, mock_sleep):
        ctxt = self.make_ctxt(
            self.make_child(stdout=timid_github.SSH_ERROR, returncode=1),
            self.make_child(stderr=timid_github.SSH_ERROR, returncode=1),
            self.make_child(stdout=timid_github.SSH_ERROR, returncode=1),
            self.make_child(stderr=timid_github.SSH_ERROR, returncode=1),
            self.make_child(stdout=b'final success'),
        )

        result = timid_github._git(ctxt, 'spam', 'arg1', 'arg2',
                                   ssh_retries=5)

        self.assertEqual(result, b'final success')
        ctxt.environment.call.assert_has_calls([
            mock.call(['git', 'spam', 'arg1', 'arg2'], close_fds=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE),
            mock.call(['git', 'spam', 'arg1', 'arg2'], close_fds=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE),
            mock.call(['git', 'spam', 'arg1', 'arg2'], close_fds=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE),
            mock.call(['git', 'spam', 'arg1', 'arg2'], close_fds=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE),
            mock.call(['git', 'spam', 'arg1', 'arg2'], close_fds=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE),
        ])
        self.assertEqual(ctxt.environment.call.call_count, 5)
        mock_sleep.assert_has_calls([
            mock.call(1),
            mock.call(2),
            mock.call(4),
            mock.call(8),
        ])
        self.assertEqual(mock_sleep.call_count, 4)


class TestCloneAction(unittest.TestCase):
    @mock.patch.object(timid_github.timid.Action, '__init__',
                       return_value=None)
    def test_init(self, mock_init):
        result = timid_github.CloneAction('ctxt', 'ghe')

        self.assertEqual(result.ghe, 'ghe')
        mock_init.assert_called_once_with('ctxt', '__clone__', None, None)

    @mock.patch.object(timid_github.os, 'lstat',
                       side_effect=OSError(errno.ENOENT, 'no file'))
    @mock.patch.object(timid_github.os, 'remove')
    @mock.patch.object(timid_github.os.path, 'isdir', return_value=False)
    @mock.patch.object(timid_github.shutil, 'rmtree')
    @mock.patch.object(timid_github.stat, 'S_ISDIR', return_value=False)
    @mock.patch.object(timid_github.CloneAction, '_clone',
                       return_value='clone success')
    @mock.patch.object(timid_github.CloneAction, '_update',
                       return_value='update success')
    def test_call_base(self, mock_update, mock_clone, mock_S_ISDIR,
                       mock_rmtree, mock_isdir, mock_remove, mock_lstat):
        ghe = mock.Mock(repo_name='repo')
        ctxt = mock.Mock(**{
            'environment.cwd': '/work/dir',
        })
        obj = timid_github.CloneAction(ctxt, ghe)

        result = obj(ctxt)

        self.assertEqual(result, 'clone success')
        self.assertEqual(ctxt.environment.cwd, '/work/dir')
        mock_lstat.assert_called_once_with('/work/dir/repo')
        self.assertFalse(mock_S_ISDIR.called)
        self.assertFalse(mock_remove.called)
        self.assertFalse(mock_isdir.called)
        self.assertFalse(mock_rmtree.called)
        mock_clone.assert_called_once_with('/work/dir', '/work/dir/repo', ctxt)
        self.assertFalse(mock_update.called)

    @mock.patch.object(timid_github.os, 'lstat',
                       side_effect=OSError(errno.EAGAIN, 'again'))
    @mock.patch.object(timid_github.os, 'remove')
    @mock.patch.object(timid_github.os.path, 'isdir', return_value=False)
    @mock.patch.object(timid_github.shutil, 'rmtree')
    @mock.patch.object(timid_github.stat, 'S_ISDIR', return_value=False)
    @mock.patch.object(timid_github.CloneAction, '_clone',
                       return_value='clone success')
    @mock.patch.object(timid_github.CloneAction, '_update',
                       return_value='update success')
    def test_call_error(self, mock_update, mock_clone, mock_S_ISDIR,
                        mock_rmtree, mock_isdir, mock_remove, mock_lstat):
        ghe = mock.Mock(repo_name='repo')
        ctxt = mock.Mock(**{
            'environment.cwd': '/work/dir',
        })
        obj = timid_github.CloneAction(ctxt, ghe)

        self.assertRaises(OSError, obj, ctxt)
        self.assertEqual(ctxt.environment.cwd, '/work/dir')
        mock_lstat.assert_called_once_with('/work/dir/repo')
        self.assertFalse(mock_S_ISDIR.called)
        self.assertFalse(mock_remove.called)
        self.assertFalse(mock_isdir.called)
        self.assertFalse(mock_rmtree.called)
        self.assertFalse(mock_clone.called)
        self.assertFalse(mock_update.called)

    @mock.patch.object(timid_github.os, 'lstat',
                       return_value=mock.Mock(st_mode='mode'))
    @mock.patch.object(timid_github.os, 'remove')
    @mock.patch.object(timid_github.os.path, 'isdir', return_value=False)
    @mock.patch.object(timid_github.shutil, 'rmtree')
    @mock.patch.object(timid_github.stat, 'S_ISDIR', return_value=False)
    @mock.patch.object(timid_github.CloneAction, '_clone',
                       return_value='clone success')
    @mock.patch.object(timid_github.CloneAction, '_update',
                       return_value='update success')
    def test_call_non_dir(self, mock_update, mock_clone, mock_S_ISDIR,
                          mock_rmtree, mock_isdir, mock_remove, mock_lstat):
        ghe = mock.Mock(repo_name='repo')
        ctxt = mock.Mock(**{
            'environment.cwd': '/work/dir',
        })
        obj = timid_github.CloneAction(ctxt, ghe)

        result = obj(ctxt)

        self.assertEqual(result, 'clone success')
        self.assertEqual(ctxt.environment.cwd, '/work/dir')
        mock_lstat.assert_called_once_with('/work/dir/repo')
        mock_S_ISDIR.assert_called_once_with('mode')
        mock_remove.assert_called_once_with('/work/dir/repo')
        self.assertFalse(mock_isdir.called)
        self.assertFalse(mock_rmtree.called)
        mock_clone.assert_called_once_with('/work/dir', '/work/dir/repo', ctxt)
        self.assertFalse(mock_update.called)

    @mock.patch.object(timid_github.os, 'lstat',
                       return_value=mock.Mock(st_mode='mode'))
    @mock.patch.object(timid_github.os, 'remove')
    @mock.patch.object(timid_github.os.path, 'isdir', return_value=True)
    @mock.patch.object(timid_github.shutil, 'rmtree')
    @mock.patch.object(timid_github.stat, 'S_ISDIR', return_value=True)
    @mock.patch.object(timid_github.CloneAction, '_clone',
                       return_value='clone success')
    @mock.patch.object(timid_github.CloneAction, '_update',
                       return_value='update success')
    def test_call_git_dir(self, mock_update, mock_clone, mock_S_ISDIR,
                          mock_rmtree, mock_isdir, mock_remove, mock_lstat):
        ghe = mock.Mock(repo_name='repo')
        ctxt = mock.Mock(**{
            'environment.cwd': '/work/dir',
        })
        obj = timid_github.CloneAction(ctxt, ghe)

        result = obj(ctxt)

        self.assertEqual(result, 'update success')
        self.assertEqual(ctxt.environment.cwd, '/work/dir/repo')
        mock_lstat.assert_called_once_with('/work/dir/repo')
        mock_S_ISDIR.assert_called_once_with('mode')
        self.assertFalse(mock_remove.called)
        mock_isdir.assert_called_once_with('/work/dir/repo/.git')
        self.assertFalse(mock_rmtree.called)
        self.assertFalse(mock_clone.called)
        mock_update.assert_called_once_with(ctxt)

    @mock.patch.object(timid_github.os, 'lstat',
                       return_value=mock.Mock(st_mode='mode'))
    @mock.patch.object(timid_github.os, 'remove')
    @mock.patch.object(timid_github.os.path, 'isdir', return_value=False)
    @mock.patch.object(timid_github.shutil, 'rmtree')
    @mock.patch.object(timid_github.stat, 'S_ISDIR', return_value=True)
    @mock.patch.object(timid_github.CloneAction, '_clone',
                       return_value='clone success')
    @mock.patch.object(timid_github.CloneAction, '_update',
                       return_value='update success')
    def test_call_nongit_dir(self, mock_update, mock_clone, mock_S_ISDIR,
                             mock_rmtree, mock_isdir, mock_remove, mock_lstat):
        ghe = mock.Mock(repo_name='repo')
        ctxt = mock.Mock(**{
            'environment.cwd': '/work/dir',
        })
        obj = timid_github.CloneAction(ctxt, ghe)

        result = obj(ctxt)

        self.assertEqual(result, 'clone success')
        self.assertEqual(ctxt.environment.cwd, '/work/dir')
        mock_lstat.assert_called_once_with('/work/dir/repo')
        mock_S_ISDIR.assert_called_once_with('mode')
        self.assertFalse(mock_remove.called)
        mock_isdir.assert_called_once_with('/work/dir/repo/.git')
        mock_rmtree.assert_called_once_with('/work/dir/repo')
        mock_clone.assert_called_once_with('/work/dir', '/work/dir/repo', ctxt)
        self.assertFalse(mock_update.called)

    @mock.patch.object(timid_github.os, 'lstat',
                       return_value=mock.Mock(st_mode='mode'))
    @mock.patch.object(timid_github.os, 'remove')
    @mock.patch.object(timid_github.os.path, 'isdir', return_value=True)
    @mock.patch.object(timid_github.shutil, 'rmtree')
    @mock.patch.object(timid_github.stat, 'S_ISDIR', return_value=True)
    @mock.patch.object(timid_github.CloneAction, '_clone',
                       return_value='clone success')
    @mock.patch.object(timid_github.CloneAction, '_update',
                       side_effect=TestException('bah'))
    def test_call_git_dir_failed_update(self, mock_update, mock_clone,
                                        mock_S_ISDIR, mock_rmtree, mock_isdir,
                                        mock_remove, mock_lstat):
        ghe = mock.Mock(repo_name='repo')
        ctxt = mock.Mock(**{
            'environment.cwd': '/work/dir',
        })
        obj = timid_github.CloneAction(ctxt, ghe)

        result = obj(ctxt)

        self.assertEqual(result, 'clone success')
        self.assertEqual(ctxt.environment.cwd, '/work/dir')
        mock_lstat.assert_called_once_with('/work/dir/repo')
        mock_S_ISDIR.assert_called_once_with('mode')
        self.assertFalse(mock_remove.called)
        mock_isdir.assert_called_once_with('/work/dir/repo/.git')
        mock_rmtree.assert_called_once_with('/work/dir/repo')
        mock_clone.assert_called_once_with('/work/dir', '/work/dir/repo', ctxt)
        mock_update.assert_called_once_with(ctxt)

    @mock.patch.object(timid_github, '_git')
    @mock.patch.object(timid_github.CloneAction, '_update',
                       return_value='update success')
    def test_clone_base(self, mock_update, mock_git):
        ghe = mock.Mock(repo_url='repo://url')
        ctxt = mock.Mock(**{
            'environment.cwd': '/work/dir',
        })
        obj = timid_github.CloneAction(ctxt, ghe)

        result = obj._clone('/work/dir', '/work/dir/repo', ctxt)

        self.assertEqual(result, 'update success')
        self.assertEqual(ctxt.environment.cwd, '/work/dir/repo')
        mock_git.assert_called_once_with(
            ctxt, 'clone', 'repo://url', '/work/dir/repo', ssh_retries=5)
        mock_update.assert_called_once_with(ctxt)

    @mock.patch.object(timid_github, '_git')
    @mock.patch.object(timid_github.CloneAction, '_update',
                       side_effect=TestException('bah'))
    def test_clone_error(self, mock_update, mock_git):
        ghe = mock.Mock(repo_url='repo://url')
        ctxt = mock.Mock(**{
            'environment.cwd': '/work/dir',
        })
        obj = timid_github.CloneAction(ctxt, ghe)

        self.assertRaises(TestException, obj._clone,
                          '/work/dir', '/work/dir/repo', ctxt)
        self.assertEqual(ctxt.environment.cwd, '/work/dir')
        mock_git.assert_called_once_with(
            ctxt, 'clone', 'repo://url', '/work/dir/repo', ssh_retries=5)
        mock_update.assert_called_once_with(ctxt)

    @mock.patch.object(timid_github, '_git')
    @mock.patch.object(timid_github.timid, 'StepResult', return_value='result')
    def test_update(self, mock_StepResult, mock_git):
        ghe = mock.Mock(repo_url='repo://url', repo_branch='branch')
        obj = timid_github.CloneAction('ctxt', ghe)

        result = obj._update('ctxt')

        self.assertEqual(result, 'result')
        mock_git.assert_has_calls([
            mock.call('ctxt', 'remote', 'set-url', 'origin', 'repo://url'),
            mock.call('ctxt', 'rebase', '--abort', do_raise=False),
            mock.call('ctxt', 'checkout', '-f', 'branch'),
            mock.call('ctxt', 'reset', '--hard', 'origin/branch'),
            mock.call('ctxt', 'clean', '-fdx'),
            mock.call('ctxt', 'fetch', 'origin', 'branch', ssh_retries=5),
            mock.call('ctxt', 'checkout', 'branch'),
        ])
        self.assertEqual(mock_git.call_count, 7)
        mock_StepResult.assert_called_once_with(status=timid.SUCCESS)


class TestMergeAction(unittest.TestCase):
    @mock.patch.object(timid_github.timid.Action, '__init__',
                       return_value=None)
    def test_init(self, mock_init):
        result = timid_github.MergeAction('ctxt', 'ghe')

        self.assertEqual(result.ghe, 'ghe')
        mock_init.assert_called_once_with('ctxt', '__merge__', None, None)

    @mock.patch.object(timid_github, '_git')
    @mock.patch.object(timid_github.timid, 'StepResult', return_value='result')
    def test_call(self, mock_StepResult, mock_git):
        ghe = mock.Mock(**{
            'pull.user.login': 'user-login',
            'repo_branch': 'repo-branch',
            'change_url': 'https://change/repo',
            'change_branch': 'change-branch',
        })
        obj = timid_github.MergeAction('ctxt', ghe)

        result = obj('ctxt')

        self.assertEqual(result, 'result')
        mock_git.assert_has_calls([
            mock.call('ctxt', 'branch', '-D', 'user-login-change-branch',
                      do_raise=False),
            mock.call('ctxt', 'checkout', '-b', 'user-login-change-branch',
                      'repo-branch'),
            mock.call('ctxt', 'pull', 'https://change/repo', 'change-branch'),
            mock.call('ctxt', 'checkout', 'repo-branch'),
            mock.call('ctxt', 'merge', 'user-login-change-branch'),
        ])
        self.assertEqual(mock_git.call_count, 5)
        mock_StepResult.assert_called_once_with(status=timid.SUCCESS)


class TestSelectUrl(unittest.TestCase):
    def test_from_repo(self):
        repo = mock.Mock(**dict((v, '%s url' % k) for k, v in
                                timid_github.URL_ATTR.items()))

        for url in timid_github.URL_ATTR.keys():
            result = timid_github._select_url(url, repo)

            self.assertEqual(result, '%s url' % url)

    def test_verbatim(self):
        repo = mock.Mock()

        result = timid_github._select_url('foo://url', repo)

        self.assertEqual(result, 'foo://url')


class TestGithubExtension(unittest.TestCase):
    @mock.patch.dict(timid_github.os.environ, clear=True)
    @mock.patch.object(timid_github.getpass, 'getuser', return_value='user')
    def test_prepare_noenviron(self, mock_getuser):
        parser = mock.Mock()
        group = parser.add_argument_group.return_value

        timid_github.GithubExtension.prepare(parser)

        parser.add_argument_group.assert_called_once_with(
            'Github Integration', 'Options for integrating with Github.')
        group.add_argument.assert_has_calls([
            mock.call('--github-api', default='https://api.github.com',
                      help=mock.ANY),
            mock.call('--github-user', default='user', help=mock.ANY),
            mock.call('--github-pass', default=None, help=mock.ANY),
            mock.call('--github-keyring-set', default=False,
                      action='store_true', help=mock.ANY),
            mock.call('--github-pull', help=mock.ANY),
            mock.call('--github-repo', default='git', help=mock.ANY),
            mock.call('--github-change-repo', help=mock.ANY),
            mock.call('--github-status-url', help=mock.ANY),
            mock.call('--github-override', help=mock.ANY),
            mock.call('--github-override-status',
                      choices=['pending', 'error', 'failure'], help=mock.ANY),
            mock.call('--github-override-text', help=mock.ANY),
            mock.call('--github-override-url', help=mock.ANY),
        ])

    @mock.patch.dict(timid_github.os.environ, clear=True,
                     TIMID_GITHUB_API='https://example.com/api',
                     TIMID_GITHUB_USER='alt_user',
                     TIMID_GITHUB_PASS='passwd')
    @mock.patch.object(timid_github.getpass, 'getuser', return_value='user')
    def test_prepare_withenviron(self, mock_getuser):
        parser = mock.Mock()
        group = parser.add_argument_group.return_value

        timid_github.GithubExtension.prepare(parser)

        parser.add_argument_group.assert_called_once_with(
            'Github Integration', 'Options for integrating with Github.')
        group.add_argument.assert_has_calls([
            mock.call('--github-api', default='https://example.com/api',
                      help=mock.ANY),
            mock.call('--github-user', default='alt_user', help=mock.ANY),
            mock.call('--github-pass', default='passwd', help=mock.ANY),
            mock.call('--github-keyring-set', default=False,
                      action='store_true', help=mock.ANY),
            mock.call('--github-pull', help=mock.ANY),
            mock.call('--github-repo', default='git', help=mock.ANY),
            mock.call('--github-change-repo', help=mock.ANY),
            mock.call('--github-status-url', help=mock.ANY),
            mock.call('--github-override', help=mock.ANY),
            mock.call('--github-override-status',
                      choices=['pending', 'error', 'failure'], help=mock.ANY),
            mock.call('--github-override-text', help=mock.ANY),
            mock.call('--github-override-url', help=mock.ANY),
        ])

    def make_pull(self, mock_Github, number=1, repo_name='repo',
                  full_name='some/repo',
                  repo_url='repo-url', repo_branch='branch',
                  change_url='change-repo-url', change_branch='change-branch'):
        # Create the pull object
        last_commit = mock.Mock()
        pull = mock.Mock(**{
            'base.repo.full_name': 'some/repo',
            'base.repo.name': repo_name,
            'base.repo.url': repo_url,
            'base.ref': repo_branch,
            'head.repo.url': change_url,
            'head.ref': change_branch,
            'number': 5,
            '_last_commit': last_commit,
            'get_commits.return_value': [0, 1, 2, last_commit],
        })

        # Attach it to the right places
        obj = mock_Github.return_value
        obj.get_repo.return_value.get_pull.return_value = pull
        obj.create_from_raw_data.return_value = pull

        return pull

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_base(self, mock_init, mock_select_url, mock_set_password,
                           mock_get_password, mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'Tests passed!',
                'github_success_url': None,
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'success',
                'text': 'Tests passed!',
                'url': None,
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_nopull(self, mock_init, mock_select_url,
                             mock_set_password, mock_get_password, mock_Github,
                             mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull=None,
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertEqual(result, None)
        self.assertFalse(mock_get_password.called)
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        self.assertFalse(mock_Github.called)
        self.assertFalse(mock_select_url.called)
        self.assertEqual(len(ctxt.variables.method_calls), 0)
        self.assertFalse(mock_init.called)

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_withpass(self, mock_init, mock_select_url,
                               mock_set_password, mock_get_password,
                               mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass='from_cli',
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        self.assertFalse(mock_get_password.called)
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_cli', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_cli',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'Tests passed!',
                'github_success_url': None,
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'success',
                'text': 'Tests passed!',
                'url': None,
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value=None)
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_nokeyring(self, mock_init, mock_select_url,
                                mock_set_password, mock_get_password,
                                mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        mock_getpass.assert_called_once_with(
            '[https://api.github.com] Password for "example"> ')
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyboard', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyboard',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'Tests passed!',
                'github_success_url': None,
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'success',
                'text': 'Tests passed!',
                'url': None,
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_set_keyring(self, mock_init, mock_select_url,
                                  mock_set_password, mock_get_password,
                                  mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=True,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        self.assertFalse(mock_get_password.called)
        mock_getpass.assert_called_once_with(
            '[https://api.github.com] Password for "example"> ')
        mock_set_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example', 'from_keyboard')
        mock_Github.assert_called_once_with(
            'example', 'from_keyboard', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyboard',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'Tests passed!',
                'github_success_url': None,
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'success',
                'text': 'Tests passed!',
                'url': None,
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_empty_pull_number(self, mock_init, mock_select_url,
                                        mock_set_password, mock_get_password,
                                        mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertEqual(result, None)
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        self.assertFalse(gh.get_repo.called)
        self.assertFalse(gh.get_repo.return_value.get_pull.called)
        self.assertFalse(gh.create_from_raw_data.called)
        self.assertFalse(mock_select_url.called)
        self.assertEqual(len(ctxt.variables.method_calls), 0)
        self.assertFalse(mock_init.called)

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_bad_pull_number(self, mock_init, mock_select_url,
                                      mock_set_password, mock_get_password,
                                      mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#x',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertEqual(result, None)
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        self.assertFalse(gh.get_repo.called)
        self.assertFalse(gh.get_repo.return_value.get_pull.called)
        self.assertFalse(gh.create_from_raw_data.called)
        self.assertFalse(mock_select_url.called)
        self.assertEqual(len(ctxt.variables.method_calls), 0)
        self.assertFalse(mock_init.called)

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_no_pull_object(self, mock_init, mock_select_url,
                                     mock_set_password, mock_get_password,
                                     mock_Github, mock_getpass):
        mock_Github.return_value.get_repo.side_effect = TestException()
        ctxt = mock.Mock()
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertEqual(result, None)
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        self.assertFalse(gh.get_repo.return_value.get_pull.called)
        self.assertFalse(gh.create_from_raw_data.called)
        self.assertFalse(mock_select_url.called)
        self.assertEqual(len(ctxt.variables.method_calls), 0)
        self.assertFalse(mock_init.called)

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_unqualified_repo(self, mock_init, mock_select_url,
                                       mock_set_password, mock_get_password,
                                       mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('example/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'Tests passed!',
                'github_success_url': None,
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'success',
                'text': 'Tests passed!',
                'url': None,
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_json_pull(self, mock_init, mock_select_url,
                                mock_set_password, mock_get_password,
                                mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull=json.dumps({'foo': 'bar'}),
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        self.assertFalse(gh.get_repo.called)
        self.assertFalse(gh.get_repo.return_value.get_pull.called)
        gh.create_from_raw_data.assert_called_once_with(
            github.PullRequest.PullRequest, {'foo': 'bar'})
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'Tests passed!',
                'github_success_url': None,
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'success',
                'text': 'Tests passed!',
                'url': None,
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_alternate_change_repo(self, mock_init, mock_select_url,
                                            mock_set_password,
                                            mock_get_password, mock_Github,
                                            mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='ssh',
            github_change_repo='https',
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('ssh', pull.base.repo),
            mock.call('https', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'Tests passed!',
                'github_success_url': None,
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'success',
                'text': 'Tests passed!',
                'url': None,
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_override_compat(self, mock_init, mock_select_url,
                                      mock_set_password, mock_get_password,
                                      mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=json.dumps({
                'status': 'override',
                'text': 'some text',
                'url': 'some url',
                'other': 'skipped',
            }),
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'override',
                'github_success_text': 'some text',
                'github_success_url': 'some url',
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'override',
                'text': 'some text',
                'url': 'some url',
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_override_compat_missing_key(self, mock_init,
                                                  mock_select_url,
                                                  mock_set_password,
                                                  mock_get_password,
                                                  mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=json.dumps({
                'status': 'override',
                'url': 'some url',
                'other': 'skipped',
            }),
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'override',
                'github_success_text': 'Tests passed!',
                'github_success_url': 'some url',
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'override',
                'text': 'Tests passed!',
                'url': 'some url',
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_override_compat_invalid(self, mock_init, mock_select_url,
                                              mock_set_password,
                                              mock_get_password, mock_Github,
                                              mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override='invalid',
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'Tests passed!',
                'github_success_url': None,
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'success',
                'text': 'Tests passed!',
                'url': None,
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_override_status(self, mock_init, mock_select_url,
                                      mock_set_password, mock_get_password,
                                      mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status='status',
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'status',
                'github_success_text': 'Tests passed!',
                'github_success_url': None,
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'status',
                'text': 'Tests passed!',
                'url': None,
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_override_text(self, mock_init, mock_select_url,
                                    mock_set_password, mock_get_password,
                                    mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text='text',
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'text',
                'github_success_url': None,
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'success',
                'text': 'text',
                'url': None,
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_override_url(self, mock_init, mock_select_url,
                                   mock_set_password, mock_get_password,
                                   mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url='url',
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'Tests passed!',
                'github_success_url': 'url',
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'success',
                'text': 'Tests passed!',
                'url': 'url',
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_override_compat_precedence(self, mock_init,
                                                 mock_select_url,
                                                 mock_set_password,
                                                 mock_get_password,
                                                 mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url=None,
            github_override=json.dumps({
                'status': 'override',
                'text': 'some text',
                'url': 'some url',
                'other': 'skipped',
            }),
            github_override_status='status',
            github_override_text='text',
            github_override_url='url',
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'status',
                'github_success_text': 'text',
                'github_success_url': 'url',
                'github_status_url': None,
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, None, {
                'status': 'status',
                'text': 'text',
                'url': 'url',
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    @mock.patch.object(timid_github.getpass, 'getpass',
                       return_value='from_keyboard')
    @mock.patch.object(timid_github.github, 'Github')
    @mock.patch.object(timid_github.keyring, 'get_password',
                       return_value='from_keyring')
    @mock.patch.object(timid_github.keyring, 'set_password')
    @mock.patch.object(timid_github, '_select_url',
                       side_effect=lambda x, y: y.url)
    @mock.patch.object(timid_github.GithubExtension, '__init__',
                       return_value=None)
    def test_activate_status_url(self, mock_init, mock_select_url,
                                 mock_set_password, mock_get_password,
                                 mock_Github, mock_getpass):
        ctxt = mock.Mock()
        pull = self.make_pull(mock_Github)
        args = mock.Mock(
            github_pull='some/repo#5',
            github_api='https://api.github.com',
            github_user='example',
            github_pass=None,
            github_keyring_set=False,
            github_repo='https://example.com/repo',
            github_change_repo=None,
            github_status_url='https://status.example.com/',
            github_override=None,
            github_override_status=None,
            github_override_text=None,
            github_override_url=None,
        )

        result = timid_github.GithubExtension.activate(ctxt, args)

        self.assertTrue(isinstance(result, timid_github.GithubExtension))
        mock_get_password.assert_called_once_with(
            'timid-github!https://api.github.com', 'example')
        self.assertFalse(mock_getpass.called)
        self.assertFalse(mock_set_password.called)
        mock_Github.assert_called_once_with(
            'example', 'from_keyring', 'https://api.github.com')
        gh = mock_Github.return_value
        gh.get_repo.assert_called_once_with('some/repo')
        gh.get_repo.return_value.get_pull.assert_called_once_with(5)
        self.assertFalse(gh.create_from_raw_data.called)
        mock_select_url.assert_has_calls([
            mock.call('https://example.com/repo', pull.base.repo),
            mock.call('https://example.com/repo', pull.head.repo),
        ])
        self.assertEqual(mock_select_url.call_count, 2)
        ctxt.variables.assert_has_calls([
            mock.call.declare_sensitive('github_api_password'),
            mock.call.update({
                'github_api': 'https://api.github.com',
                'github_api_username': 'example',
                'github_api_password': 'from_keyring',
                'github_repo_name': 'repo',
                'github_pull': 'some/repo#5',
                'github_base_repo': 'repo-url',
                'github_base_branch': 'branch',
                'github_change_repo': 'change-repo-url',
                'github_change_branch': 'change-branch',
                'github_success_status': 'success',
                'github_success_text': 'Tests passed!',
                'github_success_url': 'https://status.example.com/',
                'github_status_url': 'https://status.example.com/',
            }),
        ])
        self.assertEqual(len(ctxt.variables.method_calls), 2)
        mock_init.assert_called_once_with(
            gh, pull, pull._last_commit, 'https://status.example.com/', {
                'status': 'success',
                'text': 'Tests passed!',
                'url': 'https://status.example.com/',
            }, 'repo', 'repo-url', 'branch',
            'change-repo-url', 'change-branch')

    def test_init(self):
        result = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        self.assertEqual(result.gh, 'gh')
        self.assertEqual(result.pull, 'pull')
        self.assertEqual(result.last_commit, 'last_commit')
        self.assertEqual(result.status_url, 'status_url')
        self.assertEqual(result.final_status, 'final_status')
        self.assertEqual(result.repo_name, 'repo_name')
        self.assertEqual(result.repo_url, 'repo_url')
        self.assertEqual(result.repo_branch, 'repo_branch')
        self.assertEqual(result.change_url, 'change_url')
        self.assertEqual(result.change_branch, 'change_branch')
        self.assertEqual(result.last_status, None)

    def test_set_status_base(self):
        last_commit = mock.Mock()
        obj = timid_github.GithubExtension(
            'gh', 'pull', last_commit, 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        obj._set_status('pending')

        self.assertEqual(obj.last_status, {
            'status': 'pending',
            'text': None,
            'url': None,
        })
        last_commit.create_status.assert_called_once_with(
            'pending', github.GithubObject.NotSet,
            github.GithubObject.NotSet)

    def test_set_status_alt(self):
        last_commit = mock.Mock()
        obj = timid_github.GithubExtension(
            'gh', 'pull', last_commit, 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        obj._set_status('pending', 'text', 'url')

        self.assertEqual(obj.last_status, {
            'status': 'pending',
            'text': 'text',
            'url': 'url',
        })
        last_commit.create_status.assert_called_once_with(
            'pending', 'url', 'text')

    @mock.patch.object(timid_github, 'CloneAction', return_value='clone')
    @mock.patch.object(timid_github, 'MergeAction', return_value='merge')
    @mock.patch.object(timid_github.timid, 'Step',
                       side_effect=lambda addr, action, name, description:
                       "%s#%s" % (addr, action))
    @mock.patch.object(timid_github.timid, 'StepAddress',
                       side_effect=lambda x, y: '%s:%s' % (x, y))
    def test_read_steps(self, mock_StepAddress, mock_Step, mock_MergeAction,
                        mock_CloneAction):
        fname = inspect.getsourcefile(timid_github.GithubExtension)
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')
        steps = ['step0', 'step1', 'step2']

        obj.read_steps('ctxt', steps)

        self.assertEqual(steps, [
            '%s:0#clone' % fname, '%s:1#merge' % fname,
            'step0', 'step1', 'step2',
        ])
        mock_CloneAction.assert_called_once_with('ctxt', obj)
        mock_MergeAction.assert_called_once_with('ctxt', obj)
        mock_StepAddress.assert_has_calls([
            mock.call(fname, 0),
            mock.call(fname, 1),
        ])
        self.assertEqual(mock_StepAddress.call_count, 2)
        mock_Step.assert_has_calls([
            mock.call('%s:0' % fname, 'clone', name='Cloning repository',
                      description='Clone the Github repository'),
            mock.call('%s:1' % fname, 'merge', name='Merging pull request',
                      description='Merge the Github pull request'),
        ])
        self.assertEqual(mock_Step.call_count, 2)

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_pre_step(self, mock_set_status):
        step = mock.Mock()
        step.name = 'Step'
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        result = obj.pre_step('ctxt', step, 5)

        self.assertEqual(result, None)
        mock_set_status.assert_called_once_with(
            'pending', 'Step', 'status_url')

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_post_step_skipped(self, mock_set_status):
        step = mock.Mock()
        step.name = 'Step'
        result = timid.StepResult(state=timid.SKIPPED)
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        obj.post_step('ctxt', step, 5, result)

        self.assertFalse(mock_set_status.called)

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_post_step_success(self, mock_set_status):
        step = mock.Mock()
        step.name = 'Step'
        result = timid.StepResult(state=timid.SUCCESS)
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        obj.post_step('ctxt', step, 5, result)

        self.assertFalse(mock_set_status.called)

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_post_step_failure_nomsg(self, mock_set_status):
        step = mock.Mock()
        step.name = 'Step'
        result = timid.StepResult(state=timid.FAILURE)
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        obj.post_step('ctxt', step, 5, result)

        mock_set_status.assert_called_once_with(
            'failure', 'Failed: Step', 'status_url')

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_post_step_failure_withmsg(self, mock_set_status):
        step = mock.Mock()
        step.name = 'Step'
        result = timid.StepResult(state=timid.FAILURE, msg='message')
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        obj.post_step('ctxt', step, 5, result)

        mock_set_status.assert_called_once_with(
            'failure', 'message', 'status_url')

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_post_step_error_nomsg(self, mock_set_status):
        step = mock.Mock()
        step.name = 'Step'
        result = timid.StepResult(state=timid.ERROR)
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        obj.post_step('ctxt', step, 5, result)

        mock_set_status.assert_called_once_with(
            'error', 'Error: Step', 'status_url')

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_post_step_error_withmsg(self, mock_set_status):
        step = mock.Mock()
        step.name = 'Step'
        result = timid.StepResult(state=timid.ERROR, msg='message')
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        obj.post_step('ctxt', step, 5, result)

        mock_set_status.assert_called_once_with(
            'error', 'message', 'status_url')

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_post_step_other_nomsg(self, mock_set_status):
        step = mock.Mock()
        step.name = 'Step'
        result = timid.StepResult(state=5)
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        obj.post_step('ctxt', step, 5, result)

        mock_set_status.assert_called_once_with(
            'error', 'Unknown timid state "5" during step: Step',
            'status_url')

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_post_step_other_withmsg(self, mock_set_status):
        step = mock.Mock()
        step.name = 'Step'
        result = timid.StepResult(state='other', msg='message')
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', 'final_status',
            'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        obj.post_step('ctxt', step, 5, result)

        mock_set_status.assert_called_once_with(
            'error', 'message', 'status_url')

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_finalize_none(self, mock_set_status):
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', {
                'status': 'success',
                'text': 'Tests passed!',
                'url': 'https://example.com',
            }, 'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        result = obj.finalize('ctxt', None)

        self.assertEqual(result, None)
        mock_set_status.assert_called_once_with(
            status='success', text='Tests passed!', url='https://example.com')

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_finalize_exception(self, mock_set_status):
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', {
                'status': 'success',
                'text': 'Tests passed!',
                'url': 'https://example.com',
            }, 'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')
        exc = TestException('some failure')

        result = obj.finalize('ctxt', exc)

        self.assertEqual(result, exc)
        mock_set_status.assert_called_once_with(
            'error', 'Exception while running timid: some failure',
            'status_url')

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_finalize_string_no_last_status(self, mock_set_status):
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', {
                'status': 'success',
                'text': 'Tests passed!',
                'url': 'https://example.com',
            }, 'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')

        result = obj.finalize('ctxt', 'text')

        self.assertEqual(result, 'text')
        self.assertFalse(mock_set_status.called)

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_finalize_string_with_last_status_other(self, mock_set_status):
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', {
                'status': 'success',
                'text': 'Tests passed!',
                'url': 'https://example.com',
            }, 'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')
        obj.last_status = {
            'status': 'other',
        }

        result = obj.finalize('ctxt', 'text')

        self.assertEqual(result, 'text')
        self.assertFalse(mock_set_status.called)

    @mock.patch.object(timid_github.GithubExtension, '_set_status')
    def test_finalize_string_with_last_status_pending(self, mock_set_status):
        obj = timid_github.GithubExtension(
            'gh', 'pull', 'last_commit', 'status_url', {
                'status': 'success',
                'text': 'Tests passed!',
                'url': 'https://example.com',
            }, 'repo_name', 'repo_url', 'repo_branch',
            'change_url', 'change_branch')
        obj.last_status = {
            'status': 'pending',
        }

        result = obj.finalize('ctxt', 'text')

        self.assertEqual(result, 'text')
        mock_set_status.assert_called_once_with(
            'failure', 'Testing failed: text', 'status_url')
