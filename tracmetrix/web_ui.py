# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2008 Bhuricha Sethanadha <khundeen@gmail.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac-hacks.org/wiki/TracMetrixPlugin.
#
# Author: Bhuricha Sethanandha <khundeen@gmail.com>
#
# Copyright (C) 2012 Aleksey A. Porfirov

from datetime import timedelta, datetime

from genshi.builder import tag
from genshi.filters.transform import StreamBuffer, Transformer

from trac.core import Component, implements
from trac.config import ExtensionOption, Option

from trac.util.datefmt import to_datetime, utc, format_date, parse_date_only
from trac.web import IRequestHandler, ITemplateStreamFilter
from trac.web.chrome import add_stylesheet, INavigationContributor, ITemplateProvider

from trac.ticket import Milestone
from trac.ticket.roadmap import ITicketGroupStatsProvider, get_ticket_stats, get_tickets_for_milestone, milestone_stats_data

from tracmetrix.api import TracMetrix, _
from tracmetrix.model import ChangesetsStats, TicketGroupMetrics, ProgressTicketGroupStatsProvider



def get_project_tickets(env, project_id):
    """
        This method collect interesting data of each ticket in the project.

        lead_time is the time from when ticket is created until it is closed.
        closed_time is the time from wheh ticket is closed untill it is reopened.

    """

    db = env.get_read_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM ticket WHERE project_id=%s ORDER BY id",
                   (project_id,))

    tkt_ids = [id for id , in cursor]

    return tkt_ids

def last_day_of_month(year, month):

    # For december the next month will be january of next year.
    if month == 12:
        year = year + 1

    return datetime(year+(month/12), (month%12)+1 , 1, tzinfo=utc) - timedelta(days=1)

class GenerateMetrixLink(object):
    """
    Takes a C{StreamBuffer} object containing a milestone name and creates a
    hyperlink to the TracMetrixPlugin dashboard page for that milestone.
    See: http://groups.google.com/group/genshi/msg/3193e468b6b52395
    """

    def __init__(self, buffer, baseHref):
        """
        @param buffer: An C{StreamBuffer} instance containing the name of a milestone
        @param baseHref: An C{trac.web.href.Href} instance that is aware of
        TracMetrixPlugin navigation plugins.
        """
        self.buffer = buffer
        self.baseHref = baseHref

    def __iter__(self):

        """
        Return a <dd><a> link to be inserted at the end of the stats block of
        the milstone summary.
        """
        milestoneName = u"".join(e[1] for e in self.buffer.events)
        title = "Go to TracMetrix for %s" % milestoneName
        href = self.baseHref.mdashboard(milestoneName)

        return iter(tag.dd('[', tag.a('TracMetrix', href=href, title=title), ']'))



class RoadmapMetrixIntegrator(Component):
    """
    Add a link from each milestone in the roadmap, to the corresponding
    metrix dashboard page.
    """
    implements(ITemplateStreamFilter)

    # ITemplateStreamFilter methods
    def filter_stream(self, req, method, filename, stream, data):

        if filename in ('roadmap.html', ):

            buffer = StreamBuffer()
            t = Transformer('//li[@class="milestone"]/div[@class="info"]/h2/a/em/text()')
            t = t.copy(buffer).end()
            t = t.select('//li[@class="milestone"]/div[@class="info"]/dl')
            t = t.append(GenerateMetrixLink(buffer, req.href))
            stream |= t

        return stream

class MilestoneMetrixIntegrator(Component):
    """Add a link from the milestone view, to the corresponding metrix
    dashboard page.
    """
    implements(ITemplateStreamFilter)

    # ITemplateStreamFilter methods
    def filter_stream(self, req, method, filename, stream, data):

        if filename in ('milestone_view.html', ):

            buffer = StreamBuffer()
            t = Transformer('//div[@class="milestone"]/h1/text()[2]')
            t = t.copy(buffer).end()
            t = t.select('//div[@class="milestone"]/div[@class="info"]/dl')
            t = t.append(GenerateMetrixLink(buffer, req.href))
            stream |= t

        return stream

