"""Consistency of the sample-metadata schema with every file that uses it.

``utils/sample_metadata_schema.py`` is the single list of ``usxSample:``
fields.  These tests check it against the ophyd device and the four XML
files that place the fields in the SAXS, WAXS and fly-scan data files.  They
need no EPICS, ophyd or ``apsbits``: the device is read with ``ast`` and the
XML with ``xml.etree``.

    PYTHONPATH=src python -m pytest tests/test_sample_metadata_schema.py -v

Tests marked ``xfail(strict=True)`` describe work not yet done (see
``Plans_skills/PLAN_sample_metadata.md`` §12); when that step lands they
start passing, ``strict`` turns that into a failure, and the mark comes off.
"""

import ast
import math
import pathlib
import xml.etree.ElementTree as ET

import pytest

from usaxs.utils import sample_metadata_schema as schema

REPO = pathlib.Path(__file__).resolve().parents[1]
DEVICE_FILE = REPO / "src" / "usaxs" / "devices" / "sample_data.py"
AD = REPO / "ADconfigs"
ATTRIBUTE_FILES = [
    AD / "SAXS_config" / "attributes.xml",
    AD / "WAXS_config" / "attributes.xml",
]
LAYOUT_FILES = [
    AD / "SAXS_config" / "layout.xml",
    AD / "WAXS_config" / "layout_waxs.xml",
]
FLY_FILE = AD / "Flyscan_config" / "saveFlyData.xml"

UNTIL_STEP_4 = pytest.mark.xfail(
    strict=True, reason="device not yet extended (plan step 4)"
)
UNTIL_STEP_7 = pytest.mark.xfail(
    strict=True, reason="XML not yet extended (plan step 7)"
)


def _ids(paths):
    return [f"{p.parent.name}/{p.name}" for p in paths]


# --- the schema itself ------------------------------------------------------


def test_schema_has_no_duplicates():
    """Names, PVs and NeXus paths are each unique."""
    for attr in ("name", "pv", "nexus"):
        values = [getattr(f, attr) for f in schema.FIELDS]
        dups = {v for v in values if values.count(v) > 1}
        assert not dups, f"duplicate {attr}: {sorted(dups)}"


def test_schema_entries_are_well_formed():
    """Every field has a known kind and scope, and enums have states."""
    for f in schema.FIELDS:
        assert f.kind in ("float", "int", "str", "enum"), f.name
        assert f.scope in schema.SCOPES, f.name
        assert f.name.isidentifier(), f.name
        assert (f.kind == "enum") == bool(f.choices), f.name
        assert not (f.long and f.kind != "str"), f.name
        # every new sub-group of /entry/sample has a declared NeXus class
        parts = f.nexus.split("/")
        assert len(parts) <= 2, f.nexus
        if len(parts) == 2:
            assert parts[0] in schema.GROUP_CLASSES, f.nexus


def test_unset_is_never_plausible():
    """Numbers unset to NaN, strings to "", enums to their state 0."""
    for f in schema.FIELDS:
        if f.kind in ("float", "int"):
            assert math.isnan(f.unset), f.name
        elif f.kind == "str":
            assert f.unset == "", f.name
        else:
            assert f.unset == f.choices[0], f.name
    # state 0 means "unset" for every enum except the field directions
    for f in schema.FIELDS:
        if f.kind == "enum" and not f.name.endswith("_dir"):
            assert f.choices[0] in ("None", "Unset"), f.name


def test_thickness_is_not_a_schema_field():
    """Thickness defaults to 1 and must never be cleared to NaN."""
    assert not any("thickness" in f.name.lower() for f in schema.FIELDS)
    assert not any("Thickness" in f.pv for f in schema.FIELDS)


def test_scopes_partition_the_table():
    """Every field is in exactly one scope."""
    counted = sum(len(schema.fields_in_scope(s)) for s in schema.SCOPES)
    assert counted == len(schema.FIELDS)
    with pytest.raises(ValueError):
        schema.fields_in_scope("nonsense")


@pytest.mark.parametrize(
    "title, blank",
    [
        ("blank", True),
        ("Blank_kapton", True),
        ("empty cell BLANK", True),
        ("PS_film_200C_22min", False),
        ("", False),
        (None, False),
    ],
)
def test_blank_rule(title, blank):
    """Matilda's rule: 'blank' anywhere in the title, any case."""
    assert schema.is_blank_title(title) is blank


# --- the ophyd device ---------------------------------------------------------


def _device_components():
    """``{attribute: (suffix, string_kw)}`` for SampleDataDevice, via ast."""
    tree = ast.parse(DEVICE_FILE.read_text())
    cls = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "SampleDataDevice"
    )
    found = {}
    for node in cls.body:
        if not (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", None) in ("Component", "Cpt")
        ):
            continue
        name = node.targets[0].id
        suffix = node.value.args[1].value
        kw = {k.arg: k.value for k in node.value.keywords}
        string = isinstance(kw.get("string"), ast.Constant) and kw["string"].value
        found[name] = (suffix, bool(string))
    return found


def test_device_has_no_unknown_usxsample_pvs():
    """Every usxSample: component of the device is in the schema."""
    for name, (suffix, _) in _device_components().items():
        if suffix.startswith(schema.PV_PREFIX):
            assert suffix in schema.FIELDS_BY_PV, f"{name} -> {suffix}"


