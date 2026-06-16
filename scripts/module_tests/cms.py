import time

from module_tests.common import CheckError, Runner, Step, first_id_from_list, unique


def country_payload(_: Runner) -> dict:
    code = str(int(time.time() * 1000))[-6:]
    return {
        "country_name": unique("Script Country"),
        "country_code": f"T{code}",
        "phone_code": "+91",
        "currency_code": "INR",
        "status": "active",
    }


def city_payload(runner: Runner) -> dict:
    country_id = runner.ids.get("country") or first_id_from_list(runner, "/countries?page=1&limit=1")
    if not country_id:
        raise CheckError("City write check needs a country. Run cms with --write first.")
    runner.ids["country"] = country_id
    return {"country_id": country_id, "city_name": unique("Script City"), "status": "active"}


def category_payload(_: Runner) -> dict:
    name = unique("Script Category")
    return {"category_name": name, "slug": "", "description": "Created by module script", "image": "", "status": "active"}


def subcategory_payload(runner: Runner) -> dict:
    category_id = runner.ids.get("category") or first_id_from_list(runner, "/tour-categories?page=1&limit=1")
    if not category_id:
        raise CheckError("Subcategory write check needs a category. Run cms with --write first.")
    runner.ids["category"] = category_id
    return {
        "category_id": category_id,
        "subcategory_name": unique("Script Subcategory"),
        "slug": "",
        "description": "Created by module script",
        "image": "",
        "status": "active",
    }


def tour_payload(runner: Runner) -> dict:
    country_id = runner.ids.get("country") or first_id_from_list(runner, "/countries?page=1&limit=1")
    city_id = runner.ids.get("city") or first_id_from_list(runner, "/cities?page=1&limit=1")
    category_id = runner.ids.get("category") or first_id_from_list(runner, "/tour-categories?page=1&limit=1")
    return {
        "title": unique("Script Tour"),
        "slug": "",
        "subtitle": "",
        "price_start_per_person": 100,
        "currency": "USD",
        "country_id": country_id,
        "city_id": city_id,
        "category_id": category_id,
        "subcategory_ids": [],
        "start_location": "",
        "finish_location": "",
        "number_of_days": 1,
        "short_description": "Created by module script",
        "long_description": "",
        "status": "draft",
    }


STEPS = [
    Step("list countries", "GET", "/countries?page=1&limit=5&search="),
    Step("create country", "POST", "/countries", body=country_payload, save_id_as="country"),
    Step("detail country", "GET", "/countries/{id}", needs_id="country"),
    Step("disable country", "PATCH", "/countries/{id}/status", body={"status": "inactive"}, needs_id="country"),
    Step("create city", "POST", "/cities", body=city_payload, save_id_as="city"),
    Step("detail city", "GET", "/cities/{id}", needs_id="city"),
    Step("create category", "POST", "/tour-categories", body=category_payload, save_id_as="category"),
    Step("detail category", "GET", "/tour-categories/{id}", needs_id="category"),
    Step("create subcategory", "POST", "/tour-subcategories", body=subcategory_payload, save_id_as="subcategory"),
    Step("detail subcategory", "GET", "/tour-subcategories/{id}", needs_id="subcategory"),
    Step("create tour", "POST", "/tours", body=tour_payload, save_id_as="tour"),
    Step("detail tour", "GET", "/tours/{id}", needs_id="tour"),
    Step("publish tour", "PATCH", "/tours/{id}/status", body={"status": "published"}, needs_id="tour"),
]
