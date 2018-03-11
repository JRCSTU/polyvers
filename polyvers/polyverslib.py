#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""
Python-2.7 safe code to discover sub-project versions in Git *polyvers* monorepos.

The *polyvers* version-configuration tool is generating **pvtags** like::

    proj-foo-v0.1.0

And assuming :func:`polyversion()` is invoked from within a Git repo, it may return
either ``0.1.0`` or ``0.1.0+2.gcaffe00``, if 2 commits have passed since
last *pvtag*.
"""
from __future__ import print_function

import inspect
import os
import re
import sys

import os.path as osp
import subprocess as sbp


#: The default pattern for *pvtags* receiving 2 :pep:`3101` parameters
#: ``{pname}`` and ``{version} = '*'`` to interpolate.  It is used to generate
#: the match patterns for ``git describe --match <pattern>`` command.
pvtag_frmt = '{pname}-v{version}'

#: The default regex pattern breaking *pvtags* and/or ``git-describe`` output
#: into 3 capturing groups.
#: It is given a :pep:`3101` parameter ``{pname}`` to interpolate.
#: See :pep:`0426` for project-name characters and format.
pvtag_regex = r"""(?xi)
    ^(?P<pname>{pname})
    -
    v(?P<version>\d[^-]*)
    (?:-(?P<descid>\d+-g[a-f\d]+))?$
"""


#: The default pattern for *vtags* receiving 2 :pep:`3101` parameters
#: ``{pname}`` and ``{version} = '*'`` to interpolate.  It is used to generate
#: the match patterns for ``git describe --match <pattern>`` command.
vtag_frmt = 'v{version}'

#: The default regex pattern breaking *pvtags* and/or ``git-describe`` output
#: into 3 capturing groups.
#: It is given a :pep:`3101` parameter ``{pname}`` to interpolate.
#: See :pep:`0426` for project-name characters and format.
vtag_regex = r"""(?xi)
    ^(?P<pname>)
    v(?P<version>\d[^-]*)
    (?:-(?P<descid>\d+-g[a-f\d]+))?$
"""


def clean_cmd_result(res):  # type: (bytes) -> str
    """
    :return:
        only if there is something in `res`, as utf-8 decoded string
    """
    res = res and res.strip()
    if res:
        return res.decode('utf-8', errors='surrogateescape')


def rfc2822_tstamp(nowdt=None):
    """Py2.7 code from https://stackoverflow.com/a/3453277/548792"""
    from datetime import datetime
    import time
    from email import utils

    if nowdt is None:
        nowdt = datetime.now()
    nowtuple = nowdt.timetuple()
    nowtimestamp = time.mktime(nowtuple)
    now = utils.formatdate(nowtimestamp, localtime=True)

    return now


def _my_run(cmd, cwd):
    "For commands with small output/stderr."
    if not isinstance(cmd, (list, tuple)):
        cmd = cmd.split()
    proc = sbp.Popen(cmd, stdout=sbp.PIPE, stderr=sbp.PIPE,
                     cwd=str(cwd), bufsize=-1)
    res, err = proc.communicate()

    if proc.returncode != 0:
        print('%s\n  cmd: %s' % (err, cmd), file=sys.stderr)
        raise sbp.CalledProcessError(proc.returncode, cmd)
    else:
        return clean_cmd_result(res)


def _caller_fpath(nframes_back=2):
    frame = inspect.currentframe()
    try:
        for _ in range(nframes_back):
            frame = frame.f_back
        fpath = inspect.getframeinfo(frame).filename

        return osp.dirname(fpath)
    finally:
        del frame


def split_pvtag(pvtag, pvtag_regex):
    try:
        m = pvtag_regex.match(pvtag)
        if not m:
            raise ValueError(
                "Unparseable *pvtag* from `pvtag_regex`!")
        mg = m.groupdict()
        return mg['pname'], mg['version'], mg['descid']
    except Exception as ex:
        print("Matching pvtag '%s' failed due to: %s" %
              (pvtag, ex), file=sys.stderr)
        raise


def version_from_descid(version, descid):
    """
    Combine ``git-describe`` parts in a :pep:`440` version with "local" part.

    :param: version:
        anythng after the project and ``'-v`'`` i,
        e.g it is ``1.7.4.post0``. ``foo-project-v1.7.4.post0-2-g79ceebf8``
    :param: descid:
        the part after the *pvtag* and the 1st dash('-'), which must not be empty,
        e.g it is ``2-g79ceebf8`` for ``foo-project-v1.7.4.post0-2-g79ceebf8``.
    :return:
        something like this: ``1.7.4.post0+2.g79ceebf8`` or ``1.7.4.post0``
    """
    assert descid, (version, descid)
    local_part = descid.replace('-', '.')
    return '%s+%s' % (version, local_part)


def _pvtag_fnmatch_frmt(tag_frmt, pname):
    return tag_frmt.format(pname=pname, version='*')


