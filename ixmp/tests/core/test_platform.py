"""Test all functionality of ixmp.Platform."""
import logging

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from pytest import raises

import ixmp


def test_init():
    with pytest.raises(ValueError, match="backend class 'foo' not among "
                                         r"\['jdbc'\]"):
        ixmp.Platform(backend='foo')


@pytest.fixture
def log_level_mp(test_mp):
    """A fixture that preserves the log level of *test_mp*."""
    tmp = test_mp.get_log_level()
    yield test_mp
    test_mp.set_log_level(tmp)


@pytest.mark.parametrize('level, exc', [
    ('CRITICAL', None),
    ('ERROR', None),
    ('WARNING', None),
    ('INFO', None),
    ('DEBUG', None),
    ('NOTSET', None),
    # An unknown string fails
    ('FOO', ValueError),
    # TODO also support Python standard library values
    (logging.CRITICAL, ValueError),
    (logging.ERROR, ValueError),
    (logging.WARNING, ValueError),
    (logging.INFO, ValueError),
    (logging.DEBUG, ValueError),
    (logging.NOTSET, ValueError),
])
def test_log_level(log_level_mp, level, exc):
    """Log level can be set and retrieved."""
    if exc is None:
        log_level_mp.set_log_level(level)
        assert log_level_mp.get_log_level() == level
    else:
        with pytest.raises(exc):
            log_level_mp.set_log_level(level)


def test_scenario_list(mp):
    scenario = mp.scenario_list(model='Douglas Adams')['scenario']
    assert scenario[0] == 'Hitchhiker'


def test_export_timeseries_data(mp, tmp_path):
    path = tmp_path / 'export.csv'
    mp.export_timeseries_data(path, model='Douglas Adams')

    with open(path) as f:
        first_line = f.readline()
        assert first_line == ('MODEL,SCENARIO,VERSION,VARIABLE,UNIT,'
                              'REGION,META,SUBANNUAL,YEAR,VALUE\n')
        assert len(f.readlines()) == 2


def test_unit_list(test_mp):
    units = test_mp.units()
    assert ('cases' in units) is True


def test_add_unit(test_mp):
    test_mp.add_unit('test', 'just testing')


def test_regions(test_mp):
    regions = test_mp.regions()

    # Result has the expected columns
    columns = ['region', 'mapped_to', 'parent', 'hierarchy']
    assert all(regions.columns == columns)

    # One row is as expected
    obs = regions[regions.region == 'World']
    assert all([list(obs.loc[0]) == ['World', None, 'World', 'common']])


def test_add_region(test_mp):
    # Region can be added
    test_mp.add_region('foo', 'bar', 'World')

    # Region can be retrieved
    regions = test_mp.regions()
    obs = regions[regions['region'] == 'foo'].reset_index(drop=True)
    assert all([list(obs.loc[0]) == ['foo', None, 'World', 'bar']])


def test_add_region_synonym(test_mp):
    test_mp.add_region('foo', 'bar', 'World')
    test_mp.add_region_synonym('foo2', 'foo')
    regions = test_mp.regions()
    obs = regions[regions.region.isin(['foo', 'foo2'])] \
        .reset_index(drop=True)

    exp = pd.DataFrame([
        ['foo', None, 'World', 'bar'],
        ['foo2', 'foo', 'World', 'bar'],
    ],
        columns=['region', 'mapped_to', 'parent', 'hierarchy']
    )
    assert_frame_equal(obs, exp)


def test_timeslices(test_mp):
    timeslices = test_mp.timeslices()
    obs = timeslices[timeslices.category == 'Common']
    # result has all attributes of time slice
    assert all(obs.columns == ['name', 'category', 'duration'])
    # result contains pre-defined YEAR time slice
    assert all([list(obs.iloc[0]) == ['Year', 'Common', 1.0]])


def test_add_timeslice(test_mp):
    test_mp.add_timeslice('January, 1st', 'Days',
                          1.0 / 366)
    timeslices = test_mp.timeslices()
    obs = timeslices[timeslices.category == 'Days']
    # return only added time slice
    assert len(obs) == 1
    # returned time slice attributes have expected values
    assert all([list(obs.iloc[0]) == ['January, 1st', 'Days',
                                      1.0 / 366]])


def test_add_timeslice_duplicate_raise(test_mp):
    test_mp.add_timeslice('foo_slice', 'foo_category', 0.2)
    # adding same name with different duration raises an error
    with raises(ValueError, match='timeslice `foo_slice` already defined with '
                                  'duration 0.2'):
        test_mp.add_timeslice('foo_slice', 'bar_category', 0.3)
