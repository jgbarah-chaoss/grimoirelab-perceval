#!/usr/bin/env python3
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

import unittest
import sys
import io
import tempfile
import os.path
import shutil
import subprocess
import argparse

if not '..' in sys.path:
    sys.path.insert(0, '..')

from perceval.errors import ParseError, RepositoryError
from perceval.backend import uuid
from perceval._version import __version__
from perceval.backends.gitblame import (BlameOutput, GitBlame,
                                        GitBlameCommand, GitRepository)


class TestBlameOutput(unittest.TestCase):
    """Git blame output tests"""

    text = """d7d30291c9ec0ab4af99220ef52e3e88f51e2c31 29 29 1
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
d8e0f9c118f3026251ba0369424b7a3918a66231 27 27 1
author Santiago Dueñas
author-mail <sduenas@bitergia.com>
author-time 1469722351
author-tz +0200
committer Santiago Dueñas
committer-mail <sduenas@bitergia.com>
committer-time 1469725990
committer-tz +0200
summary [perceval] Add Phabricator backend
previous d163a11551f52c13f38824a2a4a2e23409e60d96 README.md
filename README.md
d8e0f9c118f3026251ba0369424b7a3918a66231 163 164 5
filename README.md
ba1e441986b32f505e1dbaa1e8e16758c073fc07 24 24 1
author Alvaro del Castillo
author-mail <acs@bitergia.com>
author-time 1467802564
author-tz +0200
committer Alvaro del Castillo
committer-mail <acs@bitergia.com>
committer-time 1468965921
committer-tz +0200
summary [perceval] Add Kitsune backend
previous 6c797b8499a70f3af520bcd0863127dc0f29fb94 README.md
filename README.md
ba1e441986b32f505e1dbaa1e8e16758c073fc07 147 149 5
filename README.md
""".encode('utf-8')

    analyzed = [{
        'hash': 'd7d30291c9ec0ab4af99220ef52e3e88f51e2c31',
        'prev_line': '29',
        'this_line': '29',
        'lines': '1',
        'committer': 'Santiago Dueñas',
        'committer-mail': '<sduenas@bitergia.com>',
        'committer-time': '1470075075',
        'committer-tz': '+0200',
        'author': 'Santiago Dueñas',
        'author-mail': '<sduenas@bitergia.com>',
        'author-time': '1470075075',
        'author-tz': '+0200',
        'summary': '[perceval] Add Redmine backend',
        'previous': 'a12760b159f813863bb4f7b6c383cad72f824160 README.md',
        'filename': 'README.md'
        },
        {'hash': 'd7d30291c9ec0ab4af99220ef52e3e88f51e2c31',
        'lines': '6',
        'filename': 'README.md',
        'prev_line': '174',
        'this_line': '174'},
        {'lines': '1',
        'prev_line': '27',
        'this_line': '27',
        'committer-time': '1469725990',
        'author-mail': '<sduenas@bitergia.com>',
        'committer-mail': '<sduenas@bitergia.com>',
        'author-time': '1469722351',
        'author': 'Santiago Dueñas',
        'author-tz': '+0200',
        'summary': '[perceval] Add Phabricator backend',
        'hash': 'd8e0f9c118f3026251ba0369424b7a3918a66231',
        'previous': 'd163a11551f52c13f38824a2a4a2e23409e60d96 README.md',
        'committer': 'Santiago Dueñas',
        'filename': 'README.md',
        'committer-tz': '+0200'},
        {'hash': 'd8e0f9c118f3026251ba0369424b7a3918a66231',
        'lines': '5',
        'filename': 'README.md',
        'prev_line': '163',
        'this_line': '164'},
        {'lines': '1',
        'prev_line': '24',
        'this_line': '24',
        'committer-time': '1468965921',
        'author-mail': '<acs@bitergia.com>',
        'committer-mail': '<acs@bitergia.com>',
        'author-time': '1467802564',
        'author': 'Alvaro del Castillo',
        'author-tz': '+0200',
        'summary': '[perceval] Add Kitsune backend',
        'hash': 'ba1e441986b32f505e1dbaa1e8e16758c073fc07',
        'previous': '6c797b8499a70f3af520bcd0863127dc0f29fb94 README.md',
        'committer': 'Alvaro del Castillo',
        'filename': 'README.md',
        'committer-tz': '+0200'},
        {'hash': 'ba1e441986b32f505e1dbaa1e8e16758c073fc07',
        'lines': '5',
        'filename': 'README.md',
        'prev_line': '147',
        'this_line': '149'}]

    @classmethod
    def setUpClass(cls):
        lines = cls.text.splitlines(keepends=True)
        cls.text_single = b''.join(lines[0:12])
        cls.analyzed_single = [cls.analyzed[0]]

    def test_initialization(self):
        """Test initialization"""

        output = BlameOutput(self.text)
        self.assertEqual(output.text, self.text)

    def test_analyze(self):
        """Test analyze function"""

        output = BlameOutput(self.text_single)
        result = output.analyze()
        self.assertEqual(result, self.analyzed_single)

        output = BlameOutput(self.text)
        result = output.analyze()
        self.assertEqual(result, self.analyzed)

