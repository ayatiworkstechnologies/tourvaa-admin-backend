from module_tests.common import Runner, Step, unique


def supplier_payload(_: Runner) -> dict:
    return {
        "supplier_name": unique("Script Supplier"),
        "supplier_type": "local",
        "years_in_operation": 1,
        "status": "inactive",
        "approval_status": "pending",
    }


STEPS = [
    Step("list suppliers", "GET", "/suppliers?page=1&limit=5&search="),
    Step("create supplier", "POST", "/suppliers/", body=supplier_payload, save_id_as="supplier"),
    Step("detail supplier", "GET", "/suppliers/{id}", needs_id="supplier"),
    Step("update supplier", "PUT", "/suppliers/{id}", body={"admin_comments": "Checked by script"}, needs_id="supplier"),
    Step("markup supplier", "PATCH", "/suppliers/{id}/markup", body={"markup_type": "percentage", "markup_value": 5}, needs_id="supplier"),
    Step("partial approve supplier", "PATCH", "/suppliers/{id}/partial-approve", body={"reason": "Script check"}, needs_id="supplier"),
]
