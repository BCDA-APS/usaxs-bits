#!/bin/bash

# file: start-usaxs-bits.sh
# purpose: Start USAXS bluesky controls in an IPython session

export BLUESKY_ENVIRONMENT=bits_usaxs
export STARTUP_MODULE=usaxs.startup
export CONDA_ROOT=$(conda info --base)

if [ "${CONDA_PREFIX}" == "" ]; then
    # No environment active, activate base
    source "${CONDA_ROOT}/etc/profile.d/conda.sh"
fi

# local solution to: CondaError: Run 'conda init' before 'conda activate'
# ref: https://www.ansiblepilot.com/articles/solving-the-conda-activation-error/
eval "$(conda shell.bash hook)"

conda activate "${BLUESKY_ENVIRONMENT}"

echo "CONDA_PREFIX = '${CONDA_PREFIX}'"
ipython -i -c "from ${STARTUP_MODULE} import *"
