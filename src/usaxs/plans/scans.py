"""
user-facing scans
"""

import datetime
import logging
import os
import time
from collections import OrderedDict
from typing import Any
from typing import Dict
from typing import Optional

from .mono_feedback import MONO_FEEDBACK_OFF
from .mono_feedback import MONO_FEEDBACK_ON
from apsbits.core.instrument_init import oregistry
from apstools.devices import SCALER_AUTOCOUNT_MODE
from apstools.plans import restorable_stage_sigs
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp
from .axis_tuning import tune_mr
from .axis_tuning import tune_ar
from .axis_tuning import tune_a2rp
from usaxs.startup import suspend_BeamInHutch
from usaxs.startup import suspend_FE_shutter
from usaxs.utils.emails import email_notices
from usaxs.utils.override_parameters import user_override
from .requested_stop import IfRequestedStopBeforeNextScan
from .mode_changes import mode_USAXS
from ..utils.a2q_q2a import q2angle
from .command_list import after_plan
from .command_list import before_plan
from .mode_changes import mode_USAXS
from .mode_changes import mode_SAXS
from .mode_changes import mode_WAXS
from .requested_stop import IfRequestedStopBeforeNextScan 
from .sample_transmission import measure_SAXS_Transmission
from .sample_transmission import measure_USAXS_Transmission
from .filter_changes import insertSaxsFilters
from .filter_changes import insertWaxsFilters
from .area_detector import areaDetectorAcquire
from .amplifiers import autoscale_amplifiers
from .I0_controls import I0_controls
from .I00_controls import I00_controls
from .upd_controls import upd_controls
from .trd_controls import trd_controls
from .sample_imaging import record_sample_image_on_demand


# from usaxs.utils.setup_new_user import cleanupText
# from usaxs.utils.setup_new_user import techniqueSubdirectory
# from usaxs.utils.user_sample_title import getSampleTitle

# # Constants
# tune_m2rp = oregistry["tune_m2rp"]
# tune_ar = oregistry["tune_ar"]
# tune_a2rp = oregistry["tune_a2rp"]
# NOTIFY_ON_BADTUNE = oregistry["NOTIFY_ON_BADTUNE"]

# tune_mr = oregistry["tune_mr"]
# uascan = oregistry["uascan"]
# NOTIFY_ON_BAD_FLY_SCAN = oregistry["NOTIFY_ON_BAD_FLY_SCAN"]

logger = logging.getLogger(__name__)


# # these two templates match each other, sort of
# AD_FILE_TEMPLATE = "%s%s_%4.4d.hdf"
# LOCAL_FILE_TEMPLATE = "%s_%04d.hdf"
MASTER_TIMEOUT = 60
# user_override.register("useDynamicTime")

# # Make sure these are not staged. For acquire_time,
# # any change > 0.001 s takes ~0.5 s for Pilatus to complete!
# DO_NOT_STAGE_THESE_KEYS___THEY_ARE_SET_IN_EPICS = """
#     acquire_time acquire_period num_images num_exposures
# """.split()

# # Device and plan instances from oregistry (allowed list)
mono_shutter = oregistry["mono_shutter"]
usaxs_shutter = oregistry["usaxs_shutter"]
# usaxs_shutter = oregistry["usaxs_shutter"]
# ar_start = oregistry["ar_start"]
guard_slit = oregistry["guard_slit"]
# lax_autosave = oregistry["lax_autosave"]
# m_stage = oregistry["m_stage"]
monochromator = oregistry["monochromator"]
terms = oregistry["terms"]
s_stage = oregistry["s_stage"]
# saxs_det = oregistry["saxs_det"]
# saxs_stage = oregistry["saxs_stage"]
# struck = oregistry["struck"]
# terms = oregistry["terms"]
# usaxs_flyscan = oregistry["usaxs_flyscan"]
# usaxs_q_calc = oregistry["usaxs_q_calc"]
usaxs_slit = oregistry["usaxs_slit"]
user_data = oregistry["user_device"]
scaler0 = oregistry["scaler0"]
# waxs_det = oregistry["waxs_det"]
m_stage = oregistry["m_stage"]
a_stage = oregistry["a_stage"]
d_stage = oregistry["d_stage"]
# flyscan_trajectories = oregistry["flyscan_trajectories"]
# # Plan helpers (if available in oregistry)
# mode_USAXS = oregistry["mode_USAXS"]
# mode_SAXS = oregistry["mode_SAXS"]
# mode_WAXS = oregistry["mode_WAXS"]
# record_sample_image_on_demand = oregistry["record_sample_image_on_demand"]
# measure_USAXS_Transmission = oregistry["measure_USAXS_Transmission"]
# measure_SAXS_Transmission = oregistry["measure_SAXS_Transmission"]
# insertSaxsFilters = oregistry["insertSaxsFilters"]
# insertWaxsFilters = oregistry["insertWaxsFilters"]
# areaDetectorAcquire = oregistry["areaDetectorAcquire"]
# autoscale_amplifiers = oregistry["autoscale_amplifiers"]
# I0_controls = oregistry["I0_controls"]
# I00_controls = oregistry["I00_controls"]
# upd_controls = oregistry["upd_controls"]
# trd_controls = oregistry["trd_controls"]
# scaler0 = oregistry["scaler0"]
# scaler1 = oregistry["scaler1"]
# constants = oregistry["constants"]
 



