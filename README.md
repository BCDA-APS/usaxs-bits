# Bluesky code for USAXS instrument (APS-U, 12ide)

**Description** USAXS instrument web page : https://usaxs.xray.aps.anl.gov/ 

USAXS instrument old Bluesky code is here: https://github.com/APS-USAXS/usaxs-bluesky-ended-2023

New USAXS instrument is located at APS 12ID beamline, hutch E. This is code used for operations of this instrument and is specific to existing hardware. 

**Caution**:  If you will use the bluesky queueserver (QS), note that _every_
Python file in this directory will be executed when QS starts the RunEngine.
Don't add extra Python files to this directory.  Instead, put them in `user/` or
somewhere else.

Contains:

description | item(s)
--- | ---
Introduction | [`intro2bluesky.md`](https://bcda-aps.github.io/bluesky_training/reference/_intro2bluesky.html)
IPython console startup | [`console/`](console/README.md)
Bluesky queueserver support | [introduction](qserver.md), `*qs*`
Instrument configuration | `instrument/`
Conda environments | [`environments/`](./environments/README.md)
Unit tests | [`tests/`](./tests/README.md)
Documentation | [How-to, examples, tutorials, reference](https://bcda-aps.github.io/bluesky_training)
