#!/bin/sh
set -eu

mode="$1"
shift

case "$mode" in
    app)
        exec /usr/bin/setpriv \
            --reuid=www-data --regid=www-data --init-groups \
            --inh-caps=-all --ambient-caps=-all --bounding-set=-all \
            --no-new-privs "$@"
        ;;
    raw)
        exec /usr/bin/setpriv \
            --securebits=+no_setuid_fixup,+noroot \
            --reuid=www-data --regid=www-data --init-groups \
            --inh-caps=-all,+net_raw --ambient-caps=-all,+net_raw \
            --bounding-set=-all,+net_raw --no-new-privs "$@"
        ;;
    bind)
        exec /usr/bin/setpriv \
            --securebits=+no_setuid_fixup,+noroot \
            --reuid=www-data --regid=www-data --init-groups \
            --inh-caps=-all,+net_bind_service --ambient-caps=-all,+net_bind_service \
            --bounding-set=-all,+net_bind_service --no-new-privs "$@"
        ;;
    admin)
        exec /usr/bin/setpriv \
            --inh-caps=-all,+net_admin --ambient-caps=-all,+net_admin \
            --bounding-set=-all,+net_admin --no-new-privs "$@"
        ;;
    *)
        echo "unknown capability profile: $mode" >&2
        exit 64
        ;;
esac
