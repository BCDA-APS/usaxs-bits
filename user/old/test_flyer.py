# raise RuntimeError("Work-in-progress, do not use yet")
# %matplotlib auto
from apstools.devices import EpicsOnOffShutter
from apstools.devices import make_dict_device
from apstools.devices import ScalerMotorFlyer
from bluesky import plan_stubs as bps
from bluesky import plans as bp
from bluesky import preprocessors as bpp
from bluesky import RunEngine
from bluesky.callbacks.best_effort import BestEffortCallback
from matplotlib import pyplot as plt
from ophyd import EpicsMotor
from ophyd.scaler import ScalerCH
import databroker

cat = databroker.catalog["20idb_usaxs"].v2
plt.ion()  # enables matplotlib graphics
RE = RunEngine({})
RE.subscribe(cat.v1.insert)
best_effort_callback = BestEffortCallback()
RE.subscribe(best_effort_callback)  # LivePlot & LiveTable

a2rp = EpicsMotor("usxLAX:pi:c0:m1", name="a2rp")
ar = EpicsMotor("usxAERO:m6", name="ar")
mr = EpicsMotor("usxAERO:m12", name="mr")
scaler1 = ScalerCH("usxLAX:vsc:c0", name="scaler1")
shutter = EpicsOnOffShutter("usxLAX:userTran3.A", name="shutter")  # ti_filter_shutter

for o in (mr, ar, a2rp, scaler1, shutter):
    o.wait_for_connection()
scaler1.select_channels()


class MyScalerMotorFlyer(ScalerMotorFlyer):

    tolerance = 1

    def _action_taxi(self):
        """Move motor to start position."""
        self.mode.put("taxi")
        self.status_taxi = self._motor.move(self._pos_start, wait=False)
        self.status_taxi.wait()

        # arrived to within motor's precision?
        if abs(self._motor.position - self._pos_start) > self.tolerance:
            raise RuntimeError(
                "Not in requested taxi position within tolerance:"
                f" requested={self._pos_start}"
                f" position={self._motor.position}"
                f" precision={self.tolerance}"
            )

    def _action_fly(self):
        """
        Start the fly scan and wait for it to complete.

        Data will be accumulated in response to CA monitor events from the
        scaler.
        """
        self.mode.put("fly")

        # set the fly scan velocity
        velocity = abs(self._pos_finish - self._pos_start) / self._fly_time
        if velocity != self._motor.velocity.get():
            self._original_values.remember(self._motor.velocity)
            self._motor.velocity.put(velocity)

        # make the scaler idle
        self._original_values.remember(self._scaler.count)
        self._original_values.remember(self._scaler.count_mode)
        self._scaler.count_mode.put("OneShot")  # turn off auto count mode
        self._scaler.count.put("Done")  # stop the scaler from counting

        # set the scaler count time (allowance)
        self._original_values.remember(self._scaler.preset_time)
        count_time_allowance = self._fly_time + self._scaler_time_pad
        self._scaler.preset_time.put(count_time_allowance)

        # start acquiring, scaler update rate was set in _action_setup()
        self._scaler.time.subscribe(self._action_acquire_event)  # CA monitor

        # start scaler counting, THEN motor moving
        self._scaler.count.put("Count")
        self.status_fly = self._motor.move(self._pos_finish, wait=False)

        # wait for motor to be done moving
        motion_time_allowance = self._fly_time + self._fly_time_pad
        self.status_fly.wait(timeout=motion_time_allowance)
        self._action_acquire_event()  # last event

        self._scaler.count.put("Done")  # stop scaler counting
        self._scaler.time.unsubscribe_all()  # stop acquiring


def fly_with_stats(flyers, *, md=None):
    """Replaces bp.fly(), adding stream for channel stats."""

    @bpp.stage_decorator(flyers)
    @bpp.run_decorator(md=md)
    @bpp.stub_decorator()
    def _inner_fly():
        yield from bp.fly(flyers)
        for flyer in flyers:
            if hasattr(flyer, "stats") and isinstance(flyer.stats, dict):
                yield from _flyer_stats_stream(flyer, f"{flyer.name}_stats")

    def _flyer_stats_stream(flyer, stream=None):
        """Output stats from this flyer into separate stream."""
        yield from bps.create(name=stream or f"{flyer.name}_stats")
        for ch in list(flyer.stats.keys()):
            yield from bps.read(
                make_dict_device(
                    {
                        # fmt: off
                        stat: v
                        for stat, v in flyer.stats[ch].to_dict().items()
                        if v is not None
                        # fmt: on
                    },
                    name=ch
                )
            )
        yield from bps.save()

    yield from _inner_fly()


def my_fly_plan(
    scaler, motor, start, finish,
    fly_time=10.0, period=0.5,
    fly_time_pad=2, scaler_time_pad=2,
    tolerance=1,
    name="flyer", md={}
):
    """
    my_fly_plan: Continuous motion scan of scaler v motor at constant velocity.

    Parameters

    ``scaler`` scaler:
        Instance of ``ophyd.scaler.ScalerCH``
    ``motor`` motor:
        Instance of ``ophyd.EpicssMotor``
    ``start`` number:
        Starting position for the _fly_ scan.
    ``finish`` number:
        Final position for the _fly_ scan.
    ``fly_time`` number:
        Time (seconds) for the fly scan to collect data.
        Default value: 10.0
    ``period`` number:
        Time (seconds) between individual data collections.
        Default value: 0.5
    ``fly_time_pad`` number:
        Extra time (seconds) to allow for the motor motion to complete before declaring a timeout.
        Default value: 2
    ``scaler_time_pad`` number:
        Extra time (seconds) to allow for the scaler to run before declaring a timeout.
        Default value: 2
    ``tolerance`` number:
        Acceptable difference value ``|readback - setpoint|`` to consider
        when setpoint position has been reached.
        Default value: 1
    ``name`` str:
        Name for the flyer object.
        Default value: ``flyer``
    ``md`` dict:
        Dictionary of metadata.
    """
    flyer = MyScalerMotorFlyer(
        scaler, motor, start, finish,
        fly_time=fly_time, period=period,
        fly_time_pad=fly_time_pad, scaler_time_pad=scaler_time_pad,
        name=name
    )
    flyer.tolerance = tolerance

    uid = None
    try:
        yield from bps.mv(shutter, "open")
        uid = yield from fly_with_stats([flyer], md=md)
    finally:
        yield from bps.mv(shutter, "close")
    return uid


# uids = RE(my_fly_plan(scaler1, mr, 7.7300, 7.7315, fly_time=5, period=0.2, md=dict(title="test new ScalerMotorFlyer()")))
