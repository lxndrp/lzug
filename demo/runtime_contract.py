"""Small immutable contract required by the public-demo runtime.

The complete fixture catalog and its adapters remain build-time inputs under
``fixtures/``. Only values that the runtime must use to bind a demo session to
the already persisted seed are kept here.
"""

FIXTURE_CATALOG_VERSION = 3
FIXTURE_CATALOG_REVISION = "athens-theater-venues-v3"
FIXTURE_ROOT = "name.papaspyrou.repertoire.lzug.fixture"
DEMO_MATRIX_VERSION = "demo-paths-v8"
FIXTURE_PROFILES = {
    "public-demo": {
        "name": "public-demo",
        "reference_time": "2026-01-01T00:00:00+00:00",
        "scenarios": [
            "demo.487.absence",
            "demo.487.planchange",
            "authorization.positive.athen",
            "authorization.negative.foreign-committee",
            "authorization.negative.wrong-side",
            "membership.crosscommittee",
            "staffing.fallback",
            "staffing.suitable",
            "staffing.unsuitable",
        ],
    }
}

DEMO_ROLES = {
    "chair": {
        "account_id": 1,
        "person_id": 1,
        "committee_member_id": 1,
        "account_email": "chair@demo.lzug.invalid",
        "person_email": "theseus.athen@demo.lzug.invalid",
        "display_name": "Theseus von Athen",
    },
    "examiner": {
        "account_id": 2,
        "person_id": 3,
        "committee_member_id": 3,
        "account_email": "examiner@demo.lzug.invalid",
        "person_email": "peter.quince@demo.lzug.invalid",
        "display_name": "Peter Quince",
    },
    "replacement": {
        "account_id": 4,
        "person_id": 6,
        "committee_member_id": 6,
        "account_email": "replacement@demo.lzug.invalid",
        "person_email": "francis.flute@demo.lzug.invalid",
        "display_name": "Francis Flute",
    },
}

FIXTURE_IDS = {
    f"{FIXTURE_ROOT}.membership.chair.athen": {"id": 1},
    f"{FIXTURE_ROOT}.membership.examiner.absent": {"id": 3},
    f"{FIXTURE_ROOT}.membership.examiner.replacement": {"id": 6},
    f"{FIXTURE_ROOT}.membership.examiner.unsuitable": {"id": 7},
    f"{FIXTURE_ROOT}.room.zappeion.theseus": {"id": 1},
    f"{FIXTURE_ROOT}.room.gazi.handwerkerensemble": {"id": 2},
}

DISPLAY_NAMES = {
    f"{FIXTURE_ROOT}.person.chair.athen": "Theseus von Athen",
    f"{FIXTURE_ROOT}.person.examiner.absent": "Peter Quince",
    f"{FIXTURE_ROOT}.person.examiner.replacement": "Francis Flute",
    f"{FIXTURE_ROOT}.room.zappeion.theseus": "Theseussaal",
    f"{FIXTURE_ROOT}.room.gazi.handwerkerensemble": "Werkstatt Handwerkerensemble",
}
