# usaxs/suspenders/global_suspenders.py
"""Global suspenders for the beamline."""

# Module-level variables to store suspenders
_suspend_FE_shutter = None
_suspend_BeamInHutch = None

def set_suspenders(fe_shutter, beam_in_hutch):
    """Initialize the global suspenders."""
    global _suspend_FE_shutter, _suspend_BeamInHutch
    _suspend_FE_shutter = fe_shutter
    _suspend_BeamInHutch = beam_in_hutch

def get_suspend_FE_shutter():
    """Get the FE shutter suspender."""
    if _suspend_FE_shutter is None:
        raise RuntimeError("FE shutter suspender not initialized")
    return _suspend_FE_shutter

def get_suspend_BeamInHutch():
    """Get the BeamInHutch suspender."""
    if _suspend_BeamInHutch is None:
        raise RuntimeError("BeamInHutch suspender not initialized")
    return _suspend_BeamInHutch