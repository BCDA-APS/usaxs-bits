#!/usr/bin/env python

"""
Step-Size Algorithm for Bonse-Hart Ultra-Small-Angle Scattering Instruments

:see: https://www.jemian.org/SAS/ustep.pdf
"""


class Ustep(object):
    r"""
    find the series of positions for the USAXS

    :param float start: required first position of list
    :param float center: position to take minStep
    :param float finish: required ending position of list
    :param float numPts: length of the list
    :param float exponent: :math:`\eta`, exponential factor
    :param float minStep: smallest allowed step size
    :param float factor: :math:`k`, multiplying factor (computed internally)

    EXAMPLE:

        start = 10.0
        center = 9.5
        finish = 7
        numPts = 100
        exponent = 1.2
        minStep = 0.0001

        ar_positions_step = Ustep(start, center, finish, numPts, exponent, minStep)
        ar_positions = ar_positions_step.series
        ar_trajectory = cycler(ar, ar_positions)

        # ay_positions = make_ay_positions(ar_positions)
        # dy_positions = make_dy_positions(ar_positions)
        ay_trajectory = cycler(ay, ay_positions)
        dy_trajectory = cycler(dy, dy_positions)

        # step these motors together
        motor_trajectory = ar_trajectory + ay_trajectory + dy_trajectory

        RE(scan_nd([detector], motor_trajectory)

    """

    def __init__(self, filename):
        """Initialize the ustep configuration.

        Args:
            filename: Path to the configuration file
        """
        self.start = 10.0
        self.center = 9.5
        self.finish = 7
        self.numPts = 100
        self.exponent = 1.2
        self.minStep = 0.0001
        self.sign = {True: 1, False: -1}[self.start < self.finish]
        self.factor = self._find_factor_()

    def _find_factor_(self):
        """
        Determine the factor that will make a series with the specified parameters.

        Consider recent history when refining choice.
        """

        def assess_diff(factor):
            series = self.series(factor)
            diff = abs(series[0] - series[-1]) - span_target
            return diff

        span_target = abs(self.finish - self.start)
        span_precision = abs(self.minStep) * 0.2
        factor = abs(self.finish - self.start) / (self.numPts - 1)
        diff = assess_diff(factor)
        f = [factor, factor]
        d = [diff, diff]

        # first make certain that d[0] < 0 and d[1] > 0, expand f[0] and f[1]
        for _ in range(100):
            if d[0] * d[1] < 0:
                break  # now, d[0] and d[1] have opposite sign
            factor *= {True: 2, False: 0.5}[diff < 0]
            diff = assess_diff(factor)
            key = {True: 1, False: 0}[diff > d[1]]
            f[key] = factor
            d[key] = diff
            # print(
            #     f"expand: diff={diff} key={key} factor={factor} "
            #     f"last={self.series(factor)[-1]}"
            # )

        # now: d[0] < 0 and d[1] > 0, squeeze f[0] & f[1] to converge
        for _ in range(100):
            if (d[1] - d[0]) > span_target:
                # bracket by bisection when not close
                factor = (f[0] + f[1]) / 2
            else:
                # linear interpolation when close
                factor = f[0] - d[0] * (f[1] - f[0]) / (d[1] - d[0])
            diff = assess_diff(factor)
            if abs(diff) <= span_precision:
                break
            key = {True: 0, False: 1}[diff < 0]
            f[key] = factor
            d[key] = diff
            # print(
            #     f"squeeze: diff={diff} key={key} factor={factor} "
            #     f"last={self.series(factor)[-1]}"
            # )

        return factor

    def stepper(self, factor=None):
        """
        generator: series of angle steps

        The ``factor`` argument is supplied internally.
        External callers of this method should leave it as ``None``.

        :param float factor: :math:`k`, multiplying factor (computed internally)
        """
        x = self.start
        for i in range(self.numPts):
            x += self.sign * self._calc_next_step_(x, factor or self.factor)
            if i == self.numPts - 1 and factor is None:
                yield self.finish
            else:
                yield x

    def series(self, factor=None):
        """
        create a series with the given factor

        The ``factor`` argument is supplied internally.
        External callers of this method should leave it as ``None``.

        :param float factor: :math:`k`, multiplying factor (computed internally)
        """
        return [x for x in self.stepper(factor)]

    def _calc_next_step_(self, x, factor):
        """
        Calculate the next step size with the given parameters
        """
        if abs(x - self.center) > 1e100:
            step = 1e100
        else:
            step = factor * pow(abs(x - self.center), self.exponent) + self.minStep
        return step


def main() -> None:
    """Run a demonstration of the Ustep class.

    This function creates a sample Ustep instance with predefined parameters
    and prints out the calculated step sequence.
    """
    start = 10.0
    center = 9.5
    finish = 7
    numPts = 100
    exponent = 1.2
    minStep = 0.0001
    u = Ustep(start, center, finish, numPts, exponent, minStep)

    print(f"factor={u.factor} for {len(u.series())} points")
    for i, angle in enumerate(u.stepper()):
        print(i, angle)


def get_ustep_config():
    """Get the ustep configuration.

    This function retrieves the current ustep configuration settings
    from the configuration file.

    Returns:
        dict: Dictionary containing ustep configuration settings
    """


if __name__ == "__main__":
    main()
