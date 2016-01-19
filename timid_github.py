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
import getpass
import inspect
import json
import os
import shutil
import stat
import subprocess
import sys
import time

import github
import keyring
import six
import timid


SSH_ERROR = b'ssh_exchange_identification: Connection closed by remote host'


class GitException(Exception):
    """
    An exception to be thrown in the event of an error observed while
    executing the "git" command.
    """

    pass


def _git(ctxt, *args, **kwargs):
    """
    Invoke a "git" subcommand.

    :param ctxt: The context object.
    :param args: Positional arguments, specified as strings; the first
                 must be a "git" subcommand, and remaining arguments
                 will be passed to that subcommand.
    :param ssh_retries: A keyword-only parameter specifying the number
                        of retries to attempt.  If the command fails
                        due to an SSH error, the command will be
                        retried up to this many times.  This does not
                        impact failures due to other connection
                        errors.  Defaults to ``1``.
    :param do_raise: A keyword-only parameter specifying whether to
                     raise exceptions in the event of command
                     failures.  If ``False``, no exception will be
                     raised.  Defaults to ``True``.

    :returns: The contents of standard output.
    """

    # Extract keyword-only parameters
    ssh_retries = kwargs.get('ssh_retries', 1)
    do_raise = kwargs.get('do_raise', True)

    # Construct the full command
    cmd = ['git']
    cmd.extend(args)

    # Loop the requisite number of times, with appropriate sleeps
    sleep_time = 1
    num_tries = 0
    while num_tries < ssh_retries:
        num_tries += 1
        if num_tries > 1:
            # Second or subsequent try; sleep with exponential backoff
            time.sleep(sleep_time)
            sleep_time <<= 1

        # Run the command
        child = ctxt.environment.call(
            cmd, close_fds=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = child.communicate()

        # Do we need to retry?
        if child.returncode and (SSH_ERROR in stdout or SSH_ERROR in stderr):
            continue

        # We have executed it!
        break

    if do_raise and child.returncode:
        # Reconstitute the command
        command = ' '.join(six.moves.shlex_quote(c) for c in cmd)
        raise GitException('Git command "%s" returned %d' %
                           (command, child.returncode))

    # Return the standard output
    return stdout


class CloneAction(timid.Action):
    """
    A Timid action that will clone the target repository.  The
    repository will be cloned into the working directory.  This action
    cannot appear in the test description, as it is implicitly added
    by the ``GithubExtension`` extension.
    """

    schema = None

    def __init__(self, ctxt, ghe):
        """
        Initialize a ``CloneAction`` instance.

        :param ghe: An instance of ``GithubExtension``.
        """

        # Initialize the superclass
        super(CloneAction, self).__init__(ctxt, '__clone__', None, None)

        # Store the github extension instance
        self.ghe = ghe

    def validate_conf(self, name, config, step_addr):
        """
        Validate configuration.  This action does not take a
        configuration, so the ``validate_conf()`` method is overridden
        to inhibit validation.

        :param name: The name of the action or modifier.
        :param config: The actual configuration.
        :param step_addr: The address of the step in the test
                          configuration.
        """

        pass  # pragma: no cover

    def __call__(self, ctxt):
        """
        Invoke the action.  This method will clone the repository into the
        correct directory, then switch to that directory.

        :param ctxt: The context object.

        :returns: A ``StepResult`` object.
        """

        # First step, see if the repository exists
        work_dir = ctxt.environment.cwd
        repo_dir = os.path.join(work_dir, self.ghe.repo_name)
        try:
            dir_data = os.lstat(repo_dir)
        except OSError as e:
            # Re-raise the error if it's not ENOENT
            if e.errno != errno.ENOENT:
                raise

            # OK, safe to clone from scratch
            return self._clone(work_dir, repo_dir, ctxt)

        # Hmmm, the file exists; is it a directory?
        if not stat.S_ISDIR(dir_data.st_mode):
            # OK, we control the workdir, so delete the extraneous
            # file and clone from scratch
            os.remove(repo_dir)
            return self._clone(work_dir, repo_dir, ctxt)

        # It's a directory; is it a repository?
        if os.path.isdir(os.path.join(repo_dir, '.git')):
            # Try updating the base branch
            try:
                ctxt.environment.cwd = repo_dir
                return self._update(ctxt)
            except Exception:
                # Failed to update, so back out of the directory
                # temporarily
                ctxt.environment.cwd = work_dir

        # Not a repository, or couldn't update; blow it away and try
        # cloning from scratch
        shutil.rmtree(repo_dir)
        return self._clone(work_dir, repo_dir, ctxt)

    def _clone(self, work_dir, target_dir, ctxt):
        """
        Clones the base repository into the specified target directory.

        :param work_dir: The current working directory.  This is used
                         to restore the environment working directory
                         in the event that the later call to
                         ``self._update()`` fails.
        :param target_dir: The directory into which the repository
                           should be checked out.
        :param ctxt: The context object.
        """

        # Begin by cloning the repository
        _git(ctxt, 'clone', self.ghe.repo_url, target_dir, ssh_retries=5)

        # Change to the target directory and fetch any changes
        try:
            ctxt.environment.cwd = target_dir
            return self._update(ctxt)
        except Exception:
            exc_info = sys.exc_info()

            # Reset the directory
            ctxt.environment.cwd = work_dir

            # Re-raise the exception
            six.reraise(*exc_info)

    def _update(self, ctxt):
        """
        Updates the repository, assumed to be the current working
        directory, from the specified base repository.

        :param ctxt: The context object.

        :returns: A ``timid.StepResult`` object.
        """

        # Ensure the remote is set properly
        _git(ctxt, 'remote', 'set-url', 'origin', self.ghe.repo_url)

        # Do some initial resets
        _git(ctxt, 'rebase', '--abort', do_raise=False)
        _git(ctxt, 'checkout', '-f', self.ghe.repo_branch)
        _git(ctxt, 'reset', '--hard', 'origin/%s' % self.ghe.repo_branch)
        _git(ctxt, 'clean', '-fdx')

        # And check out the designated branch
        _git(ctxt, 'fetch', 'origin', self.ghe.repo_branch, ssh_retries=5)
        _git(ctxt, 'checkout', self.ghe.repo_branch)

        return timid.StepResult(state=timid.SUCCESS)


class MergeAction(timid.Action):
    """
    A Timid action that will prepare a repository by creating and
    checking out a topic branch and merging the pull request into that
    branch.  This action cannot appear in the test description, as it
    is implicitly added by the ``GithubExtension`` extension.
    """

    schema = None

    def __init__(self, ctxt, ghe):
        """
        Initialize a ``MergeAction`` instance.

        :param ghe: An instance of ``GithubExtension``.
        """

        # Initialize the superclass
        super(MergeAction, self).__init__(ctxt, '__merge__', None, None)

        # Store the github extension instance
        self.ghe = ghe

    def validate_conf(self, name, config, step_addr):
        """
        Validate configuration.  This action does not take a
        configuration, so the ``validate_conf()`` method is overridden
        to inhibit validation.

        :param name: The name of the action or modifier.
        :param config: The actual configuration.
        :param step_addr: The address of the step in the test
                          configuration.
        """

        pass  # pragma: no cover

    def __call__(self, ctxt):
        """
        Invoke the action.  This method will create the appropriate branch
        and merge the pull request into it.

        :param ctxt: The context object.

        :returns: A ``StepResult`` object.
        """

        # Compute a branch name
        local_branch = ('%s-%s' %
                        (self.ghe.pull.user.login, self.ghe.change_branch))

        # Make sure the branch doesn't already exist
        _git(ctxt, 'branch', '-D', local_branch, do_raise=False)

        # Create the branch
        _git(ctxt, 'checkout', '-b', local_branch, self.ghe.repo_branch)

        # Merge the change
        _git(ctxt, 'pull', self.ghe.change_url, self.ghe.change_branch)
        _git(ctxt, 'checkout', self.ghe.repo_branch)
        _git(ctxt, 'merge', local_branch)

        return timid.StepResult(state=timid.SUCCESS)


# A mapping of URL string to the attribute of the repository object
# containing the desired URL.
URL_ATTR = {
    'ssh': 'ssh_url',
    'git': 'git_url',
    'https': 'clone_url',
}


def _select_url(repo_url, repo_obj):
    """
    Select the appropriate repository URL.

    :param repo_url: The URL to select.  May be "ssh", "git", or
                     "https" to select the appropriate URL from the
                     ``repo_obj``, or may be a verbatim repository
                     URL.
    :param repo_obj: An instance of ``github.Repository.Repository``.

    :returns: The appropriate repository URL.
    """

    # If it's one of the defined ones, return the appropriate
    # attribute
    if repo_url in URL_ATTR:
        return getattr(repo_obj, URL_ATTR[repo_url])

    # Verbatim URL; return it unchanged
    return repo_url


class GithubExtension(timid.Extension):
    """
    A Timid extension that provides integration with Github.  This
    will allow a pull request to be tested directly by Timid.  Testing
    includes making status updates to the pull request for each step
    in the testing procedure, with a final "success" or "failure"
    status at the conclusion of testing, with an optional override for
    "success" status.
    """

    priority = 50

    @classmethod
    def prepare(cls, parser):
        """
        Called to prepare the extension.  The extension is prepared during
        argument parser preparation.  An extension implementing this
        method is able to add command line arguments specific for that
        extension.  Note that this is a class method; the extension
        will not be instantiated prior to calling this method, nor
        should this method attempt to initialize the extension.

        :param parser: The argument parser, an instance of
                       ``argparse.ArgumentParser``.
        """

        # Begin by grouping the extension arguments
        group = parser.add_argument_group(
            'Github Integration', 'Options for integrating with Github.',
        )

        # Authentication options
        group.add_argument(
            '--github-api',
            default=os.environ.get('TIMID_GITHUB_API',
                                   'https://api.github.com'),
            help='Designate the Github API for the instance of Github to '
            'search for the pull request.  Default is drawn from the '
            '"TIMID_GITHUB_API" environment variable.  Default: %(default)s',
        )
        group.add_argument(
            '--github-user',
            default=os.environ.get('TIMID_GITHUB_USER', getpass.getuser()),
            help='Designate the username to use to authenticate to the '
            'Github API.  Default is drawn from the "TIMID_GITHUB_USER" '
            'environment variable.  Default: %(default)s',
        )
        group.add_argument(
            '--github-pass',
            default=os.environ.get('TIMID_GITHUB_PASS'),
            help='Designate the password to use to authenticate to the '
            'Github API.  If not provided, and not available from the '
            'keyring, will be prompted for.',
        )
        group.add_argument(
            '--github-keyring-set',
            default=False,
            action='store_true',
            help='Enable setting the password in the keyring.  The entry '
            'will be keyed by the Github API URL and by the username.',
        )

        # The pull request to test
        group.add_argument(
            '--github-pull',
            help='Designate the pull request to test.  This may be the '
            'repository name and pull request number (e.g., "repo#1" or '
            '"org/repo#1"), or a JSON object describing the pull request '
            '(deprecated usage).  This is the only option that enables the '
            'Github extension.',
        )

        # The repository to pull from
        group.add_argument(
            '--github-repo',
            default='git',
            help='Designate the repository URL to clone from.  This may '
            'be the full URL to the repository, or it may be one of the '
            'tokens "ssh", "git", or "https", designating to use the '
            'specified access method from the repository specified in the '
            'Github pull request.  Default: %(default)s.',
        )

        # The repository to pull from
        group.add_argument(
            '--github-change-repo',
            help='Designate the repository URL to merge the pull request '
            'from.  This may be the full URL to the repository, or it may '
            'be one of the tokens "ssh", "git", or "https", designating to '
            'use the specified access method from the repository specified '
            'in the Github pull request.  Defaults to the same method as '
            'selected for --github-repo.',
        )

        # Some control options
        group.add_argument(
            '--github-status-url',
            help='A URL to include in status updates made on the pull '
            'request.  Optional.',
        )

        # Override options
        group.add_argument(
            '--github-override',
            help='DEPRECATED.  Accepts a JSON object describing the status '
            'to use in place of a successful status resulting from the test. '
            'The JSON object should be a dictionary containing the "status" '
            'key designating the final status (replaced by '
            '"--github-override-status").  Optionally, the "text" key '
            '(replaced by "--github-override-text") designates the status '
            'text, and the "url" key (replaced by "--github-override-url") '
            'designates the status URL.',
        )
        group.add_argument(
            '--github-override-status',
            choices=['pending', 'error', 'failure'],
            help='Specifies an alternate status to use if tests complete '
            'successfully.  Must be "pending", "error", or "failure".  If '
            'used with "--github-override", this option takes precedence.',
        )
        group.add_argument(
            '--github-override-text',
            help='Specifies status text to include with the override '
            'status specified by "--github-override-status".  If used with '
            '"--github-override", this option takes precedence.',
        )
        group.add_argument(
            '--github-override-url',
            help='Specifies a status URL to include with the override '
            'status specified by "--github-override-status".  If used with '
            '"--github-override", this option takes precedence.',
        )

    @classmethod
    def activate(cls, ctxt, args):
        """
        Called to determine whether to activate the extension.  This call
        is made after processing command line arguments, and must
        return either ``None`` or an initialized instance of the
        extension.  Note that this is a class method.

        :param ctxt: An instance of ``timid.context.Context``.
        :param args: An instance of ``argparse.Namespace`` containing
                     the result of processing command line arguments.

        :returns: An instance of the extension class if the extension
                  has been activated, ``None`` if it has not.  If this
                  method returns ``None``, no further extension
                  methods will be called.
        """

        # If no pull request was specified, do nothing
        if not args.github_pull:
            return None

        # Ensure we have a password
        service = 'timid-github!%s' % args.github_api
        passwd = args.github_pass
        if passwd is None and not args.github_keyring_set:
            # Try getting it from the keyring
            passwd = keyring.get_password(service, args.github_user)
        if passwd is None:
            # OK, try prompting for it
            passwd = getpass.getpass('[%s] Password for "%s"> ' %
                                     (args.github_api, args.github_user))

        # Are we supposed to set it?
        if args.github_keyring_set:
            keyring.set_password(service, args.github_user, passwd)

        # Now we have authentication information, get a Github handle
        gh = github.Github(args.github_user, passwd, args.github_api)

        # Next, interpret the pull request designation
        try:
            # Try JSON first
            pull_raw = json.loads(args.github_pull)
        except ValueError:
            # Raw string
            repo, _sep, number = args.github_pull.partition('#')

            # Interpret the number
            if not number or not number.isdigit():
                return None
            number = int(number)

            # Interpret the repo
            if '/' not in repo:
                repo = '%s/%s' % (args.github_user, repo)

            # Look up the pull request
            try:
                repo = gh.get_repo(repo)
                pull = repo.get_pull(number)
            except Exception:
                # No such pull request, I guess
                return None
        else:
            # OK, we have raw JSON data; wrap it in a PullRequest
            pull = gh.create_from_raw_data(
                github.PullRequest.PullRequest, pull_raw)

        # Need the repository name
        repo_name = pull.base.repo.name

        # Also need the branches
        repo_branch = pull.base.ref
        change_branch = pull.head.ref

        # Select the correct repository URL
        repo_url = _select_url(args.github_repo, pull.base.repo)

        # Select the correct change repository URL.  If not
        # independently specified, default to the same as the
        # repo_url.  Note: the URLs could legally be the same, as a PR
        # could be made from one branch to another of the same
        # repository.
        change_url = _select_url(args.github_change_repo or args.github_repo,
                                 pull.head.repo)

        # With the pull, we need to select an appropriate commit
        last_commit = list(pull.get_commits())[-1]

        # Set up the final status information
        final_status = {
            'status': 'success',
            'text': 'Tests passed!',
            'url': args.github_status_url,
        }

        # Handle the --github-override option
        if args.github_override:
            try:
                override_raw = json.loads(args.github_override)
                for key in final_status:
                    if key in override_raw:
                        final_status[key] = override_raw[key]
            except ValueError:
                pass

        # Now we process the other override options
        if args.github_override_status:
            final_status['status'] = args.github_override_status
        if args.github_override_text:
            final_status['text'] = args.github_override_text
        if args.github_override_url:
            final_status['url'] = args.github_override_url

        # Set some variables in the context for the use of any callers
        ctxt.variables.declare_sensitive('github_api_password')
        ctxt.variables.update({
            'github_api': args.github_api,
            'github_api_username': args.github_user,
            'github_api_password': passwd,
            'github_repo_name': repo_name,
            'github_pull': '%s#%d' % (pull.base.repo.full_name, pull.number),
            'github_base_repo': repo_url,
            'github_base_branch': repo_branch,
            'github_change_repo': change_url,
            'github_change_branch': change_branch,
            'github_success_status': final_status['status'],
            'github_success_text': final_status['text'],
            'github_success_url': final_status['url'],
            'github_status_url': args.github_status_url,
        })

        # We are all set; initialize the extension
        return cls(gh, pull, last_commit, args.github_status_url, final_status,
                   repo_name, repo_url, repo_branch, change_url, change_branch)

    def __init__(self, gh, pull, last_commit, status_url, final_status,
                 repo_name, repo_url, repo_branch, change_url, change_branch):
        """
        Initialize the ``GithubExtension`` instance.

        :param gh: A ``github.Github`` object representing a handle
                   for interacting with the Github API.
        :param pull: A ``github.PullRequest.PullRequest`` object
                     describing the pull request being tested.
        :param last_commit: A ``github.Commit.Commit`` object
                            identifying the last commit contained in
                            the pull request.  This is used for
                            updating the pull request status.
        :param status_url: An optional status URL to include in the
                           status updates.  If none is provided, use
                           ``None``.
        :param final_status: A dictionary of three keys: "status",
                             "text", and "url".  This is used to set
                             the final status of the pull request
                             should tests pass.
        :param repo_name: The bare name of the repository, excluding
                          the organization or user name.
        :param repo_url: The repository URL to clone from.
        :param repo_branch: The branch of the repository into which to
                            merge the pull request.
        :param change_url: The repository URL of the repository
                           containing the pull request.
        :param change_branch: The branch of the change repository from
                              which to merge the pull request.
        """

        # Save the important data
        self.gh = gh
        self.pull = pull
        self.last_commit = last_commit
        self.status_url = status_url
        self.final_status = final_status
        self.repo_name = repo_name
        self.repo_url = repo_url
        self.repo_branch = repo_branch
        self.change_url = change_url
        self.change_branch = change_branch

        # Remember what the last status was
        self.last_status = None

    def _set_status(self, status, text=None, url=None):
        """
        A helper method to set the status of a pull request.

        :param status: The desired status.  Should be one of the
                       values "pending", "success", "failure", or
                       "error".
        :param text: An optional textual description of the status.
        :param url: An optional URL for the status.
        """

        # Set the status
        self.last_commit.create_status(
            status,
            url or github.GithubObject.NotSet,
            text or github.GithubObject.NotSet,
        )

        # Remember it so we only make calls we need to
        self.last_status = {
            'status': status,
            'text': text,
            'url': url,
        }

    def read_steps(self, ctxt, steps):
        """
        Called after reading steps, prior to adding them to the list of
        test steps.  This allows an extension to alter the list (in
        place).

        :param ctxt: An instance of ``timid.context.Context``.
        :param steps: A list of ``timid.steps.Step`` instances.
        """

        # Get our file name
        fname = inspect.getsourcefile(self.__class__)

        # Prepend our steps to the list of steps read
        steps[0:0] = [
            # First step will be to clone the repository
            timid.Step(timid.StepAddress(fname, 0),
                       CloneAction(ctxt, self),
                       name='Cloning repository',
                       description='Clone the Github repository'),

            # Second step will be to merge the pull request
            timid.Step(timid.StepAddress(fname, 1),
                       MergeAction(ctxt, self),
                       name='Merging pull request',
                       description='Merge the Github pull request'),
        ]

    def pre_step(self, ctxt, step, idx):
        """
        Called prior to executing a step.

        :param ctxt: An instance of ``timid.context.Context``.
        :param step: An instance of ``timid.steps.Step`` describing
                     the step to be executed.
        :param idx: The index of the step in the list of steps.

        :returns: A ``True`` value if the step is to be skipped.  Any
                  ``False`` value (including ``None``) will result in
                  the step being executed as normal.
        """

        # Update the pull request status
        self._set_status('pending', step.name, self.status_url)

        return None

    def post_step(self, ctxt, step, idx, result):
        """
        Called after executing a step.

        :param ctxt: An instance of ``timid.context.Context``.
        :param step: An instance of ``timid.steps.Step`` describing
                     the step that was executed.
        :param idx: The index of the step in the list of steps.
        :param result: An instance of ``timid.steps.StepResult``
                       describing the result of executing the step.
                       May be altered by the extension, e.g., to set
                       the ``ignore`` attribute.
        """

        if not result:
            # The step failed; compute a status update
            msg = result.msg
            if result.state == timid.FAILURE:
                status = 'failure'
                if not msg:
                    msg = 'Failed: %s' % step.name
            else:
                status = 'error'
                if not msg:
                    if result.state != timid.ERROR:
                        msg = ('Unknown timid state "%s" during step: %s' %
                               (result.state, step.name))
                    else:
                        msg = 'Error: %s' % step.name

            # Update the status
            self._set_status(status, msg, self.status_url)

    def finalize(self, ctxt, result):
        """
        Called at the end of processing.  This call allows the extension
        to emit any additional data, such as timing information, prior
        to ``timid``'s exit.  The extension may also alter the return
        value.

        :param ctxt: An instance of ``timid.context.Context``.
        :param result: The return value of the basic ``timid`` call,
                       or an ``Exception`` instance if an exception
                       was raised.  Without the extension, this would
                       be passed directly to ``sys.exit()``.

        :returns: Should return ``result`` unless the extension wishes
                  to change the return value.
        """

        # If result is None, update the status to success
        if result is None:
            self._set_status(**self.final_status)
        elif isinstance(result, Exception):
            # An exception occurred while running timid; log it as an
            # error status
            self._set_status('error', 'Exception while running timid: %s' %
                             result, self.status_url)
        elif self.last_status and self.last_status['status'] == 'pending':
            # A test failed and we haven't reported it; do so
            self._set_status('failure', 'Testing failed: %s' % result,
                             self.status_url)

        return result
