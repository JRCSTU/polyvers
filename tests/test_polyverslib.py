#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

import fnmatch
from polyvers import polyverslib as pvlib
import re
import sys

import pytest

import subprocess as sbp


proj1 = 'proj1'
proj1_ver = '0.0.1+'
proj2 = 'proj-2'
proj2_ver = '0.2.1'


split_vtag_validation_patterns = [
    ('proj', None),
    ('proj-1.0.5', None),
    ('proj-1-0.5', None),
    ('proj-v1.0-gaffe', None),
    ('proj-v1', ('proj', '1', None)),
    ('pa-v1.2', ('pa', '1.2', None)),
    ('proj.name-v1.2.3', ('proj.name', '1.2.3', None)),
    ('proj-v1.3_name-v1.2.3', ('proj-v1.3_name', '1.2.3', None)),
    ('foo-bar-v00.0-1-g4f99a6f', ('foo-bar', '00.0', '1-g4f99a6f')),
    ('foo_bar-v00.0.dev1-1-g3fb1bfae20', ('foo_bar', '00.0.dev1', '1-g3fb1bfae20')),
]


@pytest.mark.parametrize('inp, exp', split_vtag_validation_patterns)
def test_split_vtag_parsing(inp, exp):
    vtag_regex = pvlib.vtag_regex
    if exp is None:
        with pytest.raises(ValueError):
            pvlib.split_vtag(inp, vtag_regex)
    else:
        got = pvlib.split_vtag(inp, vtag_regex)
        assert got == exp


@pytest.mark.parametrize('inp, exp', split_vtag_validation_patterns)
def test_fnmatch_format(inp, exp):
    vtag_fnmatch_frmt = pvlib.vtag_fnmatch_frmt
    if exp is None:
        pass
    else:
        project = exp[0]
        frmt = vtag_fnmatch_frmt % project
        assert fnmatch.fnmatch(inp, frmt)


##############
## DESCRIBE ##
##############

def test_polyversion_p1(ok_repo, untagged_repo, no_repo):
    ok_repo.chdir()

    v = pvlib.polyversion(proj1,)
    assert v.startswith(proj1_ver)
    v = pvlib.polyversion(proj1, default='<unused>')
    assert v.startswith(proj1_ver)

    untagged_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        pvlib.polyversion('foo')
    v = pvlib.polyversion('foo', default='<unused>')
    assert v == '<unused>'

    no_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        pvlib.polyversion(proj1)
    v = pvlib.polyversion(proj1, default='<unused>')
    assert v == '<unused>'


def test_polyversion_p2(ok_repo):
    ok_repo.chdir()

    v = pvlib.polyversion(proj2)
    assert v == proj2_ver


def test_polyversion_BAD_project(ok_repo):
    ok_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        pvlib.polyversion('foo')
    v = pvlib.polyversion('foo', default='<unused>')
    assert v == '<unused>'


def test_polyversion_BAD_no_commits(empty_repo):
    empty_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        pvlib.polyversion('foo')
    v = pvlib.polyversion('foo', default='<unused>')
    assert v == '<unused>'


@pytest.mark.skipif(sys.version_info < (3, ),
                    reason="FileNotFoundError not in PY27, OSError only.")
def test_polyversion_BAD_no_git_cmd(ok_repo, monkeypatch):
    ok_repo.chdir()
    monkeypatch.setenv('PATH', '')

    with pytest.raises(FileNotFoundError):
        pvlib.polyversion('foo')
    v = pvlib.polyversion('foo', '0.1.1')
    assert v == '0.1.1'


def test_polytime_p1(ok_repo, untagged_repo, no_repo, today):
    ok_repo.chdir()

    d = pvlib.polytime()
    assert d.startswith(today)
    d = pvlib.polytime(no_raise=True)
    assert d.startswith(today)

    untagged_repo.chdir()

    pvlib.polytime()
    assert d.startswith(today)
    d = pvlib.polytime(no_raise=True)
    assert d.startswith(today)

    no_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        pvlib.polytime()
    d = pvlib.polytime(no_raise=True)
    assert d.startswith(today)


def test_polytime_p2(ok_repo, today):
    ok_repo.chdir()

    d = pvlib.polytime()
    assert d.startswith(today)


def test_polytime_BAD_no_commits(empty_repo):
    empty_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        pvlib.polytime()


@pytest.mark.skipif(sys.version_info < (3, ),
                    reason="FileNotFoundError not in PY27, OSError only.")
def test_polytime_BAD_no_git_cmd(ok_repo, monkeypatch, today):
    ok_repo.chdir()
    monkeypatch.setenv('PATH', '')

    with pytest.raises(FileNotFoundError):
        pvlib.polytime()
    d = pvlib.polytime(no_raise=True)
    assert d.startswith(today)


##############
##   MAIN   ##
##############

def test_MAIN_polyversions(ok_repo, untagged_repo, no_repo, capsys):
    ok_repo.chdir()

    pvlib.main()
    out, err = capsys.readouterr()
    assert not out and not err

    pvlib.main(proj1)
    out, err = capsys.readouterr()
    assert out.startswith(proj1_ver) and not err
    pvlib.main(proj2)
    out, err = capsys.readouterr()
    assert out.startswith(proj2_ver)
    #assert not caplog.text()

    pvlib.main(proj1, proj2, 'foo')
    out, err = capsys.readouterr()
    assert re.match(
        r'proj1: 0\.0\.1\+2\.g[\da-f]+\nproj-2: 0\.2\.1\nfoo:', out)
    #assert 'No names found' in caplog.text()

    untagged_repo.chdir()

    pvlib.main()
    out, err = capsys.readouterr()
    assert not out and not err
    with pytest.raises(sbp.CalledProcessError):
        pvlib.main('foo')
    pvlib.main('foo', 'bar')
    out, err = capsys.readouterr()
    assert out == 'foo: \nbar: \n'
    #assert 'No names found' in caplog.text()

    no_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        pvlib.main(proj1)
    pvlib.main('foo', 'bar')
    out, err = capsys.readouterr()
    assert out == 'foo: \nbar: \n'
    #assert caplog.records()
