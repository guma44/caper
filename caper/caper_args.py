#!/usr/bin/env python3
"""CaperArgs: Command line arguments parser for Caper

Author:
    Jin Lee (leepc12@gmail.com) at ENCODE-DCC
"""

import argparse
from configparser import ConfigParser
import sys
import os
from distutils.util import strtobool
from collections import OrderedDict
from .caper_backend import BACKENDS, BACKENDS_WITH_ALIASES
from .caper_backend import BACKEND_GCP, BACKEND_AWS, BACKEND_LOCAL
from .caper_backend import BACKEND_SLURM, BACKEND_SGE, BACKEND_PBS
from .caper_backend import BACKEND_ALIAS_LOCAL
from .caper_backend import BACKEND_ALIAS_GOOGLE, BACKEND_ALIAS_AMAZON
from .caper_backend import BACKEND_ALIAS_SHERLOCK, BACKEND_ALIAS_SCG


__version__ = '0.5.0'

DEFAULT_JAVA_HEAP_SERVER = '7G'
DEFAULT_JAVA_HEAP_RUN = '1G'
DEFAULT_CAPER_CONF = '~/.caper/default.conf'
DEFAULT_SINGULARITY_CACHEDIR = '~/.caper/singularity_cachedir'
DEFAULT_CROMWELL_JAR = 'https://github.com/broadinstitute/cromwell/releases/download/42/cromwell-42.jar'
DEFAULT_MYSQL_DB_IP = 'localhost'
DEFAULT_MYSQL_DB_PORT = 3306
DEFAULT_DB_TIMEOUT_MS = 30000
DEFAULT_MAX_CONCURRENT_WORKFLOWS = 40
DEFAULT_MAX_CONCURRENT_TASKS = 1000
DEFAULT_MAX_RETRIES = 1
DEFAULT_PORT = 8000
DEFAULT_IP = 'localhost'
DEFAULT_FORMAT = 'id,status,name,str_label,user,submission'
DEFAULT_DEEPCOPY_EXT = 'json,tsv'
DEFAULT_SERVER_HEARTBEAT_FILE = '~/.caper/default_server_heartbeat'
DEFAULT_SERVER_HEARTBEAT_TIMEOUT_MS = 120000
DEFAULT_CONF_CONTENTS = '\n\n'
DYN_FLAGS = ['--singularity', '--docker']
INVALID_EXT_FOR_DYN_FLAG = '.wdl'
DEFAULT_CONF_CONTENTS_LOCAL = """backend=local

tmp-dir=
"""
DEFAULT_CONF_CONTENTS_SHERLOCK = """backend=slurm
slurm-partition=

tmp-dir=
"""
DEFAULT_CONF_CONTENTS_SCG = """backend=slurm
slurm-account=

tmp-dir=
"""
DEFAULT_CONF_CONTENTS_SLURM = """backend=slurm

# define one of the followings (or both) according to your
# cluster's SLURM configuration.
slurm-partition=
slurm-account=

tmp-dir=
"""
DEFAULT_CONF_CONTENTS_SGE = """backend=sge
sge-pe=

tmp-dir=
"""
DEFAULT_CONF_CONTENTS_PBS = """backend=pbs
"""
DEFAULT_CONF_CONTENTS_AWS = """backend=aws
aws-batch-arn=
aws-region=
out-s3-bucket=

tmp-dir=
"""
DEFAULT_CONF_CONTENTS_GCP = """backend=gcp
gcp-prj=
out-gcs-bucket=

tmp-dir=
"""


def process_dyn_flags(remaining_args, dyn_flags,
                      invalid_ext_for_dyn_flag):
    """Special treatment for dynamic flags which can be used as
    both params and flags

    Example1: caper run --docker atac.wdl
    atac.wdl can be misinterpreated as a docker image
    This function switches the order of --docker and atac.wdl
    Result1: caper run atac.wdl --docker

    Example2: caper run --singularity --docker atac.wdl
    This example switches twice. This is just for an example
    --singularity and --docker are mutually exclusive
    Result2: caper run atac.wdl --singularity --docker
    """
    for f in DYN_FLAGS:
        if f in remaining_args:
            loc = remaining_args.index(f)
            if loc < len(remaining_args) - 1:
                if remaining_args[loc + 1].endswith(INVALID_EXT_FOR_DYN_FLAG):
                    remaining_args[loc], remaining_args[loc + 1] = \
                        remaining_args[loc + 1], remaining_args[loc]
    return remaining_args


