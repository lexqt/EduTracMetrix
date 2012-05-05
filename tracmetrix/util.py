# -*- coding: utf-8 -*-
#
# Stractistics
# Copyright (C) 2008 GMV SGI Team <http://www.gmv-sgi.es>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of version 2 of the GNU General Public
# License as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA
#
# EduTracMetrix
# Copyright (C) 2012 Aleksey A. Porfirov

import datetime

from trac.util.datefmt import format_date, utc

from tracmetrix.api import _
import OpenFlashChart



def _increment(storage, idx, event_data):
    storage[idx] += 1
def _initial_null(event):
    return 0

def aggregate_events_by_periods(events, events_data, start_date, groupsize, groupcnt,
                             func=_increment, initial_aggr=_initial_null):
    """
    Returns (list, dict)
    1. list of time groups labels for time range from `start_date`
    and `groupcnt` * `groupsize` days ahead.
    2. dict { <event>: [ <event aggregation>, ... ], ... }. Length of each list is `groupcnt`.

    `events`: list of events
    `events_data`: list of tuples (<event>, <event datetime>[, <extra data>, ...])

    Event is event type/label for `events_data` grouping. E.g., you can use authors
    as events if data is grouped by authors.
    Event aggregation is result of `func` manipulation with storage (see
    `_increment` as an example.

    """
    groups_labels, groups_map = get_date_groups_map(start_date, groupsize, groupcnt)
    groups_data = {}
    for e in events:
        groups_data[e] = [initial_aggr(e) for i in xrange(groupcnt)]
    for ed in events_data:
        event = ed[0]
        idx = groups_map[ed[1].date()]
        func(groups_data[event], idx, ed)

    return (groups_labels, groups_data)


def get_date_groups_map(start_date, groupsize, groupcnt):
    '''
    Returns a list of <string time period representation> and
    a dict { <date>: <index in the first list>, ... }
    for all dates from `start_date` and during next `groupcnt` periods
    `groupsize` days long.
    '''
    DAY = datetime.timedelta(days=1)
    GROUP_DIFF = datetime.timedelta(days=groupsize-1)
    nextd = datetime.date(start_date.year, start_date.month, start_date.day)
    groups_map = {}
    labels = []
    for i in xrange(groupcnt):
        if GROUP_DIFF:
            strgrp = '%s - %s' % (format_date(nextd, tzinfo=utc),
                                   format_date(nextd+GROUP_DIFF, tzinfo=utc))
        else:
            strgrp = format_date(nextd, tzinfo=utc)
        labels.append(strgrp)
        for d in xrange(groupsize):
            groups_map[nextd] = i
            nextd = nextd + DAY
    return labels, groups_map

def translate_keys(groups_data):
    new_data = {}
    for key, data in groups_data.iteritems():
        new_data[_(key)] = data
    return new_data

def adapt_to_table(weeks_list, authors_data, name_cap=None):
    """
    This function rearranges our data in order to be displayed easier
    in the html table.
    """

    #First, we reverse the order of the weeks.
    reversed_weeks_list = list(weeks_list)
    reversed_weeks_list.reverse()

    """Now, we must reverse the order of the results to match the new
    order of weeks."""
    results = {}
    for author in authors_data.iterkeys():
        results[author] = list(authors_data[author])
        results[author].reverse()

    """
    Every row in rows is a 2-tuple, the first element of the tuple is the
    week and the second element of the tuple is an array of the wiki
    modifications per author for that week.
    """
    authors = results.keys()
    rows = []
    index = 0
    for week in reversed_weeks_list:
        week_N_values = []
        for author in authors:
            week_N_values.append(results[author][index])
        index += 1
        rows.append((week, week_N_values))

    #Name mangling goes here
    def mangle_name(name, characters_cap):
        if characters_cap is not None and characters_cap > 0:
            name = name[0:characters_cap]
        return name

    columns = [mangle_name(name, name_cap) for name in authors]
    return (columns, rows)

def restructure_data(authors_data):
    """
    We need this function to avoid employing names with dots as HDF nodes.
    """
    new_data = []
    for author in authors_data:
        new_data.append({
            'author': author,
            'info': authors_data[author]
        })
    return new_data


class QueryResponse:
    """
    Encapsulates the information retrieved by a query and additional data for
    correct display.
    """
    def __init__(self,name, path='/chrome'):
        self.title = None
        self.name = name
        self.columns = []
        self.results = []
        self.path = "".join([path, '/tracmetrix/swf/'])
        self.chart_info = ChartInfo(name, self.path)

    def set_name(self,name):
        self.name = name
        self.chart_info.name = "%s_chart" % self.name

    def set_title(self, title):
        self.title = title
        self.chart_info.title = title

    def set_columns(self, columns):
        self.columns = columns

    def set_results(self, results):
        self.results = results
        size = len( results )
        self.chart_info.data_size = size

    def get_data(self):
        return {
                'title':self.title,
                'columns':self.columns,
                'results':self.results,
                'chart_info': self.chart_info.get_data()
                }


class ChartInfo:
    """
    This data is meant to be fed to SWF objects.
    It lets us control chart presentation.
    """
    def __init__(self,name='',path=''):
        #Default values
        self.width = 540
        self.height = 360
        self.x_font_size = 10
        self.x_font_color = "#000000"
        self.y_max = 0
        self.y_steps = 8
        self.data_size = 0
        self.x_orientation = 2
        self.x_steps = 1
        self.bg_color = '#FFFFFF'
        self.x_axis_color = '#000000'
        self.y_axis_color = '#000000'
        self.x_grid_color = '#F2F2EA'
        self.y_grid_color = '#F2F2EA'
        self.tool_tip = '#key#<br>#x_label#<br>#val#'
        self.type = "Bar"
        self.x_labels = None
        self.data = None
        self.colors = ["#f79910","#cbcc99","#6498c1","#cb1009","#64b832",
                       "#FF69B4","#000000","#8470FF"]
        self.title = ''
        self.name = "%s_chart" % name
        self.path = path

    def embed(self):
        chartObject = OpenFlashChart.graph_object()
        return chartObject.render(self.width, self.height,'',
                                  self.path, ofc_id = self.name)

    def get_data(self):
        members_dic = {}
        for member in dir(self):
            if not callable(getattr(self,member)) and member[0] != "_":
                members_dic[member] = getattr(self, member)
        return members_dic
