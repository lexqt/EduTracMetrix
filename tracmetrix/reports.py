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

from trac.util.datefmt import to_utimestamp, from_utimestamp, format_date

from tracmetrix.util import QueryResponse, adapt_to_table, restructure_data, \
                            aggregate_events_by_periods, translate_keys
from tracmetrix.api import _, N_






def repository_activity(project_id, start_date, end_date, groupsize, groupcnt, db, req,
                         authors_limit=None, ignored_authors=None):
    """
    Get query response for specified time interval, for max `authors_limit` most
    active users, excluding `ignored_authors`:
    Data: <author>: <count commits>
    """
    authors_limit   = authors_limit or 10
    ignored_authors = ignored_authors or ()

    authors = _most_active_repository_authors( project_id,
                                               authors_limit, ignored_authors,
                                               start_date, end_date,
                                               db)
    revisions = _retrieve_revisions(project_id, authors, start_date, end_date, db)
    groups_list, authors_data = aggregate_events_by_periods(authors, revisions,
                                              start_date, groupsize, groupcnt)

    query_response = QueryResponse("repository_activity", req.href('/chrome'))
    query_response.set_title(_("Commits from %(start_date)s to %(end_date)s",
                               start_date=format_date(start_date, tzinfo=req.tz),
                               end_date=format_date(end_date, tzinfo=req.tz)))

    columns, rows = adapt_to_table(groups_list, authors_data)
    query_response.set_columns(columns)
    query_response.set_results(rows)

    chart = query_response.chart_info
    chart.type = 'Line'
    chart.x_legend = _('Time periods')
    chart.y_legend = _('Commits')
    chart.x_labels = groups_list
    chart.data = restructure_data(authors_data)
    chart.tool_tip = "#key#<br>%s:#x_label#<br>%s:#val#" % (_('period'), _('commits'))

    return query_response

def _most_active_repository_authors(project_id, authors_limit, ignored_authors, start_date,
                                    end_date, db):
    sql_expr = """
        SELECT r.author AS author, COUNT( r.author ) AS commits
        FROM revision r
        WHERE r.repos IN (
            SELECT id FROM repository
            WHERE name='project_id' AND value=%s
        ) AND r.time > %s AND r.time < %s {extra}
        GROUP BY author
        LIMIT {limit:d}
    """
    args = [str(project_id), to_utimestamp(start_date), to_utimestamp(end_date)]
    if ignored_authors:
        extra = 'AND r.author NOT IN %s'
        args.append(tuple(ignored_authors))
    else:
        extra = ''

    cursor = db.cursor()
    cursor.execute(sql_expr.format(extra=extra, limit=authors_limit),
                   args)
    authors = [r[0] for r in cursor]
    return authors


def _retrieve_revisions(project_id, authors, start_date, end_date, db):
    sql_expr = """
        SELECT r.author, r.time
        FROM revision r
        WHERE r.repos IN (
            SELECT id FROM repository
            WHERE name='project_id' AND value=%s
        ) AND r.time >= %s AND r.time < %s {extra}
    """

    args = [str(project_id), to_utimestamp(start_date), to_utimestamp(end_date)]
    if authors:
        extra = 'AND r.author IN %s'
        args.append(tuple(authors))
    else:
        extra = ''

    cursor = db.cursor()
    cursor.execute(sql_expr.format(extra=extra), args)
    revisions = [(r[0], from_utimestamp(r[1])) for r in cursor]
    return revisions



def ticket_activity(project_id, start_date, end_date, db, req):
    """
    Get query response for specified time interval:
    Data: <ticket status>: <count tickets>
    """
    sql_expr = """
    SELECT t.status, COUNT(t.id)
    FROM ticket t
    WHERE t.project_id=%s AND t.changetime >= %s AND t.changetime < %s
    GROUP BY t.status;
    """

    cursor = db.cursor()
    cursor.execute(sql_expr, (project_id,
                              to_utimestamp(start_date), to_utimestamp(end_date))
                   )
    results = [(r[0], r[1]) for r in cursor]

    query_response = QueryResponse("ticket_activity", req.href('/chrome'))
    query_response.set_title(_("Ticket activity"))
    query_response.set_columns((_('ticket status'), _('tickets')))
    query_response.set_results(results)
    chart = query_response.chart_info
    chart.type = "Pie"
    chart.width = 480
    chart.height = 300
    chart.tool_tip = "%s:#x_label#<br>%s:#val#" % (_('status'), _('tickets'))
    chart.line_color = "#000000"
    chart.x_labels = [row[0] for row in results]
    chart.data = [row[1] for row in results]

    return query_response

