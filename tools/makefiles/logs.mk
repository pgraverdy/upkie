# Copyright 2023 Inria
# SPDX-License-Identifier: Apache-2.0
#
# Convenience Makefile to synchronize Upkie log files
#
# Put this Makefile in the directory to synchronize and run ``make download``
# to download the latest logs from the robot. For now this Makefile assumes
# logs are stored in a logs/ directory the remote user's home directory.

# Hostname or IP address of the Raspberry Pi Uses the value from the UPKIE_NAME
# environment variable, if defined.
REMOTE = ${UPKIE_NAME}

.PHONY: clean
clean:  ## Clean up logs smaller than 100 KiB
	find . -name '*.mpack' -size "-100k" -delete

.PHONY: download
download:  ## Download logs from remote host
	rsync -auvz --progress --exclude Makefile ${REMOTE}:logs/ $(CURDIR)/

.PHONY: foxplot_last
foxplot_last:  ## Plot latest log
	foxplot $(shell ls *.mpack | tail -n 1)

# Help snippet adapted from:
# http://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
.PHONY: help
help:
	@echo "Rules:\n"
	@grep -P '^[a-zA-Z0-9_-]+:.*? ## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "    \033[36m%-24s\033[0m %s\n", $$1, $$2}'
.DEFAULT_GOAL := help
