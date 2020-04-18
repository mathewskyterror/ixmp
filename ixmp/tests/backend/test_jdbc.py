import gc
import logging
from sys import getrefcount

import jpype
import pytest
from pytest import raises

import ixmp
from ixmp.testing import make_dantzig


def test_jvm_warn(recwarn):
    """Test that no warnings are issued on JVM start-up.

    A warning message is emitted e.g. for JPype 0.7 if the 'convertStrings'
    kwarg is not provided to jpype.startJVM.

    NB this function should be in test_core.py, but because pytest executes
    tests in file, then code order, it must be before the call to ix.Platform()
    below.
    """

    # Start the JVM for the first time in the test session
    from ixmp.backend.jdbc import start_jvm
    start_jvm()

    if jpype.__version__ > '0.7':
        # Zero warnings were recorded
        assert len(recwarn) == 0, recwarn.pop().message


def test_close(test_mp, capfd):
    """Platform.close_db() doesn't throw needless exceptions."""
    # Close once
    test_mp.close_db()

    # Close again, once already closed
    test_mp.close_db()

    captured = capfd.readouterr()
    msg = 'Database connection could not be closed or was already closed'
    assert msg in captured.out


def test_pass_properties():
    ixmp.Platform(driver='hsqldb', url='jdbc:hsqldb:mem://ixmptest',
                  user='ixmp', password='ixmp')


def test_invalid_properties_file(test_data_path):
    # HyperSQL creates a file with a .properties suffix for every file-based
    # database, but these files do not contain the information needed to
    # instantiate a database connection
    with pytest.raises(ValueError,
                       match='Config file contains no database URL'):
        ixmp.Platform(dbprops=test_data_path / 'hsqldb.properties')


def test_connect_message(capfd, caplog):
    msg = "connected to database 'jdbc:hsqldb:mem://ixmptest' (user: ixmp)..."

    ixmp.Platform(backend='jdbc', driver='hsqldb',
                  url='jdbc:hsqldb:mem://ixmptest')

    # Java code via JPype does not log to the standard Python logger
    assert not any(msg in m for m in caplog.messages)

    # Instead, log messages are printed to stdout
    captured = capfd.readouterr()
    assert msg in captured.out


@pytest.mark.parametrize('arg', [True, False])
def test_cache_arg(arg):
    """Test 'cache' argument, passed to CachingBackend."""
    mp = ixmp.Platform(backend='jdbc', driver='hsqldb',
                       url='jdbc:hsqldb:mem://test_cache_false',
                       cache=arg)
    scen = make_dantzig(mp)

    # Maybe put something in the cache
    scen.par('a')

    assert len(mp._backend._cache) == (1 if arg else 0)


def test_read_file(test_mp, tmp_path):
    be = test_mp._backend

    with pytest.raises(NotImplementedError):
        be.read_file(tmp_path / 'test.csv', ixmp.ItemType.ALL, filters={})


def test_write_file(test_mp, tmp_path):
    be = test_mp._backend

    with pytest.raises(NotImplementedError):
        be.write_file(tmp_path / 'test.csv', ixmp.ItemType.ALL, filters={})


# This variable formerly had 'warns' as the third element in some tuples, to
# test for deprecation warnings.
INIT_PARAMS = (
    # Handled in JDBCBackend:
    (['nonexistent.properties'], dict(), raises, ValueError, "platform name "
     r"'nonexistent.properties' not among \['default'"),
    (['nonexistent.properties'], dict(name='default'), raises, TypeError,
     None),
    # Using the dbtype keyword argument
    ([], dict(dbtype='HSQLDB'), raises, TypeError,
     r"JDBCBackend\(\) got an unexpected keyword argument 'dbtype'"),
    # Initialize with driver='oracle' and path
    ([], dict(backend='jdbc', driver='oracle', path='foo/bar'), raises,
     ValueError, None),
    # …with driver='oracle' and no url
    ([], dict(backend='jdbc', driver='oracle'), raises, ValueError, None),
    # …with driver='hsqldb' and no path
    ([], dict(backend='jdbc', driver='hsqldb'), raises, ValueError, None),
    # …with driver='hsqldb' and url
    ([], dict(backend='jdbc', driver='hsqldb', url='example.com:1234:SCHEMA'),
     raises, ValueError, None),
)


@pytest.mark.parametrize('args,kwargs,action,kind,match', INIT_PARAMS)
def test_init(tmp_env, args, kwargs, action, kind, match):
    """Semantics for JDBCBackend.__init__()."""
    with action(kind, match=match):
        ixmp.Platform(*args, **kwargs)


