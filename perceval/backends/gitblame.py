# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors:
#     Santiago Dueñas <sduenas@bitergia.com>
#     Jesus M. Gonzalez-Barahona <jgb@bitergia.com>
#

import json
import logging
import os
import io
import re
import subprocess
import threading
import datetime

from ..backend import Backend, BackendCommand, metadata
from ..errors import RepositoryError, ParseError
from ..utils import DEFAULT_DATETIME, datetime_to_utc, str_to_datetime


logger = logging.getLogger(__name__)


class BlameOutput():
    """Handle git blame output

    Extracts useful information from git blame output.
    Git blame output is slipt in snippets.
    In this context, a git blame snippet is a fragment of the output
    of git blame --incremental, corresponding and several contiguous
    lines for the same commit. For example:

    d7d30291c9ec0ab4af99220ef52e3e88f51e2c31 29 29 1
    author Santiago Dueñas
    author-mail <sduenas@bitergia.com>
    author-time 1470075075
    author-tz +0200
    committer Santiago Dueñas
    committer-mail <sduenas@bitergia.com>
    committer-time 1470075075
    committer-tz +0200
    summary [perceval] Add Redmine backend
    previous a12760b159f813863bb4f7b6c383cad72f824160 README.md
    filename README.md
    d7d30291c9ec0ab4af99220ef52e3e88f51e2c31 174 174 6
    filename README.md

    At least the first (hash) and last (filename) lines should be
    present. When the hash was already seen in the git blame output,
    only those two lines are present, since the rest are understood
    to be the same.

    """

    prefixes = ['author', 'author-mail', 'author-time', 'author-tz',
                'committer', 'committer-mail', 'committer-time', 'committer-tz',
                'summary', 'previous', 'filename']

    def __init__(self, text):
        """
        :param text: text snippet to be analyzed

        """

        self.text = text

    def analyze(self):
        """Analyze the git blame output

        :returns: list of dictionaries, one per snippet, with data about it

        """

        text = io.BytesIO(self.text)
        result = []
        in_snippet = False
        for line in text:
            line = line.decode('utf-8', errors='backslashreplace')
            if not in_snippet:
                # First line of a snippet
                in_snippet = True
                data = {}
                hash_line = line.split()
                data['hash'] = hash_line[0]
                data['prev_line'] = hash_line[1]
                data['this_line'] = hash_line[2]
                data['lines'] = hash_line[3].rstrip('\n')
            else:
                # Other lines of a snippet
                if line == 'boundary\n':
                    data['previous'] = None
                else:
                    components = line.split(maxsplit=1)
                    key = components[0]
                    if key in self.prefixes:
                        if len(components) > 1:
                            value = components[1].rstrip('\n')
                        else:
                            value = ''
                    data[key] = value
                    if key == 'filename':
                        # Snippet is finished
                        in_snippet = False
                        result.append(data)
        return result