def polyversion(project, default=None, repo_path=None,
                monoproject=None,
                tag_frmt=None, tag_regex=None,
                git_options=()):
    """
    Report the *pvtag* of the `project` in the git repo hosting the source-file calling this.

    :param str project:
        Used as the prefix of pvtags when searching them.
    :param str default:
        What *version* to return if git cmd fails.
    :param str repo_path:
        A path inside the git repo hosting the `project` in question; if missing,
        derived from the calling stack.
    :param bool monoproject:
        Choose versioning scheme:

        - false: (default) use *pvtags* :data:`pvtag_frmt` & :data:`pvtag_regex`.
        - true: use plain *vtags* :data:`vtag_frmt` & :data:`vtag_regex`.
        - The `tag_frmt` and `tag_regex` args take precendance, if given.
    :param str tag_frmt:
        The :pep:`3101` pattern for creating *pvtags* (or *vtags).

        - It receives 2 parameters to interpolate: ``{pname}, {version} = '*'``.
        - It is used also to generate the match patterns for ``git describe --match <pattern>``
          command.
        - It overrides `monoproject` arg.
        - See :data:`pvtag_frmt` & :data:`vtag_frmt`
    :param regex tag_regex:
        The regex pattern breaking apart *pvtags*, with 3 named capturing groups:
        - ``pname``,
        - ``version`` (without the 'v'),
        - ``descid`` (optional) anything following the dash('-') after
          the version in ``git-describe`` result.

        - It is given a :pep:`3101` parameter ``{pname}`` to interpolate.
        - It overrides `monoproject` arg.
        - See :pep:`0426` for project-name characters and format.
        - See :data:`pvtag_regex` & :data:`vtag_regex`
    :param git_options:
        List of options(str) passed to ``git describe`` command.
    :return:
        The version-id derived from the *pvtag*, or `default` if
        command failed/returned nothing.

    .. TIP::
        It is to be used in ``__init__.py`` files like this::

            __version__ = polyversion('myproj')

        ...or in ``setup.py`` where a default is needed for *develop* mode
        to work::

            version=polyversion('myproj', '0.0.0)

    .. NOTE::
       This is a python==2.7 & python<3.6 safe function; there is also the similar
       function with elaborate error-handling :func:`polyvers.pvtags.descrivbe_project()`
       used by the tool internally.
    """
    version = None

    if tag_frmt is None:
        tag_frmt = vtag_frmt if monoproject else pvtag_frmt
    if tag_regex is None:
        tag_regex = vtag_regex if monoproject else pvtag_regex
    if not repo_path:
        repo_path = _caller_fpath()

    tag_pattern = _pvtag_fnmatch_frmt(tag_frmt, project)
    tag_regex = re.compile(tag_regex.format(pname=project))
    try:
        cmd = 'git describe'.split()
        cmd.extend(git_options)
        cmd.append('--match')
        cmd.append(tag_pattern)
        pvtag = _my_run(cmd, cwd=repo_path)
        matched_project, version, descid = split_pvtag(pvtag, tag_regex)
        if matched_project != project:
            print("Matched  pvtag project '%s' different from expected '%s'!" %
                  (matched_project, project), file=sys.stderr)
        if descid:
            version = version_from_descid(version, descid)
    except:  # noqa;  E722"
        if default is None:
            raise

    if not version:
        version = default

    return version


def polytime(no_raise=False, repo_path=None):
    """
    The timestamp of last commit in git repo hosting the source-file calling this.

    :param str no_raise:
        If true, never fail and return current-time
    :param str repo_path:
        A path inside the git repo hosting the project in question; if missing,
        derived from the calling stack.
    :return:
        the commit-date if in git repo, or now; :rfc:`2822` formatted
    """
    # TODO: Move main from `pvlib` --> `polyvers.pvtgs`
    cdate = None
    if not repo_path:
        repo_path = _caller_fpath()
    cmd = "git log -n1 --format=format:%cD"
    try:
            cdate = _my_run(cmd, cwd=repo_path)
    except:  # noqa;  E722
        if not no_raise:
            raise

    if not cdate:
        cdate = rfc2822_tstamp()

    return cdate


def main(*args):
    """
    Describe a single or multiple projects.

    :param args:
        usually ``*sys.argv[1:]``
    """
    for o in ('-h', '--help'):
        if o in args:
            doc = main.__doc__.split('\n')[1].strip()
            cmdname = osp.basename(sys.argv[0])
            print("%s\n\nUsage: %s [-v|--verbose] [PROJ-1]..." %
                  (doc, cmdname))
            exit(0)

    if len(args) == 1:
        res = polyversion(args[0], repo_path=os.curdir)
    else:
        res = '\n'.join('%s: %s' % (p, polyversion(p, default='',
                                                   repo_path=os.curdir))
                        for p in args)

    if res:
        print(res)


if __name__ == '__main__':
    main(*sys.argv[1:])
