"""
local, custom Device definitions
"""

# from ophyd.log import config_ophyd_logging
# config_ophyd_logging(level="DEBUG")
#     # 'ophyd' — the logger to which all ophyd log records propagate
#     # 'ophyd.objects' — logs records from all devices and signals (that is, OphydObject subclasses)
#     # 'ophyd.control_layer' — logs requests issued to the underlying control layer (e.g. pyepics, caproto)
#     # 'ophyd.event_dispatcher' — issues regular summaries of the backlog of updates from the control layer that are being processed on background threads

from .aps_source import *
from .aps_undulator import *

from .override_parameters import *
from .constants import *
from .general_terms import *
from .sample_data import *
# TODO : bss code needs fixing. 
# from .user_data import *

from .scalers import *
from .motorsLAX import *
from .stages import *
from .emails import *
from .filters import *
from .shutters import *
# from .autosave import *
# from .axis_tuning import *
from .diagnostics import *
# from .emails import *
from .filters import *
# from .linkam import *
# from .miscellaneous import *
from .monochromator import *
# from .sample_rotator import *
from .slits import *
from .struck3820 import *
from .suspenders import *
from .trajectories import *
from .usaxs_fly_scan import *
# from .laser import *# from .noisy_detector import *
# from .shutter_simulator import *
# from .temperature_signal import *

from .amplifiers import *

# finally these area detectors
# from .alta_module import *
from .blackfly_module import *
# from .dexela_module import *
from .pilatus_module import *

# old load order from 20ID:
# from .aps_source import *
# from .permit import *

# from .override_parameters import *
# from .constants import *
# from .general_terms import *
# from .sample_data import *
# from .user_data import *

# # do these first
# from .scalers import *
# from .shutters import *
# from .stages import *

# # then these
# from .amplifiers import *
# from .autosave import *
# from .axis_tuning import *
# from .diagnostics import *
# from .emails import *
# from .filters import *
# from .linkam import *
# from .miscellaneous import *
# from .monochromator import *
# # from .protection_plc import *
# from .sample_rotator import *
# from .slits import *
# from .struck3820 import *
# from .suspenders import *
# from .trajectories import *
# from .usaxs_fly_scan import *
# from .laser import *

# # finally these area detectors
# from .alta_module import *
# from .blackfly_module import *
# from .dexela_module import *
# from .pilatus_module import *
# # from .simdetector import *

# # and only when all devices are defined
# from .autocollect import *

