#!/bin/bash

# file: start-usaxs-bits.sh
# purpose: Start USAXS bluesky controls in an IPython session

export BLUESKY_ENVIRONMENT=bits_usaxs  
export INSTRUMENT_PACKAGE_NAME=usaxs
export CONDA_ROOT=$(conda info --base)

if [ "${CONDA_PREFIX}" == "" ]; then
    source "${CONDA_ROOT}/etc/profile.d/conda.sh"
fi

# local solution to: CondaError: Run 'conda init' before 'conda activate'
eval "$(conda shell.bash hook)"

conda activate "${BLUESKY_ENVIRONMENT}"

echo "CONDA_PREFIX = '${CONDA_PREFIX}'"
ipython -i -c "from ${INSTRUMENT_PACKAGE_NAME}.startup import *"