class TestGitBlameBackend(unittest.TestCase):
    """GitBlame backend tests"""

    @classmethod
    def setUpClass(cls):
        cls.tmp_path = tempfile.mkdtemp(prefix='perceval_')
        cls.git_path = os.path.join(cls.tmp_path, 'gittest')

        subprocess.check_call(['tar', '-xzf', 'data/gittest.tar.gz',
                               '-C', cls.tmp_path])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_path)

    def test_initialization(self):
        """Test whether attributes are initializated"""

        git = GitBlame('http://example.com', self.git_path, origin='test')

        self.assertEqual(git.uri, 'http://example.com')
        self.assertEqual(git.gitpath, self.git_path)
        self.assertEqual(git.origin, 'test')

        # When origin is empty or None it will be set to
        # the value in uri
        git = GitBlame('http://example.com', self.git_path)
        self.assertEqual(git.origin, 'http://example.com')

        git = GitBlame('http://example.com', self.git_path, origin='')
        self.assertEqual(git.origin, 'http://example.com')

    def test_blame(self):
        """Test blame function"""


        results = [{'backend_name': 'GitBlame',
        'backend_version': GitBlame.version,
        'origin': self.git_path,
        'perceval_version': __version__,
        'updated_on': 1392185366.0,
        'data': {
        'author-time': '1392185366',
        'committer-tz': '-0800',
        'author-mail': '<lin.zhp@gmail.com>',
        'this_line': '1',
        'summary': 'modify aaa/otherthing',
        'filename': 'aaa/otherthing',
        'file_blamed': 'aaa/otherthing.renamed',
        'committer-mail': '<lin.zhp@gmail.com>',
        'committer': 'Zhongpeng Lin (林中鹏)',
        'lines': '1',
        'author': 'Zhongpeng Lin (林中鹏)',
        'previous': '589bb080f059834829a2a5955bebfd7c2baa110a aaa/otherthing',
        'hash': '51a3b654f252210572297f47597b31527c475fb8',
        'author-tz': '-0800',
        'prev_line': '1',
        'committer-time': '1392185366'}},
        {'backend_name': 'GitBlame',
        'backend_version': GitBlame.version,
        'origin': self.git_path,
        'perceval_version': __version__,
        'updated_on': 1344967441.0,
        'data': {
        'author-time': '1344967441',
        'committer-tz': '-0300',
        'author-mail': '<companheiro.vermelho@gmail.com>',
        'this_line': '1',
        'summary': 'Create "deeply" nested file',
        'filename': 'eee/fff/wildthing',
        'file_blamed': 'eee/fff/wildthing',
        'committer-mail': '<companheiro.vermelho@gmail.com>',
        'committer': 'Eduardo Morais',
        'lines': '1',
        'author': 'Eduardo Morais',
        'hash': '589bb080f059834829a2a5955bebfd7c2baa110a',
        'author-tz': '-0300',
        'prev_line': '1',
        'committer-time': '1344967441'}}]

        self.maxDiff = None
        new_path = os.path.join(self.tmp_path, 'newgit')
        git_blame = GitBlame(self.git_path, new_path)
        nsnippet = 0
        for snippet in git_blame.blame():
            snippet.pop('timestamp')
            snippet.pop('uuid')
            print(snippet)
            self.assertDictEqual(snippet, results[nsnippet])
            nsnippet += 1
        shutil.rmtree(new_path)

