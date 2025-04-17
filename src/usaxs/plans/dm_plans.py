"""Data Management plans for the USAXS instrument.

This module provides plans for managing data in the USAXS instrument,
including workflow execution, job management, and metadata sharing.
"""

__all__ = [
    "dm_kickoff_workflow",
    "dm_list_processing_jobs",
    "dm_submit_workflow_job",
]

import logging
from typing import Any
from typing import Dict
from typing import Generator
from typing import Optional

from apsbits.utils.controls_setup import oregistry
from apstools.devices import DM_WorkflowConnector
from apstools.utils import dm_api_proc
from apstools.utils import share_bluesky_metadata_with_dm
from bluesky import plan_stubs as bps
from bluesky import preprocessors as bpp

logger = logging.getLogger(__name__)
logger.info(__file__)

# Device instances
dm_workflow = oregistry["dm_workflow"]


def dm_kickoff_workflow(
    run: Any,
    argsDict: Dict[str, Any],
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
    timeout: Optional[float] = None,
    wait: bool = False,
) -> Generator[Any, None, Any]:
    """Start a DM workflow for this bluesky run and share run's metadata with DM.

    This function initiates a Data Management workflow for a Bluesky run,
    configures the workflow parameters, and shares the run's metadata with DM.

    Parameters
    ----------
    run : Any
        Bluesky run object (such as 'run = cat[uid]')
    argsDict : Dict[str, Any]
        Dictionary of parameters needed by 'workflowName'.
        At minimum, most workflows expect these keys: 'filePath' and
        'experimentName'. Consult the workflow for the expected content.
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None
    timeout : Optional[float], optional
        When should bluesky stop reporting on this DM workflow job
        (if it has not ended). Units are seconds. Default is forever.
    wait : bool, optional
        Should this plan stub wait for the job to end?, by default False

    Returns
    -------
    Generator[Any, None, Any]
        A sequence of plan messages

    USAGE:  ``RE(dm_kickoff_workflow(run, argsDict))``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    _md = {}
    _md.update(md or {})

    @bpp.run_decorator(md=_md)
    def _inner() -> Generator[Any, None, Any]:
        dm_workflow = DM_WorkflowConnector(name="dm_workflow")

        if timeout is None:
            # Disable periodic reports, use a long time (s).
            timeout = 999_999_999_999

        yield from bps.mv(dm_workflow.concise_reporting, True)
        yield from bps.mv(dm_workflow.reporting_period, timeout)

        workflow_name = argsDict.pop["workflowName"]
        yield from dm_workflow.run_as_plan(
            workflow=workflow_name,
            wait=wait,
            timeout=timeout,
            **argsDict,
        )

        # Upload bluesky run metadata to APS DM.
        share_bluesky_metadata_with_dm(argsDict["experimentName"], workflow_name, run)

        # Users requested the DM workflow job ID be printed to the console.
        dm_workflow._update_processing_data()
        job_id = dm_workflow.job_id.get()
        job_stage = dm_workflow.stage_id.get()
        job_status = dm_workflow.status.get()
        print(f"DM workflow id: {job_id!r}  status: {job_status}  stage: {job_stage}")

    return (yield from _inner())


def dm_list_processing_jobs(
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
    exclude: Optional[tuple[str, ...]] = None,
) -> Generator[Any, None, Any]:
    """Show all the DM jobs with status not excluded.

    This function lists all Data Management jobs that don't have
    an excluded status (default: 'done', 'failed').

    Parameters
    ----------
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None
    exclude : Optional[tuple[str, ...]], optional
        Tuple of status values to exclude from the listing, by default None

    Returns
    -------
    Generator[Any, None, Any]
        A sequence of plan messages

    USAGE:  ``RE(dm_list_processing_jobs())``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    _md = {}
    _md.update(md or {})

    @bpp.run_decorator(md=_md)
    def _inner() -> Generator[Any, None, Any]:
        yield from bps.null()  # make this a plan stub
        api = dm_api_proc()
        if exclude is None:
            exclude = ("done", "failed")

        for j in api.listProcessingJobs():
            if j["status"] not in exclude:
                print(
                    f"id={j['id']!r}"
                    f"  submitted={j.get('submissionTimestamp')}"
                    f"  status={j['status']!r}"
                )

    return (yield from _inner())


def dm_submit_workflow_job(
    workflowName: str,
    argsDict: Dict[str, Any],
    md: Optional[Dict[str, Any]] = None,
    RE: Optional[Any] = None,
    bec: Optional[Any] = None,
    specwriter: Optional[Any] = None,
) -> Generator[Any, None, Any]:
    """Low-level plan stub to submit a job to a DM workflow.

    This function submits a job to a Data Management workflow without
    sharing run metadata with DM. It is recommended to use
    dm_kickoff_workflow() instead.

    Parameters
    ----------
    workflowName : str
        Name of the DM workflow to be run
    argsDict : Dict[str, Any]
        Dictionary of parameters needed by 'workflowName'.
        At minimum, most workflows expect these keys: 'filePath' and
        'experimentName'. Consult the workflow for the expected content.
    md : Optional[Dict[str, Any]], optional
        Metadata dictionary, by default None
    RE : Optional[Any], optional
        Bluesky RunEngine instance, by default None
    bec : Optional[Any], optional
        Bluesky Live Callbacks instance, by default None
    specwriter : Optional[Any], optional
        SPEC file writer instance, by default None

    Returns
    -------
    Generator[Any, None, Any]
        A sequence of plan messages

    USAGE:  ``RE(dm_submit_workflow_job(workflowName, argsDict))``
    """
    if md is None:
        md = {}
    if RE is None:
        raise ValueError("RunEngine instance must be provided")
    if bec is None:
        raise ValueError("Bluesky Live Callbacks instance must be provided")
    if specwriter is None:
        raise ValueError("SPEC file writer instance must be provided")

    _md = {}
    _md.update(md or {})

    @bpp.run_decorator(md=_md)
    def _inner() -> Generator[Any, None, Any]:
        yield from bps.null()  # make this a plan stub
        api = dm_api_proc()

        job = api.startProcessingJob(api.username, workflowName, argsDict)
        print(f"workflow={workflowName!r}  id={job['id']!r}")

    return (yield from _inner())
