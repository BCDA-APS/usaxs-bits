"""
user reconfiguration of various USAXS parameters
"""

import pyRestTable


class UserOverride:
    """
    Define parameters that can be overriden from a user configuration file.

    These parameters are supported in other code used by this instrument.

    =============== ============================
    method          usage
    =============== ============================
    ``register()``  First, register a new parameter name to be supported by user overrides.
    ``set()``       Define an override value for a known parameter.
    ``pick()``      Choose value for a known parameter, picking between override and default value.
    ``summary()``   Print a table of all known parameters and values.
    ``reset()``     Remove an override value for a known parameter.  (sets it to undefined)
    ``reset_all()`` Remove override values for all known parameters.
    =============== ============================

    Refer to ``plans.axis_tuning`` for example back-end
    handling.  Such as::

        user_override.register("usaxs_minstep")

    Then later::

        minstep = user_override.pick("usaxs_minstep", 0.000045)

    In the ``BS_conf.py`` file, import the `user_override`` object::

        from instrument.devices import user_override

    and then override the attribute(s) as desired::

        user_override.set("usaxs_minstep", 1.0e-5)
    """

    def __init__(self):
        # ALWAYS use ``user_override.undefined`` for comparisons and resets.
        self.undefined = object()
        self._parameters = {}

    def register(self, parameter_name):
        """
        Register a new parameter name.
        """
        if parameter_name not in self._parameters:
            self._parameters[parameter_name] = self.undefined

    def set(self, parameter_name, value):
        """
        Set value of a known parameter.
        """
        if parameter_name not in self._parameters:
            raise KeyError(
                f"Unknown {parameter_name = }.  Should call register() first."
            )
        self._parameters[parameter_name] = value

    def reset(self, parameter_name):
        """
        Remove the override of a known parameter.
        """
        if parameter_name not in self._parameters:
            raise KeyError(
                f"Unknown {parameter_name = }.  Should call register() first."
            )
        self._parameters[parameter_name] = self.undefined

    def reset_all(self):
        """
        Change all override values back to undefined.
        """
        for parm in self._parameters.keys():
            self.reset(parm)

    def pick(self, parameter, default):
        """
        Either pick the override parameter value if defined, or the default.
        """
        value = self._parameters.get(parameter, default)
        if value == self.undefined:
            value = default
        return value

    def summary(self):
        """
        Print a table summarizing the overrides.

        Parameter names that have no override value will be reported
        as ``--undefined--`.
        """
        tbl = pyRestTable.Table()
        tbl.labels = "parameter value".split()
        methods = "pick reset summary undefined".split()
        for parm in sorted(self._parameters.keys()):
            tbl.addRow((parm, self.pick(parm, "--undefined--")))
        print(tbl)


user_override = UserOverride()
