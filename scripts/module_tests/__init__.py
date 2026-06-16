from module_tests.affiliates import STEPS as AFFILIATES_STEPS
from module_tests.agents import STEPS as AGENTS_STEPS
from module_tests.cms import STEPS as CMS_STEPS
from module_tests.core import STEPS as CORE_STEPS
from module_tests.rbac import STEPS as RBAC_STEPS
from module_tests.suppliers import STEPS as SUPPLIERS_STEPS
from module_tests.uploads import STEPS as UPLOADS_STEPS


MODULES = {
    "core": CORE_STEPS,
    "rbac": RBAC_STEPS,
    "suppliers": SUPPLIERS_STEPS,
    "agents": AGENTS_STEPS,
    "affiliates": AFFILIATES_STEPS,
    "cms": CMS_STEPS,
    "uploads": UPLOADS_STEPS,
}