def wiki_activity(project_id, start_date, end_date, groupsize, groupcnt, db, req,
                   authors_limit=None, ignored_authors=None):
    """
    Get query response for specified time interval, for max `authors_limit` most
    active users, excluding `ignored_authors`:
    Data: <author>: <count wiki modifications>
    """
    authors_limit   = authors_limit or 10
    ignored_authors = ignored_authors or ()

    authors_list = _retrieve_most_active_wiki_authors(project_id, authors_limit, ignored_authors,
                                                      start_date, end_date, db)
    wiki_pages_list = _retrieve_wiki_pages(project_id, authors_list, start_date, end_date, db)

    groups_list, authors_data = aggregate_events_by_periods(authors_list, wiki_pages_list,
                                              start_date, groupsize, groupcnt)

    query_response = QueryResponse("wiki_activity", req.href('/chrome'))
    query_response.set_title(_("Wiki activity from %(start_date)s to %(end_date)s",
                               start_date=format_date(start_date, tzinfo=req.tz),
                               end_date=format_date(end_date, tzinfo=req.tz)))

    columns, rows = adapt_to_table(groups_list, authors_data)
    query_response.set_columns(columns)
    query_response.set_results(rows)

    chart = query_response.chart_info
    chart.type = 'Line'
    chart.x_legend = _('Time periods')
    chart.y_legend = _('Wiki modifications')
    chart.x_labels = groups_list
    chart.data = restructure_data(authors_data)
    chart.tool_tip = "#key#<br>%s:#x_label#<br>%s:#val#" % (_('period'), _('Wiki modifications'))

    return query_response


def _retrieve_most_active_wiki_authors(project_id, authors_limit, ignored_authors,
                                       start_date, end_date, db):
    sql_expr = """
        SELECT w.author AS author, COUNT(w.version) AS modifications
        FROM wiki w
        WHERE w.project_id=%s AND
              w.time >= %s AND w.time < %s {extra}
        GROUP BY author
        LIMIT {limit:d}
    """
    args = [project_id, to_utimestamp(start_date), to_utimestamp(end_date)]
    if ignored_authors:
        extra = 'AND w.author NOT IN %s'
        args.append(tuple(ignored_authors))
    else:
        extra = ''

    cursor = db.cursor()
    cursor.execute(sql_expr.format(extra=extra, limit=authors_limit),
                   args)
    authors = [r[0] for r in cursor]
    return authors

def _retrieve_wiki_pages(project_id, authors, start_date, end_date, db):
    sql_expr = """
        SELECT author, time
        FROM wiki
        WHERE project_id=%s AND
              time >= %s AND time < %s {extra}
    """
    args = [project_id, to_utimestamp(start_date), to_utimestamp(end_date)]
    if authors:
        extra = 'AND author IN %s'
        args.append(tuple(authors))
    else:
        extra = ''

    cursor = db.cursor()
    cursor.execute(sql_expr.format(extra=extra), args)
    results = [(r[0], from_utimestamp(r[1])) for r in cursor]
    return results

def ticket_activity_user(project_id, username, start_date, end_date, groupsize, groupcnt, db, req):
    """
    Get query response for specified time interval and `username`:
    Data: <event>: <count events>.
    Events: 'created', 'closed'.
    """
    q = '''
        SELECT t.id, t.time, 'created' AS event
        FROM ticket t
        WHERE t.reporter=%s AND t.project_id=%s AND
              t.time >= %s AND t.time < %s
        UNION
        SELECT t.id, tc.time, 'closed' AS event
        FROM ticket t LEFT JOIN ticket_change tc ON t.id = tc.ticket
            AND tc.field='status' AND tc.newvalue='closed'
        WHERE t.owner=%s AND t.project_id=%s AND
              tc.time >= %s AND tc.time < %s
        ORDER BY event
    '''
    cursor = db.cursor()
    cursor.execute(q, (username, project_id, to_utimestamp(start_date), to_utimestamp(end_date))*2)
    etypes = (N_('created'), N_('closed'))
    events = [(r[2], from_utimestamp(r[1]), r[0]) for r in cursor]

    # TODO: count closed once, use global closed set
    def init_set(e):
        return set()
    def add_to_set(stor, idx, event_data):
        stor[idx].add(event_data[2])

    groups_list, groups_data = aggregate_events_by_periods(etypes, events,
                                              start_date, groupsize, groupcnt,
                                              add_to_set, init_set)

    for etype, groups in groups_data.iteritems():
        for idx, ids in enumerate(groups):
            groups[idx] = len(ids)

    query_response = QueryResponse("ticket_activity", req.href('/chrome'))
    query_response.set_title(_("Ticket activity from %(start_date)s to %(end_date)s",
                               start_date=format_date(start_date, tzinfo=req.tz),
                               end_date=format_date(end_date, tzinfo=req.tz)))

    groups_data = translate_keys(groups_data)
    columns, rows = adapt_to_table(groups_list, groups_data)
    query_response.set_columns(columns)
    query_response.set_results(rows)

    chart = query_response.chart_info
    chart.type = 'Line'
    chart.width = 600
    chart.x_legend = _('Time periods')
    chart.y_legend = _('Tickets')
    chart.x_labels = groups_list
    chart.data = restructure_data(groups_data)
    chart.tool_tip = "#key#<br>%s:#x_label#<br>%s:#val#" % (_('period'), _('tickets'))

    return query_response

