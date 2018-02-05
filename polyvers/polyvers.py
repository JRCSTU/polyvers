# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""
Bump independently PEP-440 versions of sub-project in Git monorepos.

USAGE:
  polyvers status
  polyvers [-n] [-f] [-c] [-a] [-t <message>]  <new-ver>

Without <new-ver> prints version extracted from current file.
Don't add a 'v' prefix!

OPTIONS:
  -a, --amend       Amend current commit for setting the "chore(ver): ..." msg.
  -f, --force       Bump (and optionally) commit/tag if version exists/is same.
  -n, --dry-run     Do not write files - just pretend.
  -c, --commit      Commit afterwardswith a commit-message describing version bump.
  -t, --tag=<msg>   Adds a signed tag with the given message (commit implied).


- Pre-releases: when working on some verion
    X.YbN               # Beta release
    X.YrcN  or  X.YcN   # Release Candidate
    X.Y                 # Final release
- Post-release:
    X.YaN.postM         # Post-release of an alpha release
    X.YrcN.postM        # Post-release of a release candidate
- Dev-release:
    X.YaN.devM          # Developmental release of an alpha release
    X.Y.postN.devM      # Developmental release of a post-release

EXAMPLE:
    polyvers -t 'Mostly model changes' 1.6.2b0

"""

from collections import OrderedDict, ChainMap
from datetime import datetime
import os
import re
import sys

import functools as fnt
import os.path as osp

from . import __version__
from ._vendor.traitlets import List, Bool, Unicode  # @UnresolvedImport
from ._vendor.traitlets.config import Configurable, Application

from .autoinstance_traitlet import AutoInstance
from .strexpand_traitlet import StrExpand


my_dir = osp.dirname(__file__)

VFILE = osp.join(my_dir, '..', 'co2mpas', '_version.py')
VFILE_regex_v = re.compile(r'__version__ = version = "([^"]+)"')
VFILE_regex_d = re.compile(r'__updated__ = "([^"]+)"')

RFILE = osp.join(my_dir, '..', 'README.rst')


class CmdException(Exception):
    pass


class Base(Configurable):
    #: A stack of 3 dics used by `interpolation_context_factory()` class-method,
    #: listed with 1st one winning over:
    #:   0. vcs-info: writes affect this one only,
    #:   1. time: (now, utcnow), always updated on access,
    #:   2. env-vars, `$`-prefixed.
    interpolation_context = ChainMap([{}, {}, {}])

    @classmethod
    def interpolation_context_factory(cls, obj, trait, text):
        maps = cls.interpolation_context
        if not maps:
            maps[2].update({'$' + k: v for k, v in os.environ.items()})
        maps[1].update({
            'now': datetime.now(),
            'utcnow': datetime.utcnow(),
        })

        return cls.interpolation_context

    force = Bool(
        config=True,
        help="Bump (and optionally) commit/tag even if version exists/is same.")

    dry_run = Bool(
        config=True,
        help="Do not write files - just pretend.")


class Project(Base):
    tag = Bool(
        config=True,
        help="""
        Enable tagging, per-project.

        Adds a signed tag with name/msg from `tag_name`/`message` (commit implied).

        """)
    sign_tags = Bool(
        config=True,
        help="Enable PGP-signing of tags (see also `sign_user`)."
    )

    sign_user = Unicode(
        config=True,
        help="The signing PGP user (email, key-id)."
    )

    message = StrExpand(
        "chore(ver): bump {current_version} → {new_version}",
        config=True,
        help="""
            The message for commits and per-project tags.

            Available interpolations:
            - `{current_version}`
            - `{new_version}`
            - `{now}`
            - `{utcnow:%d.%m.%Y}`
            - <`{$ENV_VAR}`>
        """)


class Polyvers(Application, Project):
    """"""
    version = __version__
    examples = Unicode("""\
        - Try the `project` sub-command::
              %(cmd_chain)s  project

        - To learn more about command-line options and configurations::
              %(cmd_chain)s  help
              %(cmd_chain)s  config
              %(cmd_chain)s  config paths --config-paths GMail --config-paths ~/.co2dice
              %(cmd_chain)s  config show --source file --config-paths GMail --config-paths ~/.co2dice
    """)
    classes = [Project]

    projects = List(
        AutoInstance(Project),
        config=True)

    use_leaf_releases = Bool(True,
        config=True,
        help="""
            Version-ids statically engraved in-trunk when false, otherwise in "leaf" commits.

            - Limit branches considered as "in-trunk" using `in_trunk_branches` param.
            - Select the name of the Leaf branch with `leaf_branch` param.

            Leaf release-commits avoid frequent merge-conflicts in files containing
            the version-ids.
    """)

    amend = Bool(
        config=True,
        help="Amend the last bump-version commit, if any.")

    commit = Bool(
        config=True,
        help="""
            Commit after engraving with a commit-message describing version bump.

            - If false, no commit created, just search'n replace version-ids.
              Related params: out_of_trunk, message.
            - False make sense only if `use_leaf_releases=False`
        """)


class VersionSubCmd(Application):
    """"""
    pass


class Status(VersionSubCmd):
    """"""
    pass


class Setver(VersionSubCmd):
    """"""
    pass


class Bump(VersionSubCmd):
    """"""
    pass


class Config(Application):
    """"""
    pass


class Help(Application):
    """"""
    pass


Polyvers.subcommands = OrderedDict([
    ('status', ('Status',
                 Status.__doc__)),
])

Polyvers.flags = {
    ('f', 'force'): (
        {'Project': {'force': True}},
        Project.force.help
    ),
    ('n', 'dry-run'): (
        {'Project': {'force': True}},
        Project.dry_run.help
    ),
    ('c', 'commit'): (
        {},
        Polyvers.commit.help
    ),
    ('a', 'amend'): (
        {'Polyvers': {'amend': True}},
        Polyvers.amend.help
    ),
    ('t', 'tag'): (
        {'Project': {'tag': True}},
        Project.tag.help
    ),
    ('s', 'sign-tags'): (
        {'Project': {'sign_tags': True}},
        Project.sign_tags.help
    ),
}

Polyvers.aliases = {
    'log-level': 'Application.log_level',
#     ('m', 'message'): 'Project.message',
#     ('u', 'sign-user'): 'Project.sign_user',
}





@fnt.lru_cache()
def read_txtfile(fpath):
    with open(fpath, 'rt', encoding='utf-8') as fp:
        return fp.read()


def extract_file_regexes(fpath, regexes):
    """
    :param regexes:
        A sequence of regexes to "search", having a single capturing-group.
    :return:
        One groups per regex, or raise if any regex did not match.
    """
    txt = read_txtfile(fpath)
    matches = [regex.search(txt) for regex in regexes]

    if not all(matches):
        raise CmdException("Failed extracting current version: "
                           "\n  ver: %s\n  date: %s" % matches)

    return [m.group(1) for m in matches]


def replace_substrings(files, subst_pairs):
    for fpath in files:
        txt = read_txtfile(fpath)

        replacements = []
        for old, new in subst_pairs:
            replacements.append((old, new, txt.count(old)))
            txt = txt.replace(old, new)

        yield (txt, fpath, replacements)


def format_syscmd(cmd):
    if isinstance(cmd, (list, tuple)):
        cmd = ' '.join('"%s"' % s if ' ' in s else s
                       for s in cmd)
    else:
        assert isinstance(cmd, str), cmd

    return cmd


def strip_ver2_commonprefix(ver1, ver2):
    cprefix = osp.commonprefix([ver1, ver2])
    if cprefix:
        striplen = cprefix.rfind('.')
        if striplen > 0:
            striplen += 1
        else:
            striplen = len(cprefix)
        ver2 = ver2[striplen:]

    return ver2


def run_testcases():
    ## From loading doc-TCs.
    sys.path.insert(0, osp.abspath(osp.normpath(osp.join(my_dir, '..'))))

    import unittest
    import tests.test_docs

    suite = unittest.TestLoader().loadTestsFromModule(tests.test_docs)
    res = unittest.TextTestRunner(failfast=True).run(suite)

    if not res.wasSuccessful():
        raise CmdException("Doc TCs failed, probably version-bumping has failed!")


def exec_cmd(cmd):
    import subprocess as sbp

    err = sbp.call(cmd, stderr=sbp.STDOUT)
    if err:
        raise CmdException("Failed(%i) on: %s" % (err, format_syscmd(cmd)))


def do_commit(new_ver, old_ver, dry_run, amend, ver_files):
    import pathlib

    #new_ver = strip_ver2_commonprefix(old_ver, new_ver)
    cmt_msg = 'chore(ver): bump %s-->%s' % (old_ver, new_ver)

    ver_files = [pathlib.Path(f).as_posix() for f in ver_files]
    git_add = ['git', 'add'] + ver_files
    git_cmt = ['git', 'commit', '-m', cmt_msg]
    if amend:
        git_cmt.append('--amend')
    commands = [git_add, git_cmt]

    for cmd in commands:
        cmd_str = format_syscmd(cmd)
        if dry_run:
            yield "DRYRUN: %s" % cmd_str
        else:
            yield "EXEC: %s" % cmd_str
            exec_cmd(cmd)


def do_tag(tag, tag_msg, dry_run, force):
    cmd = ['git', 'tag', tag, '-s', '-m', tag_msg]
    if force:
        cmd.append('--force')
    cmd_str = format_syscmd(cmd)
    if dry_run:
        yield "DRYRUN: %s" % cmd_str
    else:
        yield "EXEC: %s" % cmd_str
        exec_cmd(cmd)


def bumpver(new_ver, dry_run=False, force=False, amend=False,
            tag_name_or_commit=None):
    """
    :param tag_name_or_commit:
        if true, do `git commit`, if string, also `git tag` with that as msg.
    """
    if amend:
        ## Restore previous version before extracting it.
        exec_cmd('git checkout HEAD~  -- README.rst co2mpas/_version.py'.split())

    regexes = [VFILE_regex_v, VFILE_regex_d]
    old_ver, old_date = extract_file_regexes(VFILE, regexes)

    if not new_ver:
        yield old_ver
        yield old_date
    else:
        if new_ver == old_ver:
            msg = "Version '%s'already bumped"
            if force:
                msg += ", but --force  effected."
                yield msg % new_ver
            else:
                msg += "!\n Use of --force recommended."
                raise CmdException(msg % new_ver)

        from datetime import datetime

        new_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S%z')

        ver_files = [osp.normpath(f) for f in [VFILE, RFILE]]
        subst_pairs = [(old_ver, new_ver), (old_date, new_date)]

        for repl in replace_substrings(ver_files, subst_pairs):
            new_txt, fpath, replacements = repl

            if not dry_run:
                with open(fpath, 'wt', encoding='utf-8') as fp:
                    fp.write(new_txt)

            yield '%s: ' % fpath
            for old, new, nrepl in replacements:
                yield '  %i x (%24s --> %s)' % (nrepl, old, new)

        yield "...now launching DocTCs..."
        run_testcases()

        if tag_name_or_commit is not None:
            yield from do_commit(new_ver, old_ver, dry_run, amend, ver_files)

            if isinstance(tag_name_or_commit, str):
                tag = 'v%s' % new_ver
                yield from do_tag(tag, tag_name_or_commit, dry_run, force)


def OLDmain(*args):
    opts = docopt.docopt(__doc__, argv=args)

    new_ver = opts['<new-ver>']

    assert not new_ver or new_ver[0] != 'v', (
        "Version '%s' must NOT start with `v`!" % new_ver)

    commit = opts['--commit']
    tag = opts['--tag']
    if tag:
        tag_name_or_commit = tag
    elif commit:
        tag_name_or_commit = True
    else:
        tag_name_or_commit = None

    try:
        for i in bumpver(new_ver,
                         opts['--dry-run'],
                         opts['--force'],
                         opts['--amend'],
                         tag_name_or_commit):
            print(i)
    except CmdException as ex:
        sys.exit(str(ex))
    except Exception as ex:
        raise ex