class PDashboard(Component):

    implements(INavigationContributor, IRequestHandler, ITemplateProvider)

    DAYS_BACK = 28

    def __init__(self):
        self.tm = TracMetrix(self.env)
        self.stats_provider = ProgressTicketGroupStatsProvider(self.env)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'pdashboard'

    def get_navigation_items(self, req):
        if 'ROADMAP_VIEW' in req.perm:
            yield ('mainnav', 'pdashboard',
                   tag.a(_('Metrics'), href=req.href.pdashboard()))

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info.startswith('/pdashboard')

    def process_request(self, req):
        req.perm.require('ROADMAP_VIEW')

        pid = req.project

        return self._render_view(req)

    def _render_view(self, req):

        showall = req.args.get('show') == 'all'
        showmetrics = req.args.get('showmetrics') == 'true'
        project_id = req.data['project_id']

        fromdate = today = datetime.now(utc)
        if 'from' in req.args:
            reqfromdate = req.args['from'].strip()
            if reqfromdate:
                fromdate = parse_date_only(reqfromdate)
                fromdate = to_datetime(fromdate, utc)
        fromdate = fromdate.replace(hour=0, minute=0, second=0,
                                    microsecond=0)

        daysback = req.args.getint('daysback')
        if daysback is None or daysback < 0 or daysback > 120:
            daysback = self.DAYS_BACK

        last_day = fromdate.replace(hour=23, minute=59, second=59,
                                    microsecond=999999)
        first_day = fromdate - timedelta(days=daysback)

        db = self.env.get_read_db()

        # Get list of milestone object for the project
        milestones = list(Milestone.select(self.env, project_id, showall, db))
        stats = []

        for milestone in milestones:
            tickets = get_tickets_for_milestone(self.env, db, milestone,
                                                'owner')
            stat = get_ticket_stats(self.stats_provider, tickets, project_id)
            stats.append(milestone_stats_data(self.env, req, stat, milestone))

        data = {
            'milestones': milestones,
            'milestone_stats': stats,
            'showall': showall,
            'showmetrics': showmetrics,
            'yui_base_url': self.tm.yui_base_url,
            'fromdate': fromdate,
            'daysback': daysback,
            '_': _,
        }

        project_tickets = get_project_tickets(self.env, project_id)

        # Get project progress stats
        proj_stat = self.stats_provider.get_ticket_group_stats(project_tickets, project_id)

        data['proj_progress_stat'] = {'stats': proj_stat,
                                      'stats_href': req.href.query(proj_stat.qry_args, project_id=project_id),
                                      'interval_hrefs': [req.href.query(interval['qry_args'])
                                                         for interval in proj_stat.intervals]}

        closed_stat = self.stats_provider.get_ticket_resolution_group_stats(project_tickets, project_id)

        data['proj_closed_stat'] = {'stats': closed_stat,
                                    'stats_href': req.href.query(closed_stat.qry_args, project_id=project_id),
                                    'interval_hrefs': [req.href.query(interval['qry_args'])
                                                       for interval in closed_stat.intervals]}

        tkt_frequency_stats = {}
        tkt_duration_stats = {}
        bmi_stats = []
        daily_backlog_chart = {}

        if showmetrics:
            tkt_group_metrics = TicketGroupMetrics(self.env, project_tickets)

            tkt_frequency_stats = tkt_group_metrics.get_frequency_metrics_stats()
            tkt_duration_stats = tkt_group_metrics.get_duration_metrics_stats()

            weeks = daysback // 7
            if daysback % 7:
                weeks += 1
            offset = (last_day.isoweekday() - 1) + (7 * (weeks-1))
            fday = last_day - timedelta(offset)
            for _i in xrange(weeks):
                lday = fday + timedelta(7, microseconds=-1)
                bstats = tkt_group_metrics.get_bmi_stats(fday, lday)
                bmi_stats.append(('%s - %s' % (format_date(fday), format_date(lday)),) + bstats)
                fday += timedelta(7)

            # get daily backlog history
            backlog_history = tkt_group_metrics.get_daily_backlog_history(first_day, last_day)
            daily_backlog_chart = tkt_group_metrics.get_daily_backlog_chart(backlog_history)

        # Get daily commits history
        changeset_group_stats = ChangesetsStats(self.env, project_id, first_day, last_day)
        commits_by_date = changeset_group_stats.get_commit_by_date()
        commits_by_date_chart = changeset_group_stats.get_commit_by_date_chart(commits_by_date)

        data.update({
            'project_bmi_stats': bmi_stats,
            'ticket_frequency_stats': tkt_frequency_stats,
            'ticket_duration_stats': tkt_duration_stats,
            'ds_daily_backlog': daily_backlog_chart,
            'ds_commit_by_date': commits_by_date_chart,
        })

        add_stylesheet(req, 'tracmetrix/css/dashboard.css')
        add_stylesheet(req, 'common/css/report.css')

        return ('pdashboard.html', data, None)

    # ITemplateProvider methods
    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

    def get_htdocs_dirs(self):
        from pkg_resources import resource_filename
        return [('tracmetrix', resource_filename(__name__, 'htdocs'))]
