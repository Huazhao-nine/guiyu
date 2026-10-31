#!/bin/zsh
set -eu
TASK_ROOT="${0:A:h:h}"
export GUIYU_APP_OUTPUT="$TASK_ROOT/dist/Guiyu-0.26.0.app"
export GUIYU_APP_VERSION=0.26.0
export GUIYU_APP_BUILD=26
zsh "$TASK_ROOT/scripts/build.sh"
