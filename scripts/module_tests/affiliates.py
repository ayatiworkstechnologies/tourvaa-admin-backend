import time

from module_tests.common import Runner, Step, unique


def affiliate_payload(_: Runner) -> dict:
    suffix = int(time.time() * 1000)
    return {
        "business_type": "publisher",
        "name": unique("Script Affiliate"),
        "email": f"affiliate-{suffix}@example.com",
        "phone": "",
        "website_url": "https://example.com",
        "status": "inactive",
        "approval_status": "pending",
    }


STEPS = [
    Step("list affiliates", "GET", "/affiliates?page=1&limit=5&search="),
    Step("create affiliate", "POST", "/affiliates/", body=affiliate_payload, save_id_as="affiliate"),
    Step("detail affiliate", "GET", "/affiliates/{id}", needs_id="affiliate"),
    Step("api link affiliate", "PATCH", "/affiliates/{id}/api-link", body={"api_link": "https://api.example.com/affiliate"}, needs_id="affiliate"),
    Step("approve affiliate", "PATCH", "/affiliates/{id}/approve", needs_id="affiliate"),
]