class GitBlame(Backend):
    """Git blame backend.

    This class allows to get the results of running git blame from a
    git repository. To initialize this class, you have to provide the
    repository URI and a value for `gitpath`.

    When `gitpath` is a directory or does not exist, it will be
    considered as the place where the repository is/will be cloned;
    when `gitpath` is a file it will be considered as a Git log file.

    :param uri: URI of the Git repository
    :param gitpath: path to the repository or to the log file
    :param cache: cache object to store raw data
    :param origin: identifier of the repository; when `None` or an
        empty string are given, it will be set to `uri` value

    :raises RepositoryError: raised when there was an error cloning or
        updating the repository.
    """
    version = '0.1.0'

    def __init__(self, uri, gitpath, cache=None, origin=None):
        origin = origin if origin else uri

        super().__init__(origin, cache=cache)
        self.uri = uri
        self.gitpath = gitpath

    @metadata
    def blame(self, rev='HEAD'):
        """Get information from git blame.

        The method retrieves blame information from a Git repository.

        The class raises a `RepositoryError` exception when an error occurs
        accessing the repository.

        :param rev: names of revision to annotate (default: 'HEAD')

        :returns: a generator of blame information
        """

        logger.info("Blaming: '%s' git repository for %s revision",
                    self.uri, rev)
        nblames = 0
        nfiles = 0
        for (file, blame_text) in self.__fetch_and_blame(rev):
            nfiles += 1
            blame_output = BlameOutput(blame_text)
            for blame_data in blame_output.analyze():
                blame_data['file_blamed'] = file
                nblames += 1
                # Next two if needed for metadata_updaated_on function
                if 'committer-time' in blame_data:
                    committer_time = blame_data['committer-time']
                else:
                    blame_data['committer-time'] = committer_time
                if 'committer-tz' in blame_data:
                    committer_tz = blame_data['committer-tz']
                else:
                    blame_data['committer-tz'] = committer_tz
                yield blame_data

        logger.info("Blame process completed: %s files, %s snippets analyzed",
                    nfiles, nblames)

    def __fetch_and_blame(self, rev='HEAD'):
        """Fetch git repository and get git blame out for its files

        :param rev: revision to checkout (default: HEAD)

        """

        repo = self.__create_and_update_git_repository()
        repo.checkout(rev)

        for root, dirs, files in os.walk(self.gitpath):
            if '.git' in dirs:
                dirs.remove('.git')
            for file in files:
                filepath = os.path.join(root,file)
                blame_output = repo.blame(filepath)
                yield (filepath[len(self.gitpath)+1:], blame_output)

    def __create_and_update_git_repository(self):
        if not os.path.exists(self.gitpath):
            repo = GitRepository.clone(self.uri, self.gitpath)
        elif os.path.isdir(self.gitpath):
            repo = GitRepository(self.uri, self.gitpath)
        repo.pull()

        return repo

    @staticmethod
    def metadata_id(item):
        """Produce the identifier from a blame item (snippet).

        It is composed by the hash, the file name and the first line
        of the snippet."""

        return item['hash'] + ':' + item['filename'] + ':' + item['this_line']

    @staticmethod
    def metadata_updated_on(item):
        """Extracts the update time from a Git blame item.

        The timestamp used is extracted from 'committer-time'
        (which comes in Unix timestamp format) and the
        committer-tz (which comes in five chars timezone format).

        :param item: item generated by the backend

        :returns: a UNIX timestamp
        """

        tz = item['committer-tz']
        tz_hours = int(tz[0:2])
        tz_min = int(tz[3:4])
        timezone = datetime.timezone(datetime.timedelta(hours=tz_hours,
                                                        minutes=tz_min))
        ts = datetime.datetime.fromtimestamp(timestamp=int(item['committer-time']),
                                            tz=timezone)
        return ts.timestamp()


class GitBlameCommand(BackendCommand):
    """Class to run GitBlame backend from the command line."""

    def __init__(self, *args):
        super().__init__(*args)

        self.uri = self.parsed_args.uri
        self.outfile = self.parsed_args.outfile
        self.origin = self.parsed_args.origin
        self.rev = self.parsed_args.rev

        if not self.parsed_args.git_path:
            base_path = os.path.expanduser('~/.perceval/repositories/')
            git_path = os.path.join(base_path, self.uri)
        else:
            git_path = self.parsed_args.git_path

        cache = None

        self.backend = GitBlame(self.uri, git_path,
                           cache=cache, origin=self.origin)

    def run(self):
        """Fetch and print the blame snipppets.

        This method runs the backend to produce the blame snippets
        from the given git repo. Snippets are converted to JSON objects
        and printed to the defined output.
        """

        try:
            for snippet in self.backend.blame(rev=self.rev):
                obj = json.dumps(snippet, indent=4, sort_keys=True)
                self.outfile.write(obj)
                self.outfile.write('\n')
        except OSError as e:
            raise RuntimeError(str(e))
        except Exception as e:
            raise RuntimeError(str(e))

    @classmethod
    def create_argument_parser(cls):
        """Returns the Git argument parser."""

        parser = super().create_argument_parser()

        # Mutual exclusive parameters
        #group = parser.add_mutually_exclusive_group()

        # Required arguments
        parser.add_argument('uri',
                            help="URI of the Git repository")

        # Optional arguments
        parser.add_argument('--git-path', dest='git_path',
                           help="Path where the Git repository will be cloned")
        parser.add_argument('--rev', dest='rev',
                            type=str, default='HEAD',
                            help='Fetch commits for this revision (default: HEAD)')
        return parser