def wiki_activity_user(project_id, username, start_date, end_date, groupsize, groupcnt, db, req):
    """
    Get query response for specified time interval and `username`:
    Data: <event>: <count events>.
    Events: 'created', 'modified'.
    """
    q = '''
        SELECT time, version
        FROM wiki
        WHERE author=%s AND project_id=%s AND
              time >= %s AND time < %s
    '''
    cursor = db.cursor()
    cursor.execute(q, (username, project_id, to_utimestamp(start_date), to_utimestamp(end_date)))
    etypes = (N_('created'), N_('modified'))
    events = [(r[1]==1 and 'created' or 'modified', from_utimestamp(r[0])) for r in cursor]

    groups_list, groups_data = aggregate_events_by_periods(etypes, events,
                                              start_date, groupsize, groupcnt)

    query_response = QueryResponse("wiki_activity", req.href('/chrome'))
    query_response.set_title(_("Wiki activity from %(start_date)s to %(end_date)s",
                               start_date=format_date(start_date, tzinfo=req.tz),
                               end_date=format_date(end_date, tzinfo=req.tz)))

    groups_data = translate_keys(groups_data)
    columns, rows = adapt_to_table(groups_list, groups_data)
    query_response.set_columns(columns)
    query_response.set_results(rows)

    chart = query_response.chart_info
    chart.type = 'Line'
    chart.x_legend = _('Time periods')
#    chart.y_legend = _('Number')
    chart.x_labels = groups_list
    chart.data = restructure_data(groups_data)
    chart.tool_tip = "#key#<br>%s:#x_label#<br>%s:#val#" % (_('period'), _('number'))

    return query_response

def repository_activity_user(project_id, username, start_date, end_date, groupsize, groupcnt, db, req):
    """
    Get query response for specified time interval and `username`:
    Data: <event>: <count events>.
    Events: 'commit'.
    """
    q = '''
        SELECT r.time
        FROM revision r
        WHERE r.repos IN (
            SELECT id FROM repository
            WHERE name='project_id' AND value=%s
        ) AND r.author=%s AND r.time >= %s AND r.time < %s
    '''
    cursor = db.cursor()
    cursor.execute(q, (str(project_id), username, to_utimestamp(start_date), to_utimestamp(end_date)))
    etypes = (N_('commit'),)
    events = [('commit', from_utimestamp(r[0])) for r in cursor]

    groups_list, groups_data = aggregate_events_by_periods(etypes, events,
                                              start_date, groupsize, groupcnt)

    query_response = QueryResponse("repository_activity", req.href('/chrome'))
    query_response.set_title(_("Commits from %(start_date)s to %(end_date)s",
                               start_date=format_date(start_date, tzinfo=req.tz),
                               end_date=format_date(end_date, tzinfo=req.tz)))

    groups_data = translate_keys(groups_data)
    columns, rows = adapt_to_table(groups_list, groups_data)
    query_response.set_columns(columns)
    query_response.set_results(rows)

    chart = query_response.chart_info
    chart.type = 'Line'
    chart.x_legend = _('Time periods')
#    chart.y_legend = _('Number')
    chart.x_labels = groups_list
    chart.data = restructure_data(groups_data)
    chart.tool_tip = "#key#<br>%s:#x_label#<br>%s:#val#" % (_('period'), _('number'))

    return query_response
