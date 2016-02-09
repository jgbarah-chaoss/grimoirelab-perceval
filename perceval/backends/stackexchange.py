# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors:
#   Alberto Martín <alberto.martin@bitergia.com>
#

import json
import logging
import os.path

import requests
import time

from ..backend import Backend, BackendCommand, metadata
from ..cache import Cache
from ..errors import CacheError
from ..utils import str_to_datetime, DEFAULT_DATETIME, urljoin

# Filters are immutable and non-expiring. This filter allows to retrieve all
# the information regarding Each question. To know more, visit
# https://api.stackexchange.com/docs/questions and paste the filter in the
# whitebox filter. It will display a list of checkboxes with the selected
# values for the filter provided.

QUESTIONS_FILTER = 'Bf*y*ByQD_upZqozgU6lXL_62USGOoV3)MFNgiHqHpmO_Y-jHR'
MAX_QUESTIONS = 100  # Maximum number of reviews per query
STACKEXCHANGE_API_URL = 'https://api.stackexchange.com'
VERSION_API = '2.2'

logger = logging.getLogger(__name__)


def get_update_time(item):
    """Extracts the update time from a StackExchange item"""
    return item['last_activity_date']


class StackExchange(Backend):
    """StackExchange backend for Perceval.

    This class retrieves the questions stored in any of the
    StackExchange sites. To initialize this class the
    site and the tag must be provided.

    :param site: StackExchange site
    :param tagged: filter items by question Tag
    :param token: StackExchange access_token for the API
    :param cache: cache object to store raw data
    """
    version = '0.1.0'

    def __init__(self, site=None, tagged=None, token=None,
                 max_questions=None, cache=None):

        super().__init__(site, cache=cache)
        self.site = site
        self.tagged = tagged
        self.max_questions = max_questions
        self.client = StackExchangeClient(site, tagged, token, max_questions)

    @metadata(get_update_time)
    def fetch(self, from_date=DEFAULT_DATETIME):
        """Fetch the questions from the site.

        The method retrieves, from a StackExchange site, the
        questions updated since the given date.

        :param from_date: obtain questions updated since this date

        :returns: a generator of questions
        """
        if not from_date:
            from_date = DEFAULT_DATETIME

        logger.info("Looking for questions at site '%s', with tag '%s' and updated from '%s'",
                    self.site, self.tagged, str(from_date))

        self._purge_cache_queue()

        whole_page = self.client.get_questions(from_date)

        for questions in whole_page:
            for question in questions:
                self._push_cache_queue(question)
                self._flush_cache_queue()
                yield question

    @metadata(get_update_time)
    def fetch_from_cache(self):
        """Fetch the questions from the cache.

        :returns: a generator of questions

        :raises CacheError: raised when an error occurs accessing the
            cache
        """
        if not self.cache:
            raise CacheError(cause="cache instance was not provided")

        cache_items = self.cache.retrieve()

        for question in cache_items:
            yield question


