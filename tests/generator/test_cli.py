"""Tests for CLI argument parsing."""

import pytest

from src.generator.__main__ import parse_args


def test_project_flag():
    args = parse_args(["--project", "access"])
    assert args.project == "access"
    assert args.all is False


def test_all_flag():
    args = parse_args(["--all"])
    assert args.all is True
    assert args.project is None


def test_project_and_all_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--project", "access", "--all"])


def test_api_requires_project():
    with pytest.raises(SystemExit):
        parse_args(["--api", "CreateOrder"])


def test_api_file_requires_api():
    with pytest.raises(SystemExit):
        parse_args(["--project", "access", "--api-file", "order/create.go"])


def test_force_and_api_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--project", "access", "--api", "CreateOrder", "--force"])


def test_api_with_project():
    args = parse_args(["--project", "access", "--api", "CreateOrder"])
    assert args.project == "access"
    assert args.api == "CreateOrder"


def test_api_file_with_api():
    args = parse_args(["--project", "access", "--api", "CreateOrder", "--api-file", "order/create.go"])
    assert args.api_file == "order/create.go"


def test_dry_run():
    args = parse_args(["--project", "access", "--dry-run"])
    assert args.dry_run is True


def test_force():
    args = parse_args(["--project", "access", "--force"])
    assert args.force is True


def test_no_args_fails():
    with pytest.raises(SystemExit):
        parse_args([])
