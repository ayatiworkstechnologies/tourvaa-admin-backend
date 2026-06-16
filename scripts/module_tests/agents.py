from module_tests.common import Runner, Step, unique


def agent_payload(_: Runner) -> dict:
    return {
        "agent_name": unique("Script Agent"),
        "agent_type": "agency",
        "years_in_operation": 1,
        "status": "inactive",
        "approval_status": "pending",
    }


STEPS = [
    Step("list agents", "GET", "/agents?page=1&limit=5&search="),
    Step("create agent", "POST", "/agents/", body=agent_payload, save_id_as="agent"),
    Step("detail agent", "GET", "/agents/{id}", needs_id="agent"),
    Step("update agent", "PUT", "/agents/{id}", body={"admin_comments": "Checked by script"}, needs_id="agent"),
    Step("discount agent", "PATCH", "/agents/{id}/discount", body={"discount_type": "percentage", "discount_value": 5}, needs_id="agent"),
    Step("partial approve agent", "PATCH", "/agents/{id}/partial-approve", body={"reason": "Script check"}, needs_id="agent"),
]
