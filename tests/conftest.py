import logging
import os
import pathlib
from contextlib import nullcontext
from pathlib import Path

import datajoint as dj
import pytest
from element_interface.utils import QuietStdOut, find_full_path, value_to_bool

from workflow_zstack.paths import get_volume_root_data_dir

# ------------------- SOME CONSTANTS -------------------


logger = logging.getLogger("datajoint")

pathlib.Path("../example_data").mkdir(exist_ok=True)

sessions_dirs = [
    "subject1",
]


def pytest_addoption(parser):
    """
    Permit constants when calling pytest at command line e.g., pytest --dj-verbose False

    Arguments:
        --dj-verbose (bool):  Default True. Pass print statements from Elements.
        --dj-teardown (bool): Default True. Delete pipeline on close.
        --dj-datadir (str):  Default ./tests/user_data. Relative path of test CSV data.
    """
    parser.addoption(
        "--dj-verbose",
        action="store",
        default="True",
        help="Verbose for dj items: True or False",
        choices=("True", "False"),
    )
    parser.addoption(
        "--dj-teardown",
        action="store",
        default="True",
        help="Verbose for dj items: True or False",
        choices=("True", "False"),
    )
    parser.addoption(
        "--dj-datadir",
        action="store",
        default="./tests/user_data",
        help="Relative path for saving tests data",
    )


@pytest.fixture(autouse=True, scope="session")
def setup(request):
    """Take passed commandline variables, set as global"""
    global verbose, _tear_down, test_user_data_dir, verbose_context

    verbose = value_to_bool(request.config.getoption("--dj-verbose"))
    _tear_down = value_to_bool(request.config.getoption("--dj-teardown"))
    test_user_data_dir = Path(request.config.getoption("--dj-datadir"))
    test_user_data_dir.mkdir(exist_ok=True)

    if not verbose:
        logging.getLogger("datajoint").setLevel(logging.CRITICAL)

    verbose_context = nullcontext() if verbose else QuietStdOut()

    yield verbose_context, verbose


# --------------------  HELPER CLASS --------------------


def null_function(*args, **kwargs):
    pass


# ---------------------- FIXTURES ----------------------


@pytest.fixture(autouse=True, scope="session")
def dj_config(setup):
    """If dj_local_config exists, load"""
    if pathlib.Path("./dj_local_conf.json").exists():
        dj.config.load("./dj_local_conf.json")
    dj.config.update(
        {
            "safemode": False,
            "database.host": os.environ.get("DJ_HOST") or dj.config["database.host"],
            "database.password": os.environ.get("DJ_PASS")
            or dj.config["database.password"],
            "database.user": os.environ.get("DJ_USER") or dj.config["database.user"],
            "custom": {
                "database.prefix": (
                    os.environ.get("DATABASE_PREFIX")
                    or dj.config["custom"]["database.prefix"]
                ),
                "volume_root_data_dir": (
                    os.environ.get("VOLUME_ROOT_DATA_DIR").split(",")
                    if os.environ.get("VOLUME_ROOT_DATA_DIR")
                    else dj.config["custom"]["volume_root_data_dir"]
                ),
            },
        }
    )
    return


@pytest.fixture(scope="session")
def test_data(dj_config):
    test_data_exists = True

    for p in sessions_dirs:
        try:
            find_full_path(get_volume_root_data_dir, p).as_posix()
        except FileNotFoundError:
            test_data_exists = False
            break


@pytest.fixture(autouse=True, scope="session")
def pipeline():
    from workflow_zstack import pipeline

    yield {
        "subject": pipeline.subject,
        "lab": pipeline.lab,
        "session": pipeline.session,
        "scan": pipeline.scan,
        "volume": pipeline.volume,
        "volume_matching": pipeline.volume_matching,
        "bossdb": pipeline.bossdb,
    }

    if _tear_down:
        with verbose_context:
            pipeline.subject.Subject.delete()


@pytest.fixture(scope="session")
def testdata_paths():
    return {"test1_stitched": "sub1"}

@pytest.fixture(scope="session")
def insert_upstream(pipeline):
    import datetime


    subject = pipeline["subject"]
    session = pipeline["session"]
    scan = pipeline["scan"]

    subject.Subject.insert1(
        dict(
            subject="subject1",
            sex="M",
            subject_birth_date="2023-01-01",
            subject_description="Cellpose segmentation of volumetric data."),
        skip_duplicates=True,
    )

    session_key = dict(
        subject="subject1",
        session_id=0,
    )
    session.Session.insert1(
        dict(
            session_key,
            session_datetime=datetime.datetime.now(),
        ),
        skip_duplicates=True,
    )

    session.SessionDirectory.insert1(
        dict(session_key, session_dir="sub1"),
        skip_duplicates=True,
    )
    scan.Scan.insert1(
        dict(
            session_key,
            scan_id=0,
            acq_software="ScanImage",
        ),
        skip_duplicates=True,
    )

    yield


@pytest.fixture(scope="session")
def volume_volume(pipeline):
    volume = pipeline["volume"]

    volume.Volume.populate()

    yield
    