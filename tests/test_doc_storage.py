"""Tests for doc_storage module name validation."""

from src.tools.doc_storage import _validate_module_name


def test_simple_module_name_valid():
    assert _validate_module_name("order") is None


def test_module_name_with_numbers():
    assert _validate_module_name("order2") is None


def test_module_name_with_underscore():
    assert _validate_module_name("order_v2") is None


def test_module_name_with_slash_valid():
    """Module names with / should be valid for batch generator paths like 'access/order'."""
    assert _validate_module_name("access/order") is None


def test_module_name_multi_level_slash():
    assert _validate_module_name("access/order/sub") is None


def test_module_name_empty_invalid():
    assert _validate_module_name("") is not None


def test_module_name_starts_with_number_invalid():
    assert _validate_module_name("2order") is not None


def test_module_name_uppercase_invalid():
    assert _validate_module_name("Order") is not None


def test_module_name_trailing_slash_invalid():
    assert _validate_module_name("access/") is not None


def test_module_name_leading_slash_invalid():
    assert _validate_module_name("/access") is not None


def test_module_name_double_slash_invalid():
    assert _validate_module_name("access//order") is not None


def test_module_name_slash_segment_starts_with_number_invalid():
    assert _validate_module_name("access/2order") is not None
