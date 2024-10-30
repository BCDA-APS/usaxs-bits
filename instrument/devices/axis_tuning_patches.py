
"""
2020-05-30: patches for TuneAxis
"""

__all__ = [
    "UsaxsTuneAxis",
    ]

import logging

logger = logging.getLogger(__name__)
logger.info(__file__)


from apstools.devices import AxisTunerMixin
from apstools.plans import TuneAxis
from bluesky import plans as bp
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from bluesky.callbacks.fitting import PeakStats
import datetime
import numpy as np
from ophyd import Component, Device, Signal
from ophyd import EpicsMotor
import pyRestTable


class TuningResults(Device):
    """
    Results of a tune scan
    because bps.read() needs a Device or a Signal
    """
    tune_ok = Component(Signal)
    initial_position = Component(Signal)
    final_position = Component(Signal)
    center = Component(Signal)
    # - - - - -
    x = Component(Signal)
    y = Component(Signal)
    cen = Component(Signal)
    com = Component(Signal)
    fwhm = Component(Signal)
    min = Component(Signal)
    max = Component(Signal)
    crossings = Component(Signal)
    peakstats_attrs = "x y cen com fwhm min max crossings".split()

    def report(self, title=None, print_enable=True):
        keys = self.peakstats_attrs + "tune_ok center initial_position final_position".split()
        t = pyRestTable.Table()
        t.addLabel("key")
        t.addLabel("result")
        for key in keys:
            v = getattr(self, key).get()
            t.addRow((key, str(v)))
        if print_enable:
            if title is not None:
                print(title)
            print(t)
        return t

    def put_results(self, peaks):
        """copy values from PeakStats"""
        for key in self.peakstats_attrs:
            v = getattr(peaks, key)
            if key in ("crossings", "min", "max"):
                v = np.array(v)
            getattr(self, key).put(v)


