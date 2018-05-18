#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""
Python-2.7-safe, no-deps code to discover sub-project versions in Git *polyvers* monorepos.

The *polyvers* version-configuration tool is generating **pvtags** like::

    proj-foo-v0.1.0

And assuming :func:`polyversion()` is invoked from within a Git repo, it may return
either ``0.1.0`` or ``0.1.0+2.gcaffe00``, if 2 commits have passed since
last *pvtag*.

Also the wheel is executable like that::

    python polyversion-*.whl --help

"""
from __future__ import print_function

import inspect
import re
import sys

import os.path as osp
import subprocess as sbp


#: A 2-tuple containing 2 ``{vprefix}`` values for the patterns below,for
#: for *version-tags* and *release-tags* respectively.
tag_vprefixes = ('v', 'r')

#: The default pattern for *monorepos* version-tags,
#: receiving 3 :pep:`3101` interpolation parameters::
#:
#:     {pname}, {version} = '*', {vprefix} = tag_vprefixes[0 | 1]
#:
#: The match patterns for ``git describe --match <pattern>`` are generated by this.
pvtag_frmt = '{pname}-{vprefix}{version}'
#: Like :data:`pvtag_frmt` but for *mono-project* version-tags.
vtag_frmt = '{vprefix}{version}'

#: The default regex pattern breaking *monorepo* version-tags
#: and/or ``git-describe`` output into 3 capturing groups:
#:   - ``pname``,
#:   - ``version`` (without the ``{vprefix)``),
#:   - ``descid`` (optional) anything following the dash('-') after
#:     the version in ``git-describe`` result.
#:
#: It is given 2 :pep:`3101` interpolation parameters::
#:
#:     {pname}, {vprefix} = tag_vprefixes[0 | 1]
#:
#: See :pep:`0426` for project-name characters and format.
pvtag_regex = r"""(?xmi)
    ^(?P<pname>{pname})
    -
    {vprefix}(?P<version>\d[^-]*)
    (?:-(?P<descid>\d+-g[a-f\d]+))?$
"""
#: Like :data:`pvtag_frmt` but for *mono-project* version-tags.
vtag_regex = r"""(?xmi)
    ^(?P<pname>)
    {vprefix}(?P<version>\d[^-]*)
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


def _interp_fnmatch(tag_frmt, pname, is_release=False):
    return tag_frmt.format(pname=pname,
                           version='*',
                           vprefix=tag_vprefixes[int(is_release)])


def _interp_regex(tag_regex, pname, is_release=False):
    return tag_regex.format(pname=pname,
                            vprefix=tag_vprefixes[int(is_release)])


def polyversion(pname, default=None, repo_path=None,
                mono_project=None,
                tag_frmt=None, tag_regex=None,
                git_options=()):
    """
    Report the *pvtag* of the `pname` in the git repo hosting the source-file calling this.

    :param str pname:
        The project-name, used as the prefix of pvtags when searching them.
    :param str default:
        What *version* to return if git cmd fails.
    :param str repo_path:
        A path inside the git repo hosting the `pname` in question; if missing,
        derived from the calling stack.
    :param bool mono_project:
        Choose versioning scheme:

        - false: (default) use *pvtags* :data:`pvtag_frmt` & :data:`pvtag_regex`.
        - true: use plain *vtags* :data:`vtag_frmt` & :data:`vtag_regex`.
        - The `tag_frmt` and `tag_regex` args take precendance, if given.
    :param str tag_frmt:
        The :pep:`3101` pattern for creating *pvtags* (or *vtags).

        - It receives 2 parameters to interpolate: ``{pname}, {version} = '*'``.
        - It is used also to generate the match patterns for ``git describe --match <pattern>``
          command.
        - It overrides `mono_project` arg.
        - See :data:`pvtag_frmt` & :data:`vtag_frmt`
    :param regex tag_regex:
        The regex pattern breaking apart *pvtags*, with 3 named capturing groups:
        - ``pname``,
        - ``version`` (without the 'v'),
        - ``descid`` (optional) anything following the dash('-') after
          the version in ``git-describe`` result.

        - It is given a :pep:`3101` parameter ``{pname}`` to interpolate.
        - It overrides `mono_project` arg.
        - See :pep:`0426` for project-name characters and format.
        - See :data:`pvtag_regex` & :data:`vtag_regex`
    :param git_options:
        List of options(str) passed to ``git describe`` command.
    :return:
        The version-id derived from the *pvtag*, or `default` if
        command failed/returned nothing.

    .. TIP::
        It is to be used in ``__init__.py`` files like this::

            __version__ = '0.0.2a5'

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
        tag_frmt = vtag_frmt if mono_project else pvtag_frmt
    if tag_regex is None:
        tag_regex = vtag_regex if mono_project else pvtag_regex
    if not repo_path:
        repo_path = _caller_fpath()
        if not repo_path:
            repo_path = '.'

    tag_pattern = _interp_fnmatch(tag_frmt, pname)
    tag_regex = re.compile(_interp_regex(tag_regex, pname))
    try:
        cmd = 'git describe'.split()
        cmd.extend(git_options)
        cmd.append('--match=' + tag_pattern)
        pvtag = _my_run(cmd, cwd=repo_path)
        matched_project, version, descid = split_pvtag(pvtag, tag_regex)
        if matched_project and matched_project != pname:
            #import traceback as tb
            #tb.print_stack()
            print("Matched  pvtag project '%s' different from expected '%s'!" %
                  (matched_project, pname), file=sys.stderr)
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


def run(*args):
    """
    Describe the version of a *polyvers* projects from git tags.

    USAGE:
        %(prog)s [PROJ-1] ...

    See http://polyvers.readthedocs.io

    :param argv:
        Cmd-line arguments, nothing assumed if nothing given.

    - Invokes :func:`polyversion.run()` with ``sys.argv[1:]``.
    - In order to set cmd-line arguments, invoke directly the function above.
    """
    import os

    for o in ('-h', '--help'):
        import textwrap as tw

        if o in args:
            cmdname = osp.basename(sys.argv[0])
            doc = tw.dedent('\n'.join(run.__doc__.split('\n')[1:7]))
            print(doc % {'prog': cmdname})
            return 0

    if len(args) == 1:
        res = polyversion(args[0], repo_path=os.curdir)
    else:
        res = '\n'.join('%s: %s' % (p, polyversion(p, default='',
                                                   repo_path=os.curdir))
                        for p in args)

    if res:
        print(res)