class StackExchangeClient:
    """StackExchange API client.

    This class implements a simple client to retrieve questions from
    any Stackexchange site.

    :param site: URL of the Bugzilla server
    :param tagged: filter items by question Tag
    :param token: StackExchange access_token for the API
    :param max_questions: max number of questions per query

    :raises HTTPError: when an error occurs doing the request
    """

    def __init__(self, site, tagged, token, max_questions):
        self.site = site
        self.tagged = tagged
        self.token = token
        self.max_questions = max_questions
        self.version = VERSION_API

    def __build_base_url(self, type='questions'):
        base_api_url = STACKEXCHANGE_API_URL
        base_api_url = urljoin(base_api_url, self.version, type)
        return base_api_url

    def __build_payload(self, page, from_date, order='desc', sort='activity'):
        payload = {'page': page,
                   'pagesize': self.max_questions,
                   'order': order,
                   'sort': sort,
                   'tagged': self.tagged,
                   'site': self.site,
                   'key': self.token,
                   'filter': QUESTIONS_FILTER}
        if from_date:
            timestamp = int(time.mktime(from_date.timetuple()))
            payload['min'] = timestamp
        return payload

    def __log_status(self, quota_remaining, quota_max, page_size, total):

        logger.info("Rate limit: %s/%s" % (quota_remaining,
                                           quota_max))
        if (total != 0):
            if (total <= page_size):
                logger.info("Fetching questions: %s/%s" % (total,
                                                           total))
            else:
                logger.info("Fetching questions: %s/%s" % (page_size,
                                                           total))
        else:
            logger.info("No questions were found.")

    def get_questions(self, from_date):
        """Retrieve all the questions from a given date.

        :param from_date: obtain questions updated since this date
        """

        page = 1
        req = requests.get(self.__build_base_url(),
                           params=self.__build_payload(page, from_date))
        req.raise_for_status()
        questions = req.json()['items']

        if (req.json()['page_size'] >= req.json()['total']):
            fetched = req.json()['total']
        else:
            fetched = req.json()['page_size']

        self.__log_status(req.json()['quota_remaining'],
                          req.json()['quota_max'],
                          fetched,
                          req.json()['total'])

        while questions:
            yield questions
            questions = None

            if req.json()['has_more']:
                page += 1
                req = requests.get(self.__build_base_url(),
                                   params=self.__build_payload(page, from_date))
                req.raise_for_status()
                questions = req.json()['items']
                if (req.json()['page_size'] >= req.json()['total']):
                    fetched += req.json()['total']
                else:
                    fetched += req.json()['page_size']
                self.__log_status(req.json()['quota_remaining'],
                                  req.json()['quota_max'],
                                  fetched,
                                  req.json()['total'])


class StackExchangeCommand(BackendCommand):
    """Class to run StackExchange backend from the command line."""

    def __init__(self, *args):
        super().__init__(*args)
        self.site = self.parsed_args.site
        self.tagged = self.parsed_args.tagged
        self.token = self.parsed_args.token
        self.max_questions = self.parsed_args.max_questions
        self.from_date = str_to_datetime(self.parsed_args.from_date)
        self.outfile = self.parsed_args.outfile

        if not self.parsed_args.no_cache:
            if not self.parsed_args.cache_path:
                base_path = os.path.expanduser('~/.perceval/cache/')
            else:
                base_path = self.parsed_args.cache_path

            cache_path = os.path.join(base_path, self.site)

            cache = Cache(cache_path)

            if self.parsed_args.clean_cache:
                cache.clean()
            else:
                cache.backup()
        else:
            cache = None

        self.backend = StackExchange(
            self.site, self.tagged, self.token, self.max_questions, cache=cache)

    def run(self):
        """Fetch and print the Questions.

        This method runs the backend to fetch the Questions (plus all
        its answers and comments) of a given site and tag.
        Questions are converted to JSON objects and printed to the
        defined output.
        """
        if self.parsed_args.fetch_cache:
            questions = self.backend.fetch_from_cache()
        else:
            questions = self.backend.fetch(from_date=self.from_date)

        try:
            for question in questions:
                obj = json.dumps(question, indent=4, sort_keys=True)
                self.outfile.write(obj)
                self.outfile.write('\n')
        except requests.exceptions.HTTPError as e:
            raise requests.exceptions.HTTPError(str(e.response.json()))
        except IOError as e:
            raise RuntimeError(str(e))
        except Exception as e:
            if self.backend.cache:
                self.backend.cache.recover()
            raise RuntimeError(str(e))

    @classmethod
    def create_argument_parser(cls):
        """Returns the StackExchange argument parser."""

        parser = super().create_argument_parser()

        # StackExchange options
        group = parser.add_argument_group('StackExchange arguments')

        group.add_argument("--site", required=True,
                           help="StackExchange site")
        group.add_argument("--tagged", required=True,
                           help="filter items by question Tag")
        group.add_argument("--token", required=True,
                           help="StackExchange token for the API")
        group.add_argument('--max-questions', dest='max_questions',
                           type=int, default=MAX_QUESTIONS,
                           help="Maximum number of questions requested in the same query")

        return parser
