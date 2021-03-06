# Setup Notes

**NOTE**: this setup is of limited use without auxiliary components
i.e. our specialized MongoDB setup used for logging and tracking


- Create a snakemake environment with needed components:
  - `ver=3.7.1; conda create -n snakemake-$ver pymongo drmaa python-dateutil snakemake=$ver -c bioconda`
  - Change `snakemake_env` in etc/site.yaml to point to this env
- Install other components into conda root env: 
  - `conda install pymongo drmaa yaml pylint python-dateutil`
- Install pymongo into conda root env
- Create testing and logging directories per pipeline (see `tools/create_pipeline_dirs.sh`)
- Software/modules management is based on dotkit. See also `lib/pipelines.py:INIT`
- Test scripts expect `RPD_ROOT` to be set
- ELM logging goes to `RPD_ELMLOGDIR`

# Install Preview

- `src=pipelines.git/`
- `pushd $src; vstr=$(git rev-parse --short HEAD); popd`
- `dest=pipelines-preview/pipelines-$vstr`
- `rsync -av --exclude '.git/' --exclude '*~' --exclude '/tmp/' --exclude 'etc/' --exclude '*/_*' --exclude '*.check.*'  $src/ $dest`
- set interpreter in shebang of $dest/run
- `mkdir $dest/etc`
- copy yaml of choice to $dest/etc/ and link site.yaml

