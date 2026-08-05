#!/bin/sh
Xvfb :99 -screen 0 1280x900x24 >/dev/null 2>&1 &
sleep 1
exec "$@"
