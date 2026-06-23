#!/bin/sh

isort --check-only --settings-file ./.isort.cfg app
black --check --config=./.black app
flake8 --config=.flake8 app
