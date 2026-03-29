#!/bin/bash
set -e

echo "Starting ONVIF Splitter..."
exec python -m onvif_splitter "$@"
