# Copyright 2019 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#            http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
`utils.py`
Utility functions.
"""
from datetime import datetime
import argparse
import collections
import importlib
import logging
import os
import pprint
import re
import sys
import warnings

import pytz
import yaml

from google.auth._default import _CLOUD_SDK_CREDENTIALS_WARNING

LOGGER = logging.getLogger(__name__)


def parse_config(path):
    """Load a yaml configuration file and resolve environment variables in it.

    Args:
        path (str): the path to the yaml file.

    Returns:
        dict: Parsed YAML dictionary.
    """
    # pattern for global vars: look for ${word}
    pattern = re.compile(r'.*?\${(\w+)}.*?')

    def replace_env_vars(content):
        """Replace environment variables from content.

        Args:
            content (str): String to parse.

        Returns:
            str: the parsed string with the env var replaced.
        """
        match = pattern.findall(content)
        if match:
            full_value = content
            for var in match:
                try:
                    full_value = full_value.replace(f'${{{var}}}',
                                                    os.environ[var])
                except KeyError as exception:
                    LOGGER.error(
                        f'Environment variable "{var}" should be set.')
                    raise exception
            content = full_value
        return content

    with open(path) as config:
        content = config.read()
        content = replace_env_vars(content)
        data = yaml.safe_load(content)
    LOGGER.debug(pprint.pformat(data))
    return data


def setup_logging():
    """Setup logging for the CLI."""
    debug = os.environ.get("DEBUG", "0")
    print("DEBUG: %s" % debug)
    if debug == "1":
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(stream=sys.stdout,
                        level=level,
                        format='%(name)s - %(levelname)s - %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S')
    logging.getLogger('googleapiclient').setLevel(logging.ERROR)

    # Ingore annoying Cloud SDK warning
    warnings.filterwarnings("ignore", message=_CLOUD_SDK_CREDENTIALS_WARNING)


def get_human_time(timestamp, timezone="Europe/Paris"):
    """Get human-readable timestamp from UNIX timestamp.

    Args:
        timestamp (int): UNIX timestamp.

    Returns:
        str: Formatted timestamp in ISO format.
    """
    date = datetime.fromtimestamp(timestamp, pytz.timezone(timezone))
    timeformat = '%Y-%m-%dT%H:%M:%S.%fZ'
    return datetime.strftime(date, timeformat)


def normalize(path):
    """Converts a path to an absolute path.

    Args:
        path (str): Input path.

    Returns:
        str: Absolute path.
    """
    return os.path.abspath(path)


def get_backend_cls(backend):
    """Get backend class.

    Args:
        backend (str): Exporter type.

    Returns:
        class: Backend class.
    """
    filename = re.sub(r'(?<!^)(?=[A-Z])', '_', backend).lower()
    return import_dynamic(f'slo_generator.backends.{filename}',
                          f'{backend}Backend',
                          prefix="backend")


def get_exporter_cls(exporter):
    """Get exporter class.

    Args:
        exporter (str): Backend type.

    Returns:
        class: Exporter class.
    """
    filename = re.sub(r'(?<!^)(?=[A-Z])', '_', exporter).lower()
    return import_dynamic(f'slo_generator.exporters.{filename}',
                          f'{exporter}Exporter',
                          prefix="exporter")


def import_dynamic(package, name, prefix="class"):
    """Import class or method dynamically from package and name.

    Args:
        package: Where the method or class is located in the import path.
        name: Name of method or class.

    Returns:
        obj: Imported class or method object.
    """
    try:
        return getattr(importlib.import_module(package), name)
    except Exception as exception:  # pylint: disable=W0703
        LOGGER.error(
            f'{prefix.capitalize()} "{package}.{name}" not found, check '
            f'package and class name are valid, or that importing it doesn\'t '
            f'result in an exception.')
        LOGGER.debug(exception)
        sys.exit(1)


def dict_snake_to_caml(data):
    """Convert dictionary with keys written in snake_case to another one with
    keys written in CamlCase.

    Args:
        data (dict): Input dictionary.

    Returns:
        dict: Output dictionary.
    """
    def snake_to_caml(word):
        return re.sub('_.', lambda x: x.group()[1].upper(), word)

    return apply_func_dict(data, snake_to_caml)


def apply_func_dict(data, func):
    """Apply function on a dictionary keys.

    Args:
        data (dict): Input dictionary.

    Returns:
        dict: Output dictionary.
    """
    if isinstance(data, collections.Mapping):
        return {func(k): apply_func_dict(v, func) for k, v in data.items()}
    return data


def str2bool(string):
    """Convert a string to a boolean.

    Args:
        string (str): String to convert

    Returns:
        bool: Boolean value.

    Raises:
        `argparse.ArgumentTypeError`: IF no acceptable boolean string is found.
    """
    if isinstance(string, bool):
        return string
    if string.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    if string.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    raise argparse.ArgumentTypeError('Boolean value expected.')
