"""Regression coverage for Pydantic v2 response-model configuration."""

import pytest

from app.schemas.admin_modules import AdminModuleResponse
from app.schemas.chatbot import ChatFeedbackResponse, FAQResponse
from app.schemas.users import UserResponse


@pytest.mark.parametrize(
    "schema",
    [AdminModuleResponse, ChatFeedbackResponse, FAQResponse, UserResponse],
)
def test_response_schemas_use_pydantic_v2_attribute_configuration(schema):
    """ORM response models must use ConfigDict, not Pydantic v1's Config class."""
    assert schema.model_config.get("from_attributes") is True
    assert "Config" not in schema.__dict__