def init_caper_conf(args):
    backend = args.get('platform')
    assert(backend in BACKENDS_WITH_ALIASES)
    if backend in (BACKEND_LOCAL, BACKEND_ALIAS_LOCAL):
        contents = DEFAULT_CONF_CONTENTS_LOCAL
    elif backend == BACKEND_ALIAS_SHERLOCK:
        contents = DEFAULT_CONF_CONTENTS_SHERLOCK
    elif backend == BACKEND_ALIAS_SCG:
        contents = DEFAULT_CONF_CONTENTS_SCG
    elif backend == BACKEND_SLURM:
        contents = DEFAULT_CONF_CONTENTS_SLURM
    elif backend == BACKEND_SGE:
        contents = DEFAULT_CONF_CONTENTS_SGE
    elif backend == BACKEND_PBS:
        contents = DEFAULT_CONF_CONTENTS_PBS
    elif backend in (BACKEND_GCP, BACKEND_ALIAS_GOOGLE):
        contents = DEFAULT_CONF_CONTENTS_GCP
    elif backend in (BACKEND_AWS, BACKEND_ALIAS_AMAZON):
        contents = DEFAULT_CONF_CONTENTS_AWS
    else:
        raise Exception('Unsupported platform/backend/alias.')

    conf_file = os.path.expanduser(args.get('conf'))
    with open(conf_file, 'w') as fp:
        fp.write(contents + '\n')


