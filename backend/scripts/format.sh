#!/usr/bin/env bash

set -x

uv run ruff check app --fix
uv run ruff format app
