"""Scenario reporting."""
# The implementation uses the dask graph specfication; see
# http://docs.dask.org/en/latest/spec.html
#
# TODO meet the requirements:
# A8iii. Read CLI arguments for subset reporting.
# A9. Handle units for quantities.
# A11. Callable through `retixmp`.
from functools import partial

from dask.threaded import get as dask_get

from .utils import Key
from . import computations
from .computations import (   # noqa:F401
    disaggregate_shares,
    load_file,
)


class Reporter(object):
    """Reporter.

    A Reporter is used to postprocess data from from one or more
    :class:`ixmp.Scenario` objects. :meth:`get` can be used to:
    - Generate an entire *report* composed of multiple quantities. Generating a
      report may trigger output to file(s) or a database.
    - Retrieve individual quantities from a Scenario.

    """
    # TODO meet the requirements:
    # A2. Use exogenous data: given programmatically; from file.
    # A3i. Weighted sums.
    # A3iii. Interpolation.
    # A6. Duplicate or clone existing operations for multiple other sets of
    #     inputs or outputs. [Sub-graph manipulations.]
    # A7. Renaming of outputs.
    # A10. Provide description of how quantities are computed.

    def __init__(self):
        self.graph = {}

    @classmethod
    def from_scenario(cls, scenario):
        """Create a Reporter by introspecting *scenario*.

        The reporter will contain:
        - Every parameter in the *scenario* and all possible aggregations
          across different dimensions.
        """
        # New Reporter
        rep = cls()

        for par in scenario.par_list():
            # TODO retrieve parameter name, dims, and data
            name = NotImplementedError
            dims = NotImplementedError
            data = NotImplementedError

            # Add the parameter itself
            base_key = Key(name, dims)
            cls.add(base_key, data)

            # Add aggregates
            cls.graph.update(base_key.aggregates())

        # TODO add sets, scalars, and equations

        return rep

    # Generic graph manipulations
    def add(self, key, computation, strict=False):
        """Add *computation* to the Reporter under *key*.

        :meth:`add` may be used to:
        - Provide an alias from one *key* to another:

          >>> r.add('aliased name', 'original name')

        - Define an arbitrarily complex computation that operates directly on
          the :class:`ismp.Scenario` being reported:

          >>> def my_report(scenario):
          >>>     # many lines of code
          >>> r.add('my report', (my_report, 'scenario'))
          >>> r.finalize(scenario)
          >>> r.get('my report')

        Parameters
        ----------
        key: hashable
            A string, Key, or other value identifying the output of *task*.
        computation: object
            One of:
            1. any existing *key* in the Reporter.
            2. any other literal value or constant.
            3. a task, i.e. a tuple with a callable followed by one or more
               computations.
            4. A list containing one or more of #1, #2, and/or #3.
        strict : bool, optional
            If True (default), *key* must not already exist in the Reporter.
        """
        if strict and key in self.graph:
            raise KeyError(key)
        self.graph[key] = computation

    def get(self, key):
        """Execute and return the result of the computation *key*.

        Only *key* and its dependencies are computed.
        """
        return dask_get(self.graph, key)

    def finalize(self, scenario):
        """Prepare the Reporter to act on *scenario*."""
        self.graph['scenario'] = scenario

    # ixmp data model manipulations
    def disaggregate(self, var, new_dim, method='shares', args=[]):
        """Add a computation that disaggregates *var* using *method*.

        Parameters
        ----------
        var: hashable
            Key of the variable to be disaggregated.
        new_dim: str
            Name of the new dimension of the disaggregated variable.
        method: callable or str
            Disaggregation method. If a callable, then it is applied to *var*
            with any extra *args*. If then a method named
            'disaggregate_{method}' is used.
        args: list, optional
            Additional arguments to the *method*. The first element should be
            the key for a quantity giving shares for disaggregation.
        """
        # Compute the new key
        key = Key.from_str_or_key(var)
        key._dims.append(new_dim)

        # Get the method
        if isinstance(method, str):
            try:
                method = getattr(computations,
                                 'disaggregate_{}'.format(method))
            except AttributeError:
                raise ValueError("No disaggregation method 'disaggregate_{}'"
                                 .format(method))
        if not callable(method):
            raise ValueError(method)

        self.graph[key] = tuple([method, var] + args)

    # Convenience methods
    def add_file(self, path):
        self.add('file:{}'.format(path), (partial(load_file, path),))