def count_commits(path):
    """Get the number of commits counting the entries on the log"""

    cmd = ['git', 'log', '--oneline']
    gitlog = subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                     cwd=path,
                                     env={'LANG' : 'C', 'PAGER' : ''})
    commits = gitlog.strip(b'\n').split(b'\n')
    return len(commits)

class TestGitBlameCommand(unittest.TestCase):
    """GitBlameCommand tests"""

    def test_parsing_on_init(self):
        """Test if the class is initialized"""

        args = ['http://example.com/', '--origin', 'test']

        cmd = GitBlameCommand(*args)
        self.assertIsInstance(cmd.parsed_args, argparse.Namespace)
        self.assertEqual(cmd.parsed_args.uri, 'http://example.com/')
        self.assertEqual(cmd.parsed_args.origin, 'test')
        self.assertIsInstance(cmd.backend, GitBlame)

        args = ['http://example.com/', '--rev', 'RELEASE_1']

        cmd = GitBlameCommand(*args)
        self.assertIsInstance(cmd.parsed_args, argparse.Namespace)
        self.assertEqual(cmd.parsed_args.uri, 'http://example.com/')
        self.assertEqual(cmd.parsed_args.rev, "RELEASE_1")
        self.assertIsInstance(cmd.backend, GitBlame)

    def test_argument_parser(self):
        """Test if it returns a argument parser object"""

        parser = GitBlameCommand.create_argument_parser()
        self.assertIsInstance(parser, argparse.ArgumentParser)