class GitRepository:
    """Manage a Git repository.

    This class provides access to a Git repository running some
    common commands such as `clone`, `pull` or `log`.
    To create an instance from a remote repository, use `clone()`
    class method.

    :param uri: URI of the repository
    :param dirpath: local directory where the repository is stored
    """
    def __init__(self, uri, dirpath):
        gitdir = os.path.join(dirpath, '.git')

        if not os.path.exists(gitdir):
            cause = "git repository '%s' does not exist" % dirpath
            raise RepositoryError(cause=cause)

        self.uri = uri
        self.dirpath = dirpath

    @classmethod
    def clone(cls, uri, dirpath):
        """Clone a Git repository.

        Clone the repository stored in `uri` into `dirpath`. The repository
        would be either local or remote.

        :param uri: URI of the repository
        :param dirtpath: directory where the repository will be cloned

        :returns: a `GitRepository` class having cloned the repository

        :raises RepositoryError: when an error occurs cloning the given
            repository
        """
        cmd = ['git', 'clone', uri, dirpath]
        cls._exec(cmd, env={'LANG' : 'C'})

        logging.debug("Git %s repository cloned into %s",
                      uri, dirpath)

        return cls(uri, dirpath)

    def checkout(self, rev):
        """Checkout a certain revision from a Git repository.

        The repository is assumed to be already cloned.

        :param rev: revision to checkout

        :raises RepositoryError: when an error occurs cloning the given
            repository
        """
        cmd = ['git', '-C', self.dirpath, 'checkout', rev]
        self._exec(cmd, env={'LANG' : 'C'})

        logging.debug("Git %s repository checked out to %s",
                      self.dirpath, rev)

    def blame(self, file):
        """Run git blame for a certain file in the repository

        The repository is assumed to be already cloned.

        :param file: file to blame

        :returns: result of running git blame as a string

        """

        cmd = ['git', '-C', self.dirpath, 'blame', '--incremental', file]
        blame_output = subprocess.check_output(cmd, env={'LANG' : 'C'},
                                            universal_newlines=False)

        logging.debug("Git blame run on %s", file)
        return blame_output

    def pull(self):
        """Update repository from 'origin' remote.

        Calling this method, the repository will be synchronized with
        'origin' repository. Any commit stored in the local copy will
        be removed.

        :raises RepositoryError: when an error occurs updating the
            repository
        """
        cmd_fetch = ['git', 'fetch', 'origin']
        cmd_reset = ['git', 'reset', '--hard', 'origin']

        self._exec(cmd_fetch, cwd=self.dirpath, env={'LANG' : 'C'})
        self._exec(cmd_reset, cwd=self.dirpath, env={'LANG' : 'C'})

        logging.debug("Git %s repository pulled into %s",
                      self.uri, self.dirpath)

    @staticmethod
    def _exec(cmd, cwd=None, env=None):
        """Run a command.

        Execute `cmd` command in the directory set by `cwd`. Enviroment
        variables can be set using the `env` dictionary. The output
        data is returned as encoded bytes.

        :returns: the output of the command as encoded bytes

        :raises RepositoryError: when an error occurs running the command
        """
        logging.debug("Running command %s (cwd: %s, env: %s)",
                      ' '.join(cmd), cwd, str(env))

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    cwd=cwd, env=env)
            (outs, errs) = proc.communicate()
        except OSError as e:
            raise RepositoryError(cause=str(e))

        if proc.returncode != 0:
            err = errs.decode('utf-8', errors='backslashreplace')
            cause = "git command - %s" % err
            raise RepositoryError(cause=cause)
        else:
            logging.debug(errs.decode('utf-8', errors='backslashreplace'))

        return outs
