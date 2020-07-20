"""
`cloudwatch.py`
AWS Cloudwatch backend implementation.
"""

import boto3
import logging
import random

from datetime import datetime

LOGGER = logging.getLogger(__name__)


class CloudwatchBackend:
    """Backend for querying metrics from ElasticSearch.

    Args:
        client (elasticsearch.ElasticSearch): Existing ES client.
        es_config (dict): ES client configuration.
    """
    def __init__(self, client=None):
        self.client = client
        if self.client is None:
            self.client = boto3.client('cloudwatch')

    def good_bad_ratio(self, timestamp, window, slo_config):
        """Query two timeseries, one containing 'good' events, one containing
        'bad' events.

        Args:
            timestamp (int): UNIX timestamp.
            window (int): Window size (in seconds).
            slo_config (dict): SLO configuration.

        Returns:
            tuple: A tuple (good_event_count, bad_event_count)
        """
        measurement = slo_config['backend']['measurement']
        query_good = measurement['query_good']
        query_bad = measurement.get('query_bad')
        query_valid = measurement.get('query_valid')
        json_good = CloudwatchBackend.get_query_body(id='good',
                                                     metric=query_good,
                                                     stat='Sum',
                                                     window=window)
        if query_bad:
            json_bad = CloudwatchBackend.get_query_body(id='bad',
                                                        metric=query_bad,
                                                        stat='Sum',
                                                        window=window)
            json_ratio = {
                "Id": "sli_value",
                "Expression": "good / (good + bad)",
                "Label": "SLI"
            }
            query = [json_ratio, json_good, json_bad]
        elif query_valid:
            json_valid = CloudwatchBackend.get_query_body(id='valid',
                                                          metric=query_valid,
                                                          stat='Sum',
                                                          window=window)
            json_ratio = {
                "Id": "sli_value",
                "Expression": "good / valid",
                "Label": "SLI"
            }
            query = [json_ratio, json_good, json_valid]
        else:
            raise Exception("Oneof `query_bad` or `query_valid` is required.")
        start_dt = datetime.fromtimestamp(timestamp - window)
        end_dt = datetime.fromtimestamp(timestamp)
        response = self.client.get_metric_data(MetricDataQueries=query,
                                               StartTime=start_dt,
                                               EndTime=end_dt,
                                               MaxDatapoints=1000)
        return response

    @staticmethod
    def get_query_body(id, metric, stat, window):
        """Get query body for AWS Cloudwatch get_metric_data API.

        Args:
            id (str): Virtual id of the metric (for reference in response).
            metric (dict): Metric descriptor.
            stat (str): Statistic to aggregate on.
            window (int): Window size (in seconds).

        Returns:
            dict: Query body.
        """
        return {
            'Id': id,
            'MetricStat': {
                'Metric': {
                    'Namespace': metric['namespace'],
                    'MetricName': metric['name'],
                    'Dimensions': metric['dimensions']
                },
                'Period': window,
                'Stat': stat,
                'Unit': 'Count'
            },
            'ReturnData': False
        }