class UsaxsTuneAxis(TuneAxis):
    """use bp.rel_scan() for the tune()"""

    width_signal = None
    _width_default = 1      # fallback default when width_signal is None

    def __init__(self, signals, axis, signal_name=None,
                 width_signal=None):
        """
        Adds to the ``apstools.devices.TuneAxis()`` signature

        signal_width (obj):
            Instance of `ophyd.EpicsSignal` connected to PV
            with default tune width for this axis.

            If undefined (set to ``None``), then a private attribute
            (``_width_default``) will be used for the value.
        """
        super().__init__(signals, axis, signal_name=signal_name)
        self.width_signal = width_signal

    @property
    def width(self):
        """Get default tune width for this axis."""
        if self.width_signal is None:
            return self._width_default
        else:
            return self.width_signal.get()

    @width.setter
    def width(self, value):
        """
        Set the width PV value - blocking call, not a plan.

        To set the width PV in a plan, use ``yield from bps.mv(self.width_signal, value)``.

        CAUTION:  Do NOT call this setter from a bluesky plan!
        """
        if self.width_signal is None:
            self._width_default = value
        else:
            self.width_signal.put(value)

    def peak_analysis(self, initial_position):
        if self.peak_detected():
            self.tune_ok = True
            if self.peak_choice == "cen":
                final_position = self.peaks.cen
            elif self.peak_choice == "com":
                final_position = self.peaks.com
            else:
                final_position = None
            self.center = final_position
        else:
            self.tune_ok = False
            final_position = initial_position

        yield from bps.mv(self.axis, final_position)

        stream_name = "PeakStats"
        results = TuningResults(name=stream_name)

        results.tune_ok.put(self.tune_ok)
        results.center.put(self.center)
        results.final_position.put(final_position)
        results.initial_position.put(initial_position)
        if self.peaks is None:
            logger.info("PeakStats object is None.")
            results.put_results({})
        else:
            results.put_results(self.peaks)
        self.stats.append(results)

        t = results.report(print_enable=False)
        logger.info("%s\n%s", stream_name, str(t))

    def tune(self, width=None, num=None, md=None):
        """
        Bluesky plan to execute one pass through the current scan range

        Scan self.axis centered about current position from
        ``-width/2`` to ``+width/2`` with ``num`` observations.
        If a peak was detected (default check is that max >= 4*min),
        then set ``self.tune_ok = True``.
        PARAMETERS

        width : float
            width of the tuning scan in the units of ``self.axis``
            Default value in ``self.width`` (initially 1)
        num : int
            number of steps
            Default value in ``self.num`` (initially 10)
        md : dict, optional
            metadata
        """
        width = width or self.width
        num = num or self.num

        if self.peak_choice not in self._peak_choices_:
            raise ValueError(
                f"peak_choice must be one of {self._peak_choices_},"
                f" gave {self.peak_choice}"
            )

        initial_position = self.axis.position
        start = initial_position - width/2
        finish = initial_position + width/2
        self.tune_ok = False

        signal_list = list(self.signals)
        signal_list += [self.axis,]

        tune_md = dict(
            width = width,
            initial_position = self.axis.position,
            time_iso8601 = str(datetime.datetime.now()),
            )
        _md = {'tune_md': tune_md,
               'plan_name': self.__class__.__name__ + '.tune',
               'tune_parameters': dict(
                    num = num,
                    width = width,
                    initial_position = self.axis.position,
                    peak_choice = self.peak_choice,
                    x_axis = self.axis.name,
                    y_axis = self.signal_name,
                   ),
               'motors': (self.axis.name,),
               'detectors': (self.signal_name,),
               'hints': dict(
                   dimensions = [
                       (
                           [self.axis.name],
                           'primary')]
                   )
               }
        _md.update(md or {})

        if "pass_max" not in _md:
            self.stats = []

        self.peaks = PeakStats(x=self.axis.name, y=self.signal_name)

        @bpp.subs_decorator(self.peaks)
        def _scan(md=None):
            yield from bp.scan(signal_list, self.axis, start, finish, num, md=_md)
            yield from self.peak_analysis(initial_position)

        yield from _scan()

    def multi_pass_tune(self, width=None, step_factor=None,
                        num=None, pass_max=None, snake=None, md=None):
        """
        BlueSky plan for tuning this axis with this signal

        Execute multiple passes to refine the centroid determination.
        Each subsequent pass will reduce the width of scan by ``step_factor``.
        If ``snake=True`` then the scan direction will reverse with
        each subsequent pass.
        PARAMETERS

        width : float
            width of the tuning scan in the units of ``self.axis``
            Default value in ``self.width`` (initially 1)
        num : int
            number of steps
            Default value in ``self.num`` (initially 10)
        step_factor : float
            This reduces the width of the next tuning scan by the given factor.
            Default value in ``self.step_factor`` (initially 4)
        pass_max : int
            Maximum number of passes to be executed (avoids runaway
            scans when a centroid is not found).
            Default value in ``self.pass_max`` (initially 10)
        snake : bool
            If ``True``, reverse scan direction on next pass.
            Default value in ``self.snake`` (initially True)
        md : dict, optional
            metadata
        """
        width = width or self.width
        num = num or self.num
        step_factor = step_factor or self.step_factor
        snake = snake or self.snake
        pass_max = pass_max or self.pass_max

        self.stats = []

        def _scan(width=1, step_factor=10, num=10, snake=True):
            for _pass_number in range(pass_max):
                _md = {'pass': _pass_number+1,
                       'pass_max': pass_max,
                       'plan_name': self.__class__.__name__ + '.multi_pass_tune',
                       }
                _md.update(md or {})

                yield from self.tune(width=width, num=num, md=_md)

                if not self.tune_ok:
                    break
                width /= step_factor
                if snake:
                    width *= -1

            t = pyRestTable.Table()
            t.labels = "pass Ok? center width max.X max.Y".split()
            for i, stat in enumerate(self.stats):
                row = [i+1,]
                row.append(stat.tune_ok.get())
                row.append(stat.cen.get())
                row.append(stat.fwhm.get())
                x, y = stat.max.get()
                row += [x, y]
                t.addRow(row)
            logger.info("Results\n%s", str(t))
            logger.info("Final tune position: %s = %f", self.axis.name, self.axis.position)

        return (
            yield from _scan(
                width=width,
                step_factor=step_factor,
                num=num,
                snake=snake))

    def peak_detected(self):
        """
        returns True if a peak was detected, otherwise False

        The default algorithm identifies a peak when the maximum
        value is four times the minimum value.  Change this routine
        by subclassing :class:`TuneAxis` and override :meth:`peak_detected`.
        """
        if self.peaks is None:
            logger.info("PeakStats = None")
            return False
        self.peaks.compute()
        if self.peaks.max is None:
            logger.info("PeakStats : no max reported")
            return False

        ymax = self.peaks.max[-1]
        ymin = self.peaks.min[-1]
        ok = ymax > 4*ymin        # this works for USAXS@APS
        if not ok:
            logger.info("ymax/yman not big enough: is it a peak?")
        return ok