def test_gh_216(test_mp):
    scen = make_dantzig(test_mp)

    filters = dict(i=['seattle', 'beijing'])

    # Java code in ixmp_source would raise an exception because 'beijing' is
    # not in set i; but JDBCBackend removes 'beijing' from the filters before
    # calling the underlying method (https://github.com/iiasa/ixmp/issues/216)
    scen.par('a', filters=filters)


@pytest.fixture
def exception_verbose_true():
    """A fixture which ensures JDBCBackend raises verbose exceptions.

    The set value is not disturbed for other tests/code.
    """
    tmp = ixmp.backend.jdbc._EXCEPTION_VERBOSE  # Store current value
    ixmp.backend.jdbc._EXCEPTION_VERBOSE = True  # Ensure True
    yield
    ixmp.backend.jdbc._EXCEPTION_VERBOSE = tmp  # Restore value


def test_verbose_exception(test_mp, exception_verbose_true):
    # Exception stack trace is logged for debugging
    with pytest.raises(RuntimeError) as exc_info:
        ixmp.Scenario(test_mp, model='foo', scenario='bar', version=-1)

    exc_msg = exc_info.value.args[0]
    assert ("There exists no Scenario 'foo|bar' "
            "(version: -1)  in the database!" in exc_msg)
    assert "at.ac.iiasa.ixmp.database.DbDAO.getRunId" in exc_msg
    assert "at.ac.iiasa.ixmp.Platform.getScenario" in exc_msg


def test_del_ts():
    mp = ixmp.Platform(backend='jdbc', driver='hsqldb',
                       url=f'jdbc:hsqldb:mem:test_del_ts')

    # Number of Java objects referenced by the JDBCBackend
    N_obj = len(mp._backend.jindex)

    # Create a list of some Scenario objects
    N = 8
    scenarios = []
    for i in range(N):
        scenarios.append(
            ixmp.Scenario(mp, 'foo', f'bar{i}', version='new')
        )

    # Number of referenced objects has increased by 8
    assert len(mp._backend.jindex) == N_obj + N

    # Pop and free the objects
    for i in range(N):
        s = scenarios.pop(0)

        # The variable 's' is the only reference to this Scenario object
        assert getrefcount(s) - 1 == 1

        # ID of the Scenario object
        s_id = id(s)

        # Underlying Java object
        s_jobj = mp._backend.jindex[s]

        # Now delete the Scenario object
        del s

        # Number of referenced objects decreases by 1
        assert len(mp._backend.jindex) == N_obj + N - (i + 1)
        # ID is no longer in JDBCBackend.jindex
        assert s_id not in mp._backend.jindex

        # s_jobj is the only remaining reference to the Java object
        assert getrefcount(s_jobj) - 1 == 1
        del s_jobj

    # Backend is again empty
    assert len(mp._backend.jindex) == N_obj


@pytest.mark.performance
def test_gc_lowmem(request):  # prama: no cover
    """Test Java-side garbage collection (GC).

    By default, this test limits the JVM memory to 7 MiB. To change this limit,
    use the command-line option --jvm-mem-limit=7.
    """
    # NB coverage is omitted because this test is not included in the standard
    #    suite

    # Create a platform with a small memory limit (default 7 MiB)
    jvm_mem_limit = request.config.getoption('--jvm-mem-limit', 7)
    mp = ixmp.Platform(backend='jdbc', driver='hsqldb',
                       url=f'jdbc:hsqldb:mem:test_gc',
                       jvmargs=f'-Xmx{jvm_mem_limit}M')
    # Force Java GC
    jpype.java.lang.System.gc()

    def allocate_scenarios(n):
        for i in range(n):
            scenarios.append(
                ixmp.Scenario(mp, 'foo', f'bar{i}', version='new')
            )

    scenarios = []
    # Fill *scenarios* with Scenario object until out of memory
    raises(jpype.java.lang.OutOfMemoryError, allocate_scenarios, 100000)
    # Record the maximum number
    max = len(scenarios)

    # Clean up and GC Python and Java memory
    scenarios = []
    gc.collect()
    jpype.java.lang.System.gc()

    # Can allocate *max* scenarios again
    allocate_scenarios(max)
    # …but not twice as many
    raises(jpype.java.lang.OutOfMemoryError, allocate_scenarios, max)
