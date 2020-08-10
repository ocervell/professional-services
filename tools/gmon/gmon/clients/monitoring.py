# Copyright 2020 Google Inc.
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
`monitoring.py`
Stackdriver Monitoring Client. Wraps the official MetricServiceClient for
CLI use.
"""
import json
import logging
import re
import time

from google.cloud.monitoring_v3 import (MetricServiceClient, enums, types)
from google.protobuf.json_format import MessageToDict
from google.api_core import exceptions

from .utils import decorate, to_json

LOGGER = logging.getLogger(__name__)


@decorate(to_json, methods=['get', 'create', 'list', 'delete', 'inspect'])
class MetricsClient:
    """Client for Cloud Monitoring Metrics.

    Provides a simpler interface than the original client.

    Args:
        project_id (str): Stackdriver host project id (workspace) to query
            metrics from.
    """
    def __init__(self, project_id):
        self.client = MetricServiceClient()
        self.project_id = project_id
        self.project = self.client.project_path(project_id)

    def get(self, metric_type):
        """Get a metric descriptor from metric type.
        If the metric is not found, try listing all metrics from project and
        grab the corresponding matches.

        Args:
            metric_type (str): The metric type (e.g: custom.googleapis.com/test)
                or a regex of the metric type.

        Returns:
            iterator: Metric descriptor API response.
        """
        try:
            return self.client.get_metric_descriptor(
                f'{self.project}/metricDescriptors/{metric_type}')
        except exceptions.NotFound:
            metric_type = self.get_approx(metric_type)
            return self.client.get_metric_descriptor(
                f'{self.project}/metricDescriptors/{metric_type}')

    def get_approx(self, metric_type, interactive=True):
        """Get metric descriptors matching a regex of the metric_type.

        Args:
            metric_type (str): Metric type regex.
            interactive (bool): Interactive mode enabled (default: True).

        Returns:
            str: The metric type chosen by the user through interactive input,
                or inferred by the tool.
        """
        LOGGER.info(f'Metric type "{metric_type}" not found (no exact match). '
                    f'Trying with regex ...')
        results = self.list(pattern=metric_type)
        matches = [(x['type'], x['name'].split('/')[1]) for x in list(results)]
        if len(matches) == 0:
            LOGGER.error(
                f'No partial result matched your query "{metric_type}".')
            raise  # re-raise NotFound exception
        elif len(matches) == 1:
            metric_type = matches[0][0]
            project_id = matches[0][1]
            LOGGER.info(
                f'Found exactly one metric "{metric_type}" in project "{project_id}" matching regex.'
            )
        elif interactive:
            LOGGER.info(f'Found multiple metrics matching regex.')
            for ix, (metric_type, project_id) in enumerate(matches):
                print(f'{ix}. {metric_type} ({project_id})')
            ix = int(input(f'Enter your choice: '))
            metric_type = matches[ix][0]
            project_id = matches[ix][1]
        else:  # non-interactive mode, take first match
            metric_type = matches[0][0]
            project_id = matches[0][1]
        self.switch_project(project_id)
        return metric_type

    def create(self,
               metric_type,
               metric_kind='GAUGE',
               value_type='DOUBLE',
               description='N/A'):
        """Create a metric descriptor.

        Args:
            metric_type (str): Metric type.
            metric_kind (str, optional): Metric kind.
            value_type (str, optional): Value type.
            description (str, optional): Description.

        Returns:
            obj: Metric descriptor.
        """
        descriptor = types.MetricDescriptor()
        if metric_type.startswith('custom.googleapis.com/'):
            descriptor.type = metric_type
        else:
            descriptor.type = 'custom.googleapis.com/%s' % metric_type
        descriptor.metric_kind = (getattr(enums.MetricDescriptor.MetricKind,
                                          metric_kind))
        descriptor.value_type = (getattr(enums.MetricDescriptor.ValueType,
                                         value_type))
        descriptor.description = description
        LOGGER.info(f'Creating metric descriptor "{descriptor.type}" ...')
        return self.client.create_metric_descriptor(self.project, descriptor)

    def delete(self, metric_type):
        """Delete a metric descriptor.

        Args:
            metric_type (str): Metric type to delete.

        Returns:
            obj: Metric descriptor.
        """
        LOGGER.info(f'Deleting metric descriptor "{metric_type}" ...')
        return self.client.delete_metric_descriptor(
            f'{self.project}/metricDescriptors/{metric_type}')

    def list(self, pattern=None):
        """List all metric descriptors in project.

        Args:
            pattern (str, optional): Optional pattern to filter on
                specific metric descriptors.
            filter (dict): Filter fields.

        Returns:
            list: List of metric descriptors.
        """
        LOGGER.debug(f'Listing metrics in project "{self.project_id}" ...')
        descriptors = list(self.client.list_metric_descriptors(self.project))
        if pattern:
            descriptors = [
                x for x in descriptors if bool(re.search(pattern, x.type))
            ]
        return descriptors

    def delete_unused(self, pattern=None, window=1, interactive=True):
        """Delete unused metric.

        Args:
            pattern (str): Regex pattern to filter on.
            window (int): Window to check for metric data in days. If no
                datapoints were written during this window, add to delete list.

        Returns:
            dict: Data about metrics.
        """
        LOGGER.info(
            f'Inspecting metrics to find unused ones in "{self.project_id}". '
            f'The bigger the --window, the longest time this will take ...')
        window_seconds = window * 86400  # in seconds
        descriptors = self.list(pattern=pattern)
        delete_list = []
        keep_list = []
        for d in descriptors:
            metric_type = d['type']
            project_id = d['name'].split('/')[1]
            self.switch_project(project_id)
            results = list(self.inspect(metric_type, window_seconds))
            if not results:
                LOGGER.info(
                    f'{metric_type}: not written for (at least) {window} days')
                delete_list.append({
                    'metric_type': metric_type,
                    'project_id': self.project_id
                })
            else:
                last_written = results[0]['points'][0]['interval']['endTime']
                keep_list.append({
                    'metric_type':
                    metric_type,
                    'message':
                    f'Last datapoint written on {last_written}'
                })
                LOGGER.info(
                    f'{metric_type}: last datapoint written at {last_written}')
        if not delete_list:
            LOGGER.info(f'No unused metrics. Exiting.')
            return None
        if interactive:
            ix = input(f'Delete unused metrics (y/n) ?')
            if ix.lower() in ['y', 'yes']:
                for item in delete_list.items():
                    metric_type = item['metric_type']
                    self.switch_project(item['project_id'])
                    self.delete(metric_type)
            LOGGER.info(f'Metrics deleted successfully.')

    def inspect(self, metric_type, window):
        """Inspect a specific metric. Returns timeseries beteween now and
        300 seconds before.

        Args:
            metric_type (str): Metric type.
            window: Window (in seconds).

        Returns:
            list: List of timeseries.
        """
        LOGGER.debug(
            f'Inspecting metric "{metric_type}" in project "{self.project_id}" ...'
        )
        metric = list(self.get(metric_type))[0]
        metric_type = metric['type']
        interval = types.TimeInterval()
        now = time.time()
        interval.end_time.seconds = int(now)
        interval.end_time.nanos = int(
            (now - interval.end_time.seconds) * 10**9)
        interval.start_time.seconds = int(now - window)
        interval.start_time.nanos = interval.end_time.nanos
        results = list(
            self.client.list_time_series(
                self.project, 'metric.type = "%s"' % metric_type, interval,
                enums.ListTimeSeriesRequest.TimeSeriesView.FULL))
        return results

    def switch_project(self, new_project_id):
        self._project_id = self.project_id
        self.project_id = new_project_id
        self.project = self.client.project_path(self.project_id)