@UNTIL_STEP_4
def test_device_matches_schema():
    """One component per field, same name and PV, string=True for text."""
    components = _device_components()
    missing = [f.name for f in schema.FIELDS if f.name not in components]
    assert not missing, f"device lacks: {missing}"
    for f in schema.FIELDS:
        suffix, string = components[f.name]
        assert suffix == f.pvname, f.name
        assert string == (f.kind in ("str", "enum")), f.name


# --- AD attributes.xml --------------------------------------------------------


def _attributes(path):
    root = ET.parse(path).getroot()
    return [e.attrib for e in root.iter("Attribute")]


@pytest.mark.parametrize("path", ATTRIBUTE_FILES, ids=_ids(ATTRIBUTE_FILES))
def test_attributes_have_no_duplicates_or_orphans(path):
    """Unique attribute names; every usxSample: source is a schema field."""
    attrs = _attributes(path)
    names = [a["name"] for a in attrs]
    dups = {n for n in names if names.count(n) > 1}
    assert not dups, f"duplicate attribute names: {sorted(dups)}"
    for a in attrs:
        if a.get("source", "").startswith(schema.PV_PREFIX):
            assert a["source"] in schema.FIELDS_BY_PV, a["source"]


@UNTIL_STEP_7
@pytest.mark.parametrize("path", ATTRIBUTE_FILES, ids=_ids(ATTRIBUTE_FILES))
def test_attributes_cover_schema(path):
    """Every field is an EPICS_PV attribute named Sample_<PV>."""
    by_source = {a.get("source"): a for a in _attributes(path)}
    missing = [f.pv for f in schema.FIELDS if f.pvname not in by_source]
    assert not missing, f"{path.name} lacks: {missing}"
    for f in schema.FIELDS:
        a = by_source[f.pvname]
        assert a["type"] == "EPICS_PV", f.pv
        assert a["name"] == f.ad_attribute, f.pv
        want = "DBR_STRING" if f.kind in ("str", "enum") else "DBR_NATIVE"
        assert a["dbrtype"] == want, f.pv


# --- AD layout.xml ------------------------------------------------------------


def _layout_sample_group(path):
    root = ET.parse(path).getroot()
    entry = root.find("group[@name='entry']")
    return entry.find("group[@name='sample']")


def _nx_class(group):
    for a in group.findall("attribute"):
        if a.get("name") == "NX_class":
            return a.get("value")
    return None


@UNTIL_STEP_7
@pytest.mark.parametrize("path", LAYOUT_FILES, ids=_ids(LAYOUT_FILES))
def test_layout_places_every_field(path):
    """Each field sits at /entry/sample/<nexus>, fed from its attribute."""
    sample = _layout_sample_group(path)
    problems = []
    for f in schema.FIELDS:
        *groups, leaf = f.nexus.split("/")
        parent = sample
        for g in groups:
            parent = parent.find(f"group[@name='{g}']")
            if parent is None:
                break
            if _nx_class(parent) != schema.GROUP_CLASSES[g]:
                problems.append(f"{g}: NX_class should be {schema.GROUP_CLASSES[g]}")
        if parent is None:
            problems.append(f"{f.nexus}: group missing")
            continue
        node = parent.find(f"*[@name='{leaf}']")
        if node is None:
            problems.append(f"{f.nexus}: missing")
        elif node.tag == "dataset":
            if node.get("ndattribute") != f.ad_attribute:
                problems.append(f"{f.nexus}: ndattribute != {f.ad_attribute}")
        elif node.tag == "hardlink":
            if node.get("target") != f"/entry/Metadata/{f.ad_attribute}":
                problems.append(f"{f.nexus}: hardlink target wrong")
        else:
            problems.append(f"{f.nexus}: unexpected <{node.tag}>")
    assert not problems, "\n".join(sorted(set(problems)))


# --- fly-scan saveFlyData.xml ------------------------------------------------


def _fly_sample_group():
    root = ET.parse(FLY_FILE).getroot()
    for group in root.iter("group"):
        if group.get("name") == "sample" and group.get("class") == "NXsample":
            return group
    raise AssertionError("no NXsample group in saveFlyData.xml")


def test_fly_has_no_orphan_usxsample_pvs():
    """Every usxSample: PV in the fly-scan map is a schema field."""
    root = ET.parse(FLY_FILE).getroot()
    for pv in root.iter("PV"):
        if pv.get("pvname", "").startswith(schema.PV_PREFIX):
            assert pv.get("pvname") in schema.FIELDS_BY_PV, pv.get("pvname")


@UNTIL_STEP_7
def test_fly_places_every_field():
    """Each field is a <PV> at /entry/sample/<nexus>; text has string="true"."""
    sample = _fly_sample_group()
    problems = []
    for f in schema.FIELDS:
        *groups, leaf = f.nexus.split("/")
        parent = sample
        for g in groups:
            parent = parent.find(f"group[@name='{g}']")
            if parent is None:
                break
            if parent.get("class") != schema.GROUP_CLASSES[g]:
                problems.append(f"{g}: class should be {schema.GROUP_CLASSES[g]}")
        if parent is None:
            problems.append(f"{f.nexus}: group missing")
            continue
        node = parent.find(f"PV[@label='{leaf}']")
        if node is None:
            problems.append(f"{f.nexus}: missing")
            continue
        if node.get("pvname") != f.pvname:
            problems.append(f"{f.nexus}: pvname != {f.pvname}")
        is_string = node.get("string", "false").lower() in ("true", "1")
        if is_string != (f.kind in ("str", "enum")):
            problems.append(f"{f.nexus}: string attribute wrong")
    assert not problems, "\n".join(sorted(set(problems)))
