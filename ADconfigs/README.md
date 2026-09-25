# ADconfigs — areaDetector and fly-scan IOC configuration

Configuration read by the IOCs, not by the `usaxs` Python package.  It lives
here so the **data formats are reviewable and version-controlled**; the IOCs
read it from `/share1/AreaDetectorConfig/`, so a change here has to be deployed
before it takes effect.

```
Flyscan_config/saveFlyData.xml   PV -> HDF5 map for the USAXS fly scan
Flyscan_config/saveFlyData.xsd   its schema; saveFlyData.py validates against it
SAXS_config/attributes.xml       NDAttributes baked into every Pilatus frame
SAXS_config/layout.xml           where those attributes land in the NeXus tree
WAXS_config/attributes.xml       same, for the Eiger
WAXS_config/layout_waxs.xml
WAXS_config/copy_attributes_to_template.py
```

## Which file does what

`attributes.xml` lists EPICS PVs to capture with each frame.  `layout.xml` has
`<group name="Metadata" ndattr_default="true">`, so **any attribute added to
`attributes.xml` appears under `/entry/Metadata` automatically** — a layout edit
is needed only for explicit placement, such as the
`/entry/control/integral` hardlink that carries the NXcanSAS monitor value.

Order matters in `attributes.xml`: all `EPICS_PV` entries, then `PARAM`, then
`FUNCTION`.  The file header says so and the AD plugin enforces it.

## Counting chain version

Every file declares which counting chain produced the data:

```xml
<dataset name="counting_chain" value="FX4" source="constant" type="string"/>
<dataset name="config_version" value="2.0" source="constant" type="string"/>
```

`FX4` means the detector values are **gain-independent picoamps**; absent or
`SCALER` means the old Femto/V-F/scaler chain and counts.  Data reduction should
branch on this and nothing else — the same two field names appear in the
fly-scan HDF5, the SAXS and WAXS frames, and the uascan run metadata.

Old-chain attributes are **commented out rather than deleted**, so reverting is
one uncomment per entry.  Nothing feeds them once the diodes are wired to the
FX4, and a stale value is worse than an absent one.

## Before deploying

1. Validate the fly-scan map against its schema:
   `xmllint --noout --schema Flyscan_config/saveFlyData.xsd Flyscan_config/saveFlyData.xml`
2. Check the attribute files parse and have no duplicate `name=`.
3. Re-run `WAXS_config/copy_attributes_to_template.py` after editing
   `WAXS_config/attributes.xml`, so the template's `NXcollection` matches.
   (It is a Python 2 script meant to be run by hand on the beamline host; this
   directory is excluded from `ruff` for that reason.)
4. Copy to `/share1/AreaDetectorConfig/` and restart the affected IOC.

`EPICS_CA_MAX_ARRAY_BYTES` must be large enough for the fly-scan time-series
arrays: roughly 8000 doubles per array, six arrays, two electrometers.

See `PLAN.md` section 1.4 for how these four formats fit together.
