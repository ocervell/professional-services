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
`utils.py`
Util functions.
"""

import functools
from typing import Set

from google.protobuf.json_format import MessageToDict

def decorate_with(decorator, methods: Set[str]):
    """Class decorator that decorates wanted class methods.

    Args:
        decorator (method): Decorator method.
        methods (set): Set of class method names to decorate.

    Returns:
        cls: Decorated class.
    """
    def inner(cls):
        if not methods:
            return cls
        for attr in cls.__dict__:  # there's propably a better way to do this
            attribute = getattr(cls, attr)
            if callable(attribute) and attribute.__name__ in methods:
                setattr(cls, attr, decorator(attribute))
        return cls

    return inner


def to_json(func):
    """Format API responses as JSON, using protobuf.

    Args:
        func (method): Function to decorate.

    Returns:
        method: Decorated method.
    """
    @functools.wraps(func)
    def inner(*args, **kwargs):
        fields = kwargs.pop('fields', None)
        response = func(*args, **kwargs)
        if isinstance(response, list):
            for resp in response:
                yield filter_fields(MessageToDict(resp), fields=fields)
        elif response is None:
            yield None
        else:
            yield filter_fields(MessageToDict(response), fields=fields)

    return inner


def filter_fields(response, fields: Set[str]):
    """Filter response fields.

    Args:
        response (dict): Response as a dictionary.
        fields (set): Set of fields to filter on.

    Returns:
        dict: Filtered response.
    """
    if fields is None:
        return response
    return {k: response[k] for k in response.keys() & fields}



def plot_timeseries(time_series, title=None):
    """Plot a Cloud Monitoring timeserie using Matplotlib.

    Args:
        time_series (list): List of TimeSeries objects.
        title (str, optional): Plot title. Defaults to the metric type.
    """
    import matplotlib.pyplot as plt
    df = _build_dataframe(time_series)
    fig = plt.figure()
    if title is None:
        title = time_series[0].metric.type
    fig.suptitle(title)
    plt.plot(df)
    plt.show()

def _build_dataframe(time_series_iterable,
                     label=None, labels=None):  # pragma: NO COVER
    """Build a Pandas dataframe out of time series.

    Args:
        time_series_iterable: An iterable (e.g., a query object) yielding
            time series.
        label: The label name to use for the dataframe header.
            This can be the name of a resource label or metric label
            (e.g., ``"instance_name"``), or the string ``"resource_type"``.
        labels (list|tuple): A list or tuple of label names to use for the
            dataframe header. If more than one label name is provided, the
            resulting dataframe will have a multi-level column header.
            Specifying neither ``label`` or ``labels`` results in a dataframe
            with a multi-level column header including the resource type and
            all available resource and metric labels.
            Specifying both ``label`` and ``labels`` is an error.

    Returns:
        `pandas.DataFrame`: A dataframe where each column represents one
            time series.
    """
    import pandas   # pylint: disable=import-error
    import itertools   # pylint: disable=import-error
    import collections   # pylint: disable=import-error
    if labels is not None:
        if label is not None:
            raise ValueError('Cannot specify both "label" and "labels".')
        elif not labels:
            raise ValueError('"labels" must be non-empty or None.')
    columns = []
    headers = []
    for time_series in time_series_iterable:
        print(time_series)
        point_values = [point.value.double_value for point in time_series.points]
        point_index = [point.interval.end_time.seconds + point.interval.end_time.nanos * 10**(-9) for point in time_series.points]
        pandas_series = pandas.Series(
            data=point_values,
            index=point_index,
        )
        columns.append(pandas_series)
        labels = {}
        labels.update(time_series.metric.labels)
        labels.update(time_series.resource.labels)
        tup = collections.namedtuple('TimeSeries', 'labels points')
        test = tup(labels=labels, points=[])
        headers.append(test)

    # Implement a smart default of using all available labels.
    if label is None and labels is None:
        resource_labels = time_series.resource.labels
        metric_labels = time_series.metric.labels
        labels = (['resource_type'] +
                  _sorted_resource_labels(resource_labels) +
                  sorted(metric_labels))

    # Assemble the columns into a DataFrame.
    # print(columns[0])
    dataframe = pandas.DataFrame.from_records(columns).T

    # Convert the timestamp strings into a DatetimeIndex.
    dataframe.index = pandas.to_datetime(dataframe.index, unit='s')

    # Build a multi-level stack of column headers. Some labels may
    # be undefined for some time series.
    levels = []
    for key in labels or [label]:
        level = [header.labels.get(key, '') for header in headers]
        levels.append(level)

    # Build a column Index or MultiIndex. Do not include level names
    # in the column header if the user requested a single-level header
    # by specifying "label".
    dataframe.columns = pandas.MultiIndex.from_arrays(
        levels,
        names=labels or None)

    # Sort the rows just in case (since the API doesn't guarantee the
    # ordering), and sort the columns lexicographically.
    return dataframe.sort_index(axis=0).sort_index(axis=1)

def _sorted_resource_labels(labels):
    """Sort label names, putting well-known resource labels first."""
    TOP_RESOURCE_LABELS = (
        'project_id',
        'aws_account',
        'location',
        'region',
        'zone',
    )
    head = [label for label in TOP_RESOURCE_LABELS if label in labels]
    tail = sorted(label for label in labels
                  if label not in TOP_RESOURCE_LABELS)
    return head + tail
