# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

from polyvers._vendor.traitlets import HasTraits  # @UnresolvedImport
from polyvers.interp_traitlet import Template, Now, InterpContext

import pytest


texts = [
    ('{key}', {'key': 123}, '123'),
    ('a{key}b', {'key': 123}, 'a123b'),

    ('foo', {}, 'foo'),
]


@pytest.mark.parametrize('s, ctxt, exp', texts)
def test_Unicode_interpolation(s, ctxt, exp):
    class C1(HasTraits):
        interpolation = ctxt
        s = Template()

    class C2(HasTraits):
        interpolation = lambda _, __, v: v.format(**ctxt)
        s = Template()

    class C3(HasTraits):
        interpolation = lambda _, __, v: v.format(**ctxt)
        s = Template().tag(interp_enabled=False)

    class C4(HasTraits):
        s = Template()

    assert C1(s=s).s == exp
    assert C2(s=s).s == exp
    assert C3(s=s).s == s
    assert C4(s=s).s == s

    for c in [C1, C2, C3, C4]:
        c.s.tag(interp_enabled=False)

    assert C1(s=s).s == s
    assert C2(s=s).s == s
    assert C3(s=s).s == s
    assert C4(s=s).s == s

    for c in [C1, C2, C3, C4]:
        c.s.tag(interp_enabled=True)

    assert C1(s=s).s == exp
    assert C2(s=s).s == exp
    assert C3(s=s).s == exp
    assert C4(s=s).s == s


def test_dates_interpolation():
    class C(HasTraits):
        interpolation = {'now': Now()}
        s = Template('stop the clock at {now}!')

    now_frmt = '{now:%Y-%m-%d %H:%M}'

    assert C().s != C.s.default_value
    assert C(s=now_frmt).s != now_frmt


def test_InterpContext():
    ctxt = InterpContext().ctxt

    s = 'stop the clock at {now}!'
    assert s.format(**ctxt) != s

    assert 'Keys we have: {ikeys}'.format(**ctxt) != 'Keys we have: {ikeys}'

    ctxt['A'] = '42'
    assert 'What? {A}'.format(**ctxt) == 'What? 42'
