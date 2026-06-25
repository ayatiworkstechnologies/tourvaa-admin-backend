"""Module 33 — Website CMS endpoints"""
import pytest
import requests
import os
import uuid
from tests.conftest import BASE_URL, skip_if_readonly, unique, auth_headers

_created_blog_id = None
_created_banner_id = None
_created_destination_id = None


# ─── Blogs ────────────────────────────────────────────────────────────────────

def test_cms_blogs_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/cms/blogs", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_cms_blogs_is_list(headers):
    resp = requests.get(f"{BASE_URL}/cms/blogs", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list, got: {type(items)}"


@skip_if_readonly()
def test_create_blog(headers):
    global _created_blog_id
    title = unique("Test Blog")
    payload = {
        "title": title,
        "slug": unique("test-blog"),
        "content": "This is test blog content for automated testing.",
        "status": "draft",
    }
    resp = requests.post(f"{BASE_URL}/cms/blogs", headers=headers, json=payload, timeout=10)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    blog = body.get("data", body)
    _created_blog_id = blog.get("id")
    assert _created_blog_id, f"No id in response: {body}"
    assert blog.get("title") or blog.get("blog_title"), f"No title in response: {body}"
    assert blog.get("slug"), f"No slug in response: {body}"


@skip_if_readonly()
def test_update_blog(headers):
    if not _created_blog_id:
        pytest.skip("No blog created to update")
    payload = {"title": unique("Updated Blog Title"), "status": "published"}
    resp = requests.put(
        f"{BASE_URL}/cms/blogs/{_created_blog_id}",
        headers=headers,
        json=payload,
        timeout=10,
    )
    assert resp.status_code in (200, 201, 204), resp.text


@skip_if_readonly()
def test_delete_blog(headers):
    if not _created_blog_id:
        pytest.skip("No blog created to delete")
    resp = requests.delete(
        f"{BASE_URL}/cms/blogs/{_created_blog_id}",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code in (200, 204), resp.text


# ─── Homepage Banners ─────────────────────────────────────────────────────────

def test_cms_homepage_banners_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/cms/homepage-banners", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_cms_homepage_banners_is_list(headers):
    resp = requests.get(f"{BASE_URL}/cms/homepage-banners", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list, got: {type(items)}"


@skip_if_readonly()
def test_create_homepage_banner(headers):
    global _created_banner_id
    payload = {
        "title": unique("Test Banner"),
        "image": "https://example.com/banner.jpg",
        "cta_url": "https://example.com/tour",
        "is_active": True,
        "sort_order": 99,
    }
    resp = requests.post(
        f"{BASE_URL}/cms/homepage-banners",
        headers=headers,
        json=payload,
        timeout=10,
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    banner = body.get("data", body)
    _created_banner_id = banner.get("id")
    assert _created_banner_id, f"No id in response: {body}"


@skip_if_readonly()
def test_delete_homepage_banner(headers):
    if not _created_banner_id:
        pytest.skip("No banner created to delete")
    resp = requests.delete(
        f"{BASE_URL}/cms/homepage-banners/{_created_banner_id}",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code in (200, 204), resp.text


# ─── Popular Destinations ─────────────────────────────────────────────────────

def test_cms_popular_destinations_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/cms/popular-destinations", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


@skip_if_readonly()
def test_create_popular_destination(headers):
    global _created_destination_id
    payload = {
        "title": unique("Test Destination"),
        "image": "https://example.com/dest.jpg",
        "description": "A beautiful test destination",
        "is_active": True,
    }
    resp = requests.post(
        f"{BASE_URL}/cms/popular-destinations",
        headers=headers,
        json=payload,
        timeout=10,
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    dest = body.get("data", body)
    _created_destination_id = dest.get("id")
    assert _created_destination_id, f"No id in response: {body}"


# ─── Policies ─────────────────────────────────────────────────────────────────

def test_cms_policies_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/cms/policies", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_cms_policies_has_items(headers):
    resp = requests.get(f"{BASE_URL}/cms/policies", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert isinstance(items, list), f"Expected list of policies, got: {type(items)}"


def test_cms_policy_terms_and_conditions(headers):
    resp = requests.get(
        f"{BASE_URL}/cms/policies/terms-and-conditions",
        headers=headers,
        timeout=10,
    )
    assert resp.status_code in (200, 404), (
        f"Expected 200 or 404 for terms-and-conditions, got {resp.status_code}: {resp.text}"
    )


@skip_if_readonly()
def test_update_cms_policy(headers):
    payload = {
        "slug": "terms-and-conditions",
        "title": "Terms and Conditions",
        "content": "Updated terms and conditions content for testing purposes.",
    }
    resp = requests.put(
        f"{BASE_URL}/cms/policies",
        headers=headers,
        json=payload,
        timeout=10,
    )
    assert resp.status_code in (200, 201, 204), resp.text


# ─── Other CMS endpoints ──────────────────────────────────────────────────────

def test_cms_customer_reviews_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/cms/customer-reviews", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_cms_help_centre_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/cms/help-centre", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_cms_promotional_popups_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/cms/promotional-popups", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_cms_tours_on_deals_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/cms/tours-on-deals", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_cms_external_links_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/cms/external-links", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_cms_sitemap_returns_200(headers):
    resp = requests.get(f"{BASE_URL}/cms/sitemap", headers=headers, timeout=10)
    assert resp.status_code == 200, resp.text


def test_cms_sitemap_xml_returns_200():
    """sitemap.xml is typically public — no auth needed."""
    resp = requests.get(f"{BASE_URL}/cms/sitemap.xml", timeout=10)
    assert resp.status_code == 200, resp.text
    content_type = resp.headers.get("content-type", "")
    assert "xml" in content_type.lower(), (
        f"Expected XML content-type for sitemap.xml, got: {content_type}"
    )
