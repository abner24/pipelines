#!/usr/bin/env python3
"""{PIPELINE_NAME} pipeline (version: {PIPELINE_VERSION}): creates
pipeline-specific config files to given output directory and runs the
pipeline (unless otherwise requested).
"""
# generic usage {PIPELINE_NAME} and {PIPELINE_VERSION} replaced while
# printing usage

#--- standard library imports
#
import sys
import os
import argparse
import logging

#--- third-party imports
#
import yaml

#--- project specific imports
#
# add lib dir for this pipeline installation to PYTHONPATH
LIB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "lib"))
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)
from readunits import get_samples_and_readunits_from_cfgfile
from readunits import get_readunits_from_args
from pipelines import get_pipeline_version
from pipelines import PipelineHandler
from pipelines import logger as aux_logger
from pipelines import get_cluster_cfgfile
from pipelines import default_argparser


__author__ = "Andreas Wilm"
__email__ = "wilma@gis.a-star.edu.sg"
__copyright__ = "2016 Genome Institute of Singapore"
__license__ = "The MIT License (MIT)"


# only dump() and following do not automatically create aliases
yaml.Dumper.ignore_aliases = lambda *args: True


PIPELINE_BASEDIR = os.path.dirname(sys.argv[0])
CFG_DIR = os.path.join(PIPELINE_BASEDIR, "cfg")

# same as folder name. also used for cluster job names
PIPELINE_NAME = "gatk"

MARK_DUPS = True

# global logger
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '[{asctime}] {levelname:8s} {filename} {message}', style='{'))
logger.addHandler(handler)


def main():
    """main function
    """

    default_parser = default_argparser(CFG_DIR)
    parser = argparse.ArgumentParser(description=__doc__.format(
        PIPELINE_NAME=PIPELINE_NAME, PIPELINE_VERSION=get_pipeline_version()),
                                     parents=[default_parser])

    # pipeline specific args
    parser.add_argument('-1', "--fq1", nargs="+",
                        help="FastQ file/s (gzip only)."
                        " Multiple input files supported (auto-sorted)."
                        " Note: each file (or pair) gets a unique read-group id."
                        " Collides with --sample-cfg.")
    parser.add_argument('-2', "--fq2", nargs="+",
                        help="FastQ file/s (if paired) (gzip only). See also --fq1")
    parser.add_argument('-s', "--sample",
                        help="Sample name. Collides with --sample-cfg.")
    parser.add_argument('-t', "--seqtype", required=True,
                        choices=['WGS', 'WES', 'targeted'],
                        help="Sequencing type")
    parser.add_argument('-l', "--bed",
                        help="Bed file listing regions of interest."
                        " Required for WES and targeted sequencing.")
    parser.add_argument('--raw-bam',
                        help="Advanced: Injects raw (pre dedup, BQSR etc.) BAM (overwrites fq options)."
                        " WARNING: reference and pre-processing need to match pipeline requirements")
    parser.add_argument('--bam-only', action='store_true',
                        help="Don't call variants, just process BAM file")

    args = parser.parse_args()

    # Repeateable -v and -q for setting logging level.
    # See https://www.reddit.com/r/Python/comments/3nctlm/what_python_tools_should_i_be_using_on_every/
    # and https://gist.github.com/andreas-wilm/b6031a84a33e652680d4
    # script -vv -> DEBUG
    # script -v -> INFO
    # script -> WARNING
    # script -q -> ERROR
    # script -qq -> CRITICAL
    # script -qqq -> no logging at all
    logger.setLevel(logging.WARN + 10*args.quiet - 10*args.verbose)
    aux_logger.setLevel(logging.WARN + 10*args.quiet - 10*args.verbose)

    if os.path.exists(args.outdir):
        logger.fatal("Output directory %s already exists", args.outdir)
        sys.exit(1)


    # samples is a dictionary with sample names as key (mostly just
    # one) and readunit keys as value. readunits is a dict with
    # readunits (think: fastq pairs with attributes) as value
    if args.sample_cfg:
        if any([args.fq1, args.fq2, args.sample, args.raw_bam]):
            logger.fatal("Config file overrides fastq and sample input arguments."
                         " Use one or the other")
            sys.exit(1)
        if not os.path.exists(args.sample_cfg):
            logger.fatal("Config file %s does not exist", args.sample_cfg)
            sys.exit(1)
        samples, readunits = get_samples_and_readunits_from_cfgfile(args.sample_cfg)

    else:
        samples = dict()
        readunits = dict()

        if args.raw_bam:
            if not args.sample:
                logger.fatal("Need sample name if not using config file")
                sys.exit(1)
            samples[args.sample] = []
            assert os.path.exists(args.raw_bam)

        else:
            if not all([args.fq1, args.sample]):
                logger.fatal("Need at least fq1 and sample if not using config file")
                sys.exit(1)

            readunits = get_readunits_from_args(args.fq1, args.fq2)
            # all readunits go into this one sample specified on the command-line
            samples = dict()
            samples[args.sample] = list(readunits.keys())

    if args.seqtype in ['WES', 'targeted']:
        if not args.bed:
            logger.fatal("Analysis of exome and targeted sequence runs requires a bed file")
            sys.exit(1)
        else:
            if not os.path.exists(args.bed):
                logger.fatal("Bed file %s does not exist", args.sample_cfg)
                sys.exit(1)

    # turn arguments into user_data that gets merged into pipeline config
    #
    # generic data first
    user_data = dict()
    user_data['mail_on_completion'] = not args.no_mail
    user_data['mail_address'] = args.mail_address
    user_data['readunits'] = readunits
    user_data['samples'] = samples
    if args.name:
        user_data['analysis_name'] = args.name
    user_data['seqtype'] = args.seqtype
    user_data['intervals'] = os.path.abspath(args.bed) if args.bed else None# always safe, might be used for WGS as well
    user_data['mark_dups'] = MARK_DUPS
    user_data['bam_only'] = args.bam_only

    if args.extra_conf:
        for keyvalue in args.extra_conf:
            logger.critical("keyvalue=%s split=%s", keyvalue, keyvalue.split(":"))
            assert keyvalue.count(":") == 1, ("Invalid argument for extra-conf")
            k, v = keyvalue.split(":")
            user_data[k] = v
        
    pipeline_handler = PipelineHandler(
        PIPELINE_NAME, PIPELINE_BASEDIR,
        args.outdir, user_data,
        master_q=args.master_q,
        slave_q=args.slave_q,
        params_cfgfile=args.params_cfg,
        modules_cfgfile=args.modules_cfg,
        refs_cfgfile=args.references_cfg,
        cluster_cfgfile=get_cluster_cfgfile(CFG_DIR))
    pipeline_handler.setup_env()

    # inject existing BAM by symlinking (everything upstream is temporary anyway)
    if args.raw_bam:
        # target as defined in Snakefile!
        target = os.path.join(args.outdir, "out", args.sample,
                              "{}.bwamem.bam".format(args.sample))
        os.makedirs(os.path.dirname(target))
        os.symlink(os.path.abspath(args.raw_bam), target)

    pipeline_handler.submit(args.no_run)


if __name__ == "__main__":
    main()