class TestGitRepository(unittest.TestCase):
    """GitRepository tests"""

    @classmethod
    def setUpClass(cls):
        cls.tmp_path = tempfile.mkdtemp(prefix='perceval_')
        cls.git_path = os.path.join(cls.tmp_path, 'gittest')

        subprocess.check_call(['tar', '-xzf', 'data/gittest.tar.gz',
                               '-C', cls.tmp_path])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_path)

    def test_init(self):
        """Test initialization"""

        repo = GitRepository('http://example.git', self.git_path)

        self.assertIsInstance(repo, GitRepository)
        self.assertEqual(repo.uri, 'http://example.git')
        self.assertEqual(repo.dirpath, self.git_path)

    def test_not_existing_repo_on_init(self):
        """Test if init fails when the repos does not exists"""

        expected = "git repository '%s' does not exist" % (self.tmp_path)

        with self.assertRaisesRegex(RepositoryError, expected):
            _ = GitRepository('http://example.org', self.tmp_path)

    def test_clone(self):
        """Test if a git repository is cloned"""

        new_path = os.path.join(self.tmp_path, 'newgit')

        repo = GitRepository.clone(self.git_path, new_path)

        self.assertIsInstance(repo, GitRepository)
        self.assertEqual(repo.uri, self.git_path)
        self.assertEqual(repo.dirpath, new_path)
        self.assertTrue(os.path.exists(new_path))
        self.assertTrue(os.path.exists(os.path.join(new_path, '.git')))

        shutil.rmtree(new_path)

    def test_not_git(self):
        """Test if a supposed git repo is not a git repo"""

        new_path = os.path.join(self.tmp_path, 'falsegit')
        if not os.path.isdir(new_path):
            os.makedirs(new_path)

        expected = "git repository '%s' does not exist" % new_path

        with self.assertRaisesRegex(RepositoryError, expected):
            repo = GitRepository(uri="", dirpath=new_path)

        shutil.rmtree(new_path)

    def test_clone_error(self):
        """Test if it raises an exception when an error occurs cloning a repository"""

        # Clone a non-git repository
        new_path = os.path.join(self.tmp_path, 'newgit')

        expected = "git command - fatal: repository '%s' does not exist" \
            % self.tmp_path

        with self.assertRaisesRegex(RepositoryError, expected):
            _ = GitRepository.clone(self.tmp_path, new_path)

    def test_clone_existing_directory(self):
        """Test if it raises an exception when tries to clone an existing directory"""

        expected = "git command - fatal: destination path '%s' already exists" \
            % (self.tmp_path)

        with self.assertRaisesRegex(RepositoryError, expected):
            _ = GitRepository.clone(self.git_path, self.tmp_path)

    def test_pull(self):
        """Test if the repository is updated to 'origin' status"""

        new_path = os.path.join(self.tmp_path, 'newgit')
        new_file = os.path.join(new_path, 'newfile')

        repo = GitRepository.clone(self.git_path, new_path)

        # Count the number of commits before adding a new one
        ncommits = count_commits(new_path)
        self.assertEqual(ncommits, 9)

        # Create a new file and commit it to the repository
        with open(new_file, 'w') as f:
            f.write("Testing pull method")

        cmd = ['git', 'add', new_file]
        subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                cwd=new_path, env={'LANG' : 'C'})

        cmd = ['git', '-c', 'user.name="mock"',
               '-c', 'user.email="mock@example.com"',
               'commit', '-m', 'Testing pull']
        subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                cwd=new_path, env={'LANG' : 'C'})

        # Count the number of commits after the adding a new one
        ncommits = count_commits(new_path)
        self.assertEqual(ncommits, 10)

        # Update the repository to its original status
        repo.pull()

        # The number of commits should be updated to its original value
        ncommits = count_commits(new_path)
        self.assertEqual(ncommits, 9)

        shutil.rmtree(new_path)

    def test_checkout(self):
        """Test if the repository is checked out to an specific revision"""

        new_path = os.path.join(self.tmp_path, 'newgit')
        repo = GitRepository.clone(self.git_path, new_path)
        repo.checkout('HEAD')
        ncommits = count_commits(new_path)
        self.assertEqual(ncommits, 9)

        repo.checkout('589bb080f059834829a2a5955bebfd7c2baa110a')
        ncommits = count_commits(new_path)
        self.assertEqual(ncommits, 6)

        shutil.rmtree(new_path)

    def test_blame(self):
        """Test blame function"""

        other_output = """51a3b654f252210572297f47597b31527c475fb8 1 1 1
author Zhongpeng Lin (林中鹏)
author-mail <lin.zhp@gmail.com>
author-time 1392185366
author-tz -0800
committer Zhongpeng Lin (林中鹏)
committer-mail <lin.zhp@gmail.com>
committer-time 1392185366
committer-tz -0800
summary modify aaa/otherthing
previous 589bb080f059834829a2a5955bebfd7c2baa110a aaa/otherthing
filename aaa/otherthing
"""

        new_path = os.path.join(self.tmp_path, 'newgit')
        repo = GitRepository.clone(self.git_path, new_path)
        blame_output = repo.blame('ddd/finalthing')
        self.assertEqual(blame_output, b'')
        blame_output = repo.blame('aaa/otherthing.renamed')
        self.assertEqual(blame_output, other_output.encode('utf-8'))

        shutil.rmtree(new_path)

if __name__ == "__main__":
    unittest.main()
