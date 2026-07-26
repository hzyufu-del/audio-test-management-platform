#!/bin/sh
set -eu

flask --app run.py db upgrade

case "${SEED_DEMO_DATA:-false}" in
    true)
        flask --app run.py init-db
        ;;
    false)
        ;;
    *)
        echo "SEED_DEMO_DATA must be either true or false." >&2
        exit 64
        ;;
esac

exec "$@"
