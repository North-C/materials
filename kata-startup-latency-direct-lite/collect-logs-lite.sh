#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

RUN_DIR=""
SINCE=""
UNTIL=""

die() {
	echo "[$(basename "$0")] ERROR: $*" >&2
	exit 1
}

require_cmd() {
	command -v "$1" > /dev/null 2>&1 || die "command not available: $1"
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--run-dir)
			RUN_DIR="$2"
			shift 2
			;;
		--since)
			SINCE="$2"
			shift 2
			;;
		--until)
			UNTIL="$2"
			shift 2
			;;
		*)
			die "unknown argument: $1"
			;;
	esac
done

[ -n "${RUN_DIR}" ] || die "need --run-dir"
[ -d "${RUN_DIR}" ] || die "run dir does not exist: ${RUN_DIR}"
[ -n "${SINCE}" ] || die "need --since"
[ -n "${UNTIL}" ] || die "need --until"

require_cmd sudo
require_cmd journalctl

sudo journalctl -u containerd --since "${SINCE}" --until "${UNTIL}" -o short-iso-precise --no-pager > "${RUN_DIR}/logs/containerd.log" || true