def parse_caper_arguments():
    """Argument parser for Caper
    """
    # write default conf file if not exists
    default_caper_conf = os.path.expanduser(DEFAULT_CAPER_CONF)
    if not os.path.exists(default_caper_conf):
        os.makedirs(os.path.dirname(default_caper_conf), exist_ok=True)
        with open(default_caper_conf, 'w') as fp:
            fp.write(DEFAULT_CONF_CONTENTS)

    conf_parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False)
    conf_parser.add_argument('-c', '--conf', help='Specify config file',
                             metavar='FILE',
                             default=DEFAULT_CAPER_CONF)
    conf_parser.add_argument('-v', '--version', action='store_true',
                             help='Show version')
    known_args, remaining_argv = conf_parser.parse_known_args()
    if known_args.version is not None and known_args.version:
        print(__version__)
        conf_parser.exit()
    process_dyn_flags(remaining_argv, DYN_FLAGS, INVALID_EXT_FOR_DYN_FLAG)

    # read conf file if it exists
    defaults = {}

    if known_args.conf is not None:
        # resolve tilde (~) in conf path
        known_args.conf = os.path.expanduser(known_args.conf)
        if os.path.exists(known_args.conf):
            config = ConfigParser()
            with open(known_args.conf, 'r') as fp:
                conf_contents = fp.read()
            if '[defaults]' not in conf_contents.split('\n'):
                conf_contents = '[defaults]\n' + conf_contents
            config.read_string(conf_contents)
            d = dict(config.items('defaults'))
            # remove keys with empty string
            d = {k: v for k, v in d.items() if v != ''}
            # replace - with _
            defaults.update({k.replace('-', '_'): v for k, v in d.items()})

    parser = argparse.ArgumentParser(parents=[conf_parser])
    subparser = parser.add_subparsers(dest='action')

    parent_init = argparse.ArgumentParser(add_help=False)
    choices = list(BACKENDS)
    choices.pop(choices.index(BACKEND_LOCAL))
    choices += [BACKEND_ALIAS_SHERLOCK, BACKEND_ALIAS_SCG, BACKEND_ALIAS_LOCAL]
    parent_init.add_argument('platform',
        choices=choices,
        help='Platform to initialize Caper for.')

    # all
    parent_all = argparse.ArgumentParser(add_help=False)
    parent_all.add_argument('--dry-run',
        action='store_true',
        help='Caper does not take any action.')

    # run, server, submit
    parent_backend = argparse.ArgumentParser(add_help=False)
    parent_backend.add_argument(
        '-b', '--backend', help='Backend to run a workflow')

    # run, server
    parent_host = argparse.ArgumentParser(add_help=False)

    group_db = parent_host.add_argument_group(
        title='General DB settings (for both file DB and MySQL DB)')
    group_db.add_argument(
        '--db-timeout', type=int, default=DEFAULT_DB_TIMEOUT_MS,
        help='Milliseconds to wait for DB (both for file DB and MySQL DB) '
             'connection.')

    group_file_db = parent_host.add_argument_group(
        title='HyperSQL file DB arguments')
    group_file_db.add_argument(
        '--file-db', '-d',
        help='Default DB file for Cromwell\'s built-in HyperSQL database.')
    group_file_db.add_argument(
        '--no-file-db', '-n', action='store_true',
        help='Disable file DB for Cromwell\'s built-in HyperSQL database. '
             'An in-memory DB will still be available for server mode.')

    group_mysql = parent_host.add_argument_group(
        title='MySQL arguments')
    group_mysql.add_argument(
        '--mysql-db-ip', default=DEFAULT_MYSQL_DB_IP,
        help='MySQL Database IP address (e.g. localhost)')
    group_mysql.add_argument(
        '--mysql-db-port', default=DEFAULT_MYSQL_DB_PORT,
        help='MySQL Database TCP/IP port (e.g. 3306)')
    group_mysql.add_argument(
        '--mysql-db-user', help='MySQL Database username')
    group_mysql.add_argument(
        '--mysql-db-password', help='MySQL Database password')

    group_cromwell = parent_host.add_argument_group(
        title='Cromwell settings')
    group_cromwell.add_argument(
        '--cromwell', default=DEFAULT_CROMWELL_JAR,
        help='Path or URL for Cromwell JAR file')
    group_cromwell.add_argument(
        '--max-concurrent-tasks', default=DEFAULT_MAX_CONCURRENT_TASKS,
        type=int,
        help='Number of concurrent tasks. '
             '"config.concurrent-job-limit" in Cromwell backend configuration '
             'for each backend')
    group_cromwell.add_argument(
        '--max-concurrent-workflows', default=DEFAULT_MAX_CONCURRENT_WORKFLOWS,
        type=int,
        help='Number of concurrent workflows. '
             '"system.max-concurrent-workflows" in backend configuration')
    group_cromwell.add_argument(
        '--max-retries', default=DEFAULT_MAX_RETRIES,
        type=int,
        help='Number of retries for failing tasks. '
             'equivalent to "maxRetries" in workflow options JSON file.')
    group_cromwell.add_argument(
        '--disable-call-caching', action='store_true',
        help='Disable Cromwell\'s call caching, which re-uses outputs from '
             'previous workflows')
    group_cromwell.add_argument(
        '--backend-file',
        help='Custom Cromwell backend configuration file to override all')

    group_local = parent_host.add_argument_group(
        title='local backend arguments')
    group_local.add_argument(
        '--out-dir', default='.', help='Output directory for local backend')
    group_local.add_argument(
        '--tmp-dir', help='Temporary directory for local backend')

    group_gc = parent_host.add_argument_group(
        title='GC backend arguments')
    group_gc.add_argument('--gcp-prj', help='GC project')
    group_gc.add_argument('--gcp-zones', help='GCP zones (e.g. us-west1-b,'
                                              'us-central1-b)')
    group_gc.add_argument(
        '--out-gcs-bucket', help='Output GCS bucket for GC backend')
    group_gc.add_argument(
        '--tmp-gcs-bucket', help='Temporary GCS bucket for GC backend')

    group_aws = parent_host.add_argument_group(
        title='AWS backend arguments')
    group_aws.add_argument('--aws-batch-arn', help='ARN for AWS Batch')
    group_aws.add_argument('--aws-region', help='AWS region (e.g. us-west-1)')
    group_aws.add_argument(
        '--out-s3-bucket', help='Output S3 bucket for AWS backend')
    group_aws.add_argument(
        '--tmp-s3-bucket', help='Temporary S3 bucket for AWS backend')
    group_aws.add_argument(
        '--use-gsutil-over-aws-s3', action='store_true',
        help='Use gsutil instead of aws s3 CLI even for S3 buckets.')

    parent_http_auth = argparse.ArgumentParser(add_help=False)
    group_http = parent_http_auth.add_argument_group(
        title='HTTP/HTTPS authentication arguments')
    group_http.add_argument(
        '--http-user',
        help='Username to download data from private URLs. '
             'SECURITY WARNING: '
             'Your username will be exposed in a command line so that '
             'other users on your system can see it with "ps" command.')
    group_http.add_argument(
        '--http-password',
        help='Password to to download data from private URLs. '
             'SECURITY WARNING: '
             'Your password will be exposed in a command line so that '
             'other users on your system can see it with "ps" command.')
    group_http.add_argument(
        '--use-netrc', action='store_true',
        help='RECOMMENDED: Use ~/.netrc for HTTP/HTTPS authentication. '
             'See details about how to make a ~/.netrc file at '
             'https://github.com/bagder/everything-curl/blob/master/'
             'usingcurl-netrc.md')

    # run, submit
    parent_submit = argparse.ArgumentParser(add_help=False)

    parent_submit.add_argument(
        'wdl',
        help='Path, URL or URI for WDL script '
             'Example: /scratch/my.wdl, gs://some/where/our.wdl, '
             'http://hello.com/world/your.wdl')
    parent_submit.add_argument(
        '-i', '--inputs', help='Workflow inputs JSON file')
    parent_submit.add_argument(
        '-o', '--options', help='Workflow options JSON file')
    parent_submit.add_argument(
        '-l', '--labels',
        help='Workflow labels JSON file')
    parent_submit.add_argument(
        '-p', '--imports',
        help='Zip file of imported subworkflows')
    parent_submit.add_argument(
        '-s', '--str-label',
        help='Caper\'s special label for a workflow '
             'This label will be added to a workflow labels JSON file '
             'as a value for a key "caper-label". '
             'DO NOT USE IRREGULAR CHARACTERS. USE LETTERS, NUMBERS, '
             'DASHES AND UNDERSCORES ONLY (^[A-Za-z0-9\\-\\_]+$) '
             'since this label is used to compose a path for '
             'workflow\'s temporary directory (tmp_dir/label/timestamp/)')
    parent_submit.add_argument(
        '--hold', action='store_true',
        help='Put a hold on a workflow when submitted to a Cromwell server.')
    parent_submit.add_argument(
        '--singularity-cachedir', default=DEFAULT_SINGULARITY_CACHEDIR,
        help='Singularity cache directory. Equivalent to exporting an '
             'environment variable SINGULARITY_CACHEDIR. '
             'Define it to prevent repeatedly building a singularity image '
             'for every pipeline task')
    # server
    parent_server = argparse.ArgumentParser(add_help=False)
    parent_server.add_argument(
        '--java-heap-server', default=DEFAULT_JAVA_HEAP_SERVER,
        help='Cromwell Java heap size for "server" mode (java -Xmx)')

    # run
    parent_run = argparse.ArgumentParser(add_help=False)
    parent_run.add_argument(
        '-m', '--metadata-output',
        help='An optional directory path to output metadata JSON file')
    parent_run.add_argument(
        '--java-heap-run', default=DEFAULT_JAVA_HEAP_RUN,
        help='Cromwell Java heap size for "run" mode (java -Xmx)')

    parent_submit.add_argument(
        '--no-deepcopy', action='store_true',
        help='(IMPORTANT) --deepcopy has been deprecated. '
             'Deepcopying is now activated by default. '
             'This flag disables deepcopy for '
             'JSON (.json), TSV (.tsv) and CSV (.csv) '
             'files specified in an input JSON file (--inputs). '
             'Find all path/URI string values in an input JSON file '
             'and make copies of files on a local/remote storage '
             'for a target backend. Make sure that you have installed '
             'gsutil for GCS and aws for S3.')
    parent_submit.add_argument(
        '--deepcopy-ext', default=DEFAULT_DEEPCOPY_EXT,
        help='Comma-separated list of file extensions to be deepcopied')

    group_dep = parent_submit.add_argument_group(
        title='dependency resolver for all backends',
        description=''
        'Cloud-based backends (gc and aws) will only use Docker '
        'so that "--docker URI_FOR_DOCKER_IMG" must be specified '
        'in the command line argument or as a comment "#CAPER '
        'docker URI_FOR_DOCKER_IMG" in a WDL file')
    group_dep.add_argument(
        '--docker', nargs='*',
        help='URI for Docker image (e.g. ubuntu:latest). '
        'This can also be used as a flag to use Docker image address '
        'defined in your WDL file as a comment ("#CAPER docker").')
    group_dep_local = parent_submit.add_argument_group(
        title='dependency resolver for local backend',
        description=''
        'Singularity is for local backend only. Other backends '
        '(gcp and aws) will use Docker only. '
        'Local backend defaults to not use any container-based methods. '
        'Use "--singularity" or "--docker" to use containers')
    group_dep_local.add_argument(
        '--singularity', nargs='*',
        help='URI or path for Singularity image '
             '(e.g. ~/.singularity/ubuntu-latest.simg, '
             'docker://ubuntu:latest, shub://vsoch/hello-world). '
             'This can also be used as a flag to use Docker image address '
             'defined in your WDL file as a comment ("#CAPER singularity").')
    group_dep_local.add_argument(
        '--no-build-singularity', action='store_true',
        help='Do not build singularity image before running a workflow. ')

    group_slurm = parent_submit.add_argument_group('SLURM arguments')
    group_slurm.add_argument('--slurm-partition', help='SLURM partition')
    group_slurm.add_argument('--slurm-account', help='SLURM account')
    group_slurm.add_argument(
        '--slurm-extra-param',
        help='SLURM extra parameters. Must be double-quoted')

    group_sge = parent_submit.add_argument_group('SGE arguments')
    group_sge.add_argument(
        '--sge-pe', help='SGE parallel environment. Check with "qconf -spl"')
    group_sge.add_argument(
        '--sge-queue', help='SGE queue. Check with "qconf -sql"')
    group_sge.add_argument(
        '--sge-extra-param',
        help='SGE extra parameters. Must be double-quoted')

    group_pbs = parent_submit.add_argument_group('PBS arguments')
    group_pbs.add_argument(
        '--pbs-queue', help='PBS queue')
    group_pbs.add_argument(
        '--pbs-extra-param',
        help='PBS extra parameters. Must be double-quoted')

    # list, metadata, abort
    parent_search_wf = argparse.ArgumentParser(add_help=False)
    parent_search_wf.add_argument(
        'wf_id_or_label', nargs='*',
        help='List of workflow IDs to find matching workflows to '
             'commit a specified action (list, metadata and abort). '
             'Wildcards (* and ?) are allowed.')

    parent_server_client = argparse.ArgumentParser(add_help=False)
    parent_server_client.add_argument(
        '--port', default=DEFAULT_PORT, type=int,
        help='Port for Caper server')
    parent_server_client.add_argument(
        '--ip', default=DEFAULT_IP,
        help='IP address for Caper server')
    parent_server_client.add_argument(
        '--server-heartbeat-file',
        default=DEFAULT_SERVER_HEARTBEAT_FILE,
        help='Heartbeat file for Caper clients to get IP and port of a server')
    parent_server_client.add_argument(
        '--server-heartbeat-timeout',
        default=DEFAULT_SERVER_HEARTBEAT_TIMEOUT_MS,
        help='Timeout for a heartbeat file in Milliseconds. '
             'A heartbeat file older than '
             'this interval will be ignored.')

    parent_list = argparse.ArgumentParser(add_help=False)
    parent_list.add_argument(
        '-f', '--format', default=DEFAULT_FORMAT,
        help='Comma-separated list of items to be shown for "list" '
        'subcommand. Any key name in workflow JSON from Cromwell '
        'server\'s response is allowed. '
        'Available keys are "id" (workflow ID), "status", "str_label", '
        '"name" (WDL/CWL name), "submission" (date/time), "start", '
        '"end" and "user". '
        '"str_label" is a special key for Caper. See help context '
        'of "--str-label" for details')
    parent_list.add_argument(
        '--hide-result-before',
        help='Hide workflows submitted before this date/time. '
             'Use the same (or shorter) date/time format shown in '
             '"caper list". '
             'e.g. 2019-06-13, 2019-06-13T10:07')
    # troubleshoot
    parent_troubleshoot = argparse.ArgumentParser(add_help=False)
    parent_troubleshoot.add_argument(
        '--show-completed-task', action='store_true',
        help='Show information about completed tasks.')

    p_init = subparser.add_parser(
        'init',
        help='Initialize Caper\'s configuration file. THIS WILL OVERWRITE ON '
             'A SPECIFIED(-c)/DEFAULT CONF FILE. e.g. ~/.caper/default.conf.',
        parents=[parent_init])
    p_run = subparser.add_parser(
        'run', help='Run a single workflow without server',
        parents=[parent_all, parent_submit, parent_run, parent_host, parent_backend,
                 parent_http_auth])
    p_server = subparser.add_parser(
        'server', help='Run a Cromwell server',
        parents=[parent_all, parent_server_client, parent_server, parent_host,
                 parent_backend, parent_http_auth])
    p_submit = subparser.add_parser(
        'submit', help='Submit a workflow to a Cromwell server',
        parents=[parent_all, parent_server_client, parent_submit,
                 parent_backend, parent_http_auth])
    p_abort = subparser.add_parser(
        'abort', help='Abort running/pending workflows on a Cromwell server',
        parents=[parent_all, parent_server_client, parent_search_wf])
    p_unhold = subparser.add_parser(
        'unhold', help='Release hold of workflows on a Cromwell server',
        parents=[parent_all, parent_server_client, parent_search_wf])
    p_list = subparser.add_parser(
        'list', help='List running/pending workflows on a Cromwell server',
        parents=[parent_all, parent_server_client, parent_search_wf,
                 parent_list])
    p_metadata = subparser.add_parser(
        'metadata',
        help='Retrieve metadata JSON for workflows from a Cromwell server',
        parents=[parent_all, parent_server_client, parent_search_wf])
    p_troubleshoot = subparser.add_parser(
        'troubleshoot',
        help='Troubleshoot workflow problems from metadata JSON file or '
             'workflow IDs',
        parents=[parent_all, parent_troubleshoot, parent_server_client, parent_search_wf,
                 parent_http_auth])
    p_debug = subparser.add_parser(
        'debug',
        help='Identical to "troubleshoot"',
        parents=[parent_all, parent_troubleshoot, parent_server_client, parent_search_wf,
                 parent_http_auth])

    for p in [p_init, p_run, p_server, p_submit, p_abort, p_unhold, p_list,
              p_metadata, p_troubleshoot, p_debug]:
        p.set_defaults(**defaults)

    if len(sys.argv[1:]) == 0:
        parser.print_help()
        parser.exit()
    # parse all args
    args = parser.parse_args(remaining_argv)

    # convert to dict
    args_d = vars(args)

    # string to boolean
    for k in [
        'dry_run',
        'disable_call_caching',
        'use_gsutil_over_aws_s3',
        'hold',
        'no_deepcopy',
        'no_build_singularity',
        'no_file_db',
        'use_netrc',
        'show_completed_task']:
        v = args_d.get(k)
        if v is not None and isinstance(v, str):
            args_d[k] = bool(strtobool(v))

    # string to int
    for k in [
        'db_timeout',
        'max_retries',
        'max_concurrent_tasks',
        'max_concurrent_workflows',
        'server_heartbeat_timeout',
        'port']:
        v = args_d.get(k)
        if v is not None and isinstance(v, str):
            args_d[k] = int(v)

    # if action is 'init' then initialize Conf and exit
    action = args_d['action']
    if action == 'init':
        init_caper_conf(args_d)
        sys.exit(0)

    return args_d
