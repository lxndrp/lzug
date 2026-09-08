from __future__ import annotations

import unittest
from dataclasses import replace

from fastapi.routing import APIRoute

from backend.fastapi_assessment import create_assessment_router
from backend.fastapi_execution import create_execution_router
from backend.tests.helpers import ApiServer, TempDatabase


class FastAPIExecutionRoutingTests(unittest.TestCase):
    def test_execution_and_assessment_modules_own_their_routes(self) -> None:
        by_module: dict[str, set[tuple[str, str]]] = {}
        routers = (
            create_execution_router(
                finish=None,
                not_found=None,
                plain_text=None,
                read_security={},
                write_security={},
            ),
            create_assessment_router(
                finish=None,
                not_found=None,
                plain_text=None,
                read_security={},
                write_security={},
            ),
        )
        for router in routers:
            for route in router.routes:
                if not isinstance(route, APIRoute):
                    continue
                module = route.endpoint.__module__
                for method in route.methods:
                    by_module.setdefault(module, set()).add((method, route.path))

        self.assertEqual(
            {
                ("POST", "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/start"),
                ("GET", "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/protocol"),
                ("GET", "/api/exam-protocols/{protocol_id}"),
                ("PATCH", "/api/exam-protocols/{protocol_id}"),
                ("POST", "/api/exam-protocols/{protocol_id}/submit"),
                ("POST", "/api/exam-protocols/{protocol_id}/responses"),
                ("POST", "/api/exam-protocols/{protocol_id}/correction-requests"),
                ("POST", "/api/exam-protocols/{protocol_id}/open-correction"),
                ("PUT", "/api/exam-protocols/{protocol_id}/retention"),
                ("GET", "/api/exam-protocols/{protocol_id}/export.json"),
                ("GET", "/api/exam-protocols/{protocol_id}/export.txt"),
                ("GET", "/api/confirmed-plan-days/{day_id}/protocol-completion"),
                ("PATCH", "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance"),
                (
                    "PATCH",
                    "/api/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance",
                ),
                ("PATCH", "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/status"),
            },
            by_module["backend.fastapi_execution"],
        )
        self.assertEqual(
            {
                ("GET", "/api/assessment-model-versions"),
                ("POST", "/api/assessment-model-versions"),
                ("GET", "/api/exam-rounds/{round_id}/assessment-model-binding"),
                ("POST", "/api/exam-rounds/{round_id}/assessment-model-binding"),
                ("GET", "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/result"),
                ("GET", "/api/exam-results/{result_id}"),
                ("POST", "/api/exam-results/{result_id}/individual-assessments"),
                (
                    "POST",
                    "/api/exam-results/{result_id}/individual-assessments/{assessment_id}/withdraw",
                ),
                ("POST", "/api/exam-results/{result_id}/disclosures"),
                ("POST", "/api/exam-results/{result_id}/committee-assessments"),
                ("POST", "/api/exam-results/{result_id}/external-results"),
                (
                    "POST",
                    "/api/exam-results/{result_id}/external-results/{external_result_id}/confirm",
                ),
                ("POST", "/api/exam-results/{result_id}/determine"),
                ("POST", "/api/exam-results/{result_id}/record-confirmations"),
                ("POST", "/api/exam-results/{result_id}/corrections"),
                ("POST", "/api/exam-results/{result_id}/communications"),
                ("PUT", "/api/exam-results/{result_id}/retention"),
                ("GET", "/api/exam-results/{result_id}/export.json"),
                ("GET", "/api/exam-results/{result_id}/export.txt"),
                ("GET", "/api/confirmed-plan-days/{day_id}/result-completion"),
            },
            by_module["backend.fastapi_assessment"],
        )

    def test_selected_execution_writes_reference_domain_request_models(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            if api.client is None:
                raise AssertionError("API client is not active")
            document = api.client.app.openapi()

        commands = (
            (
                "post",
                "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/start",
                "ExamSlotStartRequest",
            ),
            (
                "patch",
                "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/attendance",
                "ExamAttendanceUpdateRequest",
            ),
            (
                "patch",
                "/api/confirmed-plan-days/{day_id}/assignments/{assignment_id}/attendance",
                "ExamAttendanceUpdateRequest",
            ),
            (
                "patch",
                "/api/confirmed-plan-days/{day_id}/slots/{slot_id}/status",
                "ExamSlotStatusUpdateRequest",
            ),
            ("patch", "/api/exam-protocols/{protocol_id}", "ExamProtocolContentRequest"),
            (
                "post",
                "/api/exam-protocols/{protocol_id}/responses",
                "ExamProtocolResponseRequest",
            ),
            (
                "post",
                "/api/exam-rounds/{round_id}/assessment-model-binding",
                "AssessmentModelBindingRequest",
            ),
            (
                "post",
                "/api/exam-results/{result_id}/individual-assessments",
                "IndividualAssessmentRequest",
            ),
        )
        for method, path, schema_name in commands:
            with self.subTest(method=method, path=path):
                request_schema = document["paths"][path][method]["requestBody"]["content"][
                    "application/json"
                ]["schema"]
                self.assertEqual(schema_name, request_schema["title"])

        entry_schema = document["paths"]["/api/exam-protocols/{protocol_id}"]["patch"][
            "requestBody"
        ]["content"]["application/json"]["schema"]["properties"]["entries"]["items"]
        self.assertEqual("ExamProtocolEntryRequest", entry_schema["title"])

    def test_execution_and_assessment_routes_keep_authentication_and_csrf_guards(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            for path in (
                "/api/exam-protocols/1",
                "/api/exam-results/1",
            ):
                with self.subTest(path=path, boundary="session"):
                    status, _response = api.request("GET", path, authenticated=False)
                    self.assertEqual(401, status)

            invalid_credentials = replace(api.credentials, csrf_token="invalid-csrf")
            for path, payload in (
                (
                    "/api/confirmed-plan-days/1/slots/1/status",
                    {"status": "completed"},
                ),
                (
                    "/api/exam-results/1/individual-assessments",
                    {
                        "version": 1,
                        "component_key": "work-sample",
                        "criterion_key": "quality",
                        "raw_points": 80,
                    },
                ),
            ):
                with self.subTest(path=path, boundary="csrf"):
                    status, _response = api.request(
                        "POST" if "individual-assessments" in path else "PATCH",
                        path,
                        payload,
                        credentials=invalid_credentials,
                    )
                    self.assertEqual(403, status)


if __name__ == "__main__":
    unittest.main()
