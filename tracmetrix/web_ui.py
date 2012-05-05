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
# EduTracMetrix
# Copyright (C) 2012 Aleksey A. Porfirov

from datetime import timedelta, datetime
import simplejson

from genshi.builder import tag
from genshi.filters.transform import StreamBuffer, Transformer

from trac.core import Component, implements

from trac.util.datefmt import to_datetime, format_date, parse_date_only
from trac.web import IRequestHandler, ITemplateStreamFilter
from trac.web.chrome import add_stylesheet, add_script, INavigationContributor, ITemplateProvider

from trac.ticket import Milestone
from trac.ticket.roadmap import get_ticket_stats, get_tickets_for_milestone, milestone_stats_data

from trac.project.api import ProjectManagement

from tracmetrix.api import TracMetrix, _
from tracmetrix.model import ChangesetsStats, TicketGroupMetrics, ProgressTicketGroupStatsProvider

from tracmetrix import reports


__all__ = ['PDashboard', 'RoadmapMetrixIntegrator', 'MilestoneMetrixIntegrator']


def get_project_tickets(env, project_id):
    """
    Get all ticket ids for `project_id`
    """

    db = env.get_read_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM ticket WHERE project_id=%s ORDER BY id",
                   (project_id,))

    return [id for id , in cursor]


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



# TODO: check / modify
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

# TODO: check / modify
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
        if req.path_info.startswith('/pdashboard/user'):
            return 'udashboard'
        else:
            return 'pdashboard'

    def get_navigation_items(self, req):
        if 'ROADMAP_VIEW' in req.perm:
            yield ('mainnav', 'pdashboard',
                   tag.a(_('Project metrics'), href=req.href.pdashboard()))
            yield ('mainnav', 'udashboard',
                   tag.a(_('User metrics'), href=req.href.pdashboard('user')))

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info.startswith('/pdashboard')

    def process_request(self, req):
        req.perm.require('ROADMAP_VIEW')

        _pid = req.project

        fromdate = datetime.now(req.tz)
        if 'from' in req.args:
            reqfromdate = req.args['from'].strip()
            if reqfromdate:
                fromdate = parse_date_only(reqfromdate)
                fromdate = to_datetime(fromdate, req.tz)
        fromdate = fromdate.replace(hour=0, minute=0, second=0,
                                    microsecond=0)

        daysback = req.args.getint('daysback')
        if daysback is None or daysback < 0 or daysback > 120:
            daysback = self.DAYS_BACK

        last_day = fromdate.replace(hour=23, minute=59, second=59,
                                    microsecond=999999)
        first_day = fromdate - timedelta(days=daysback)

        groupsize = req.args.getint('groupsize')
        if groupsize is None or groupsize <= 0:
            groupsize = 7

#        weeks = daysback // 7 + 1
#        if daysback % 7:
#            weeks += 1
#        offset = (fromdate.isoweekday() - 1) + (7 * (weeks-1))
#        first_day_week = fromdate - timedelta(offset)
#        last_day_week  = first_day_week + timedelta(7*weeks, microseconds=-1)

        groupcnt = daysback // groupsize
        if daysback % groupsize:
            groupcnt += 1
        offset = groupsize * groupcnt
        first_day_group = fromdate - timedelta(offset - 1)

        data = {
            'yui_base_url': self.tm.yui_base_url,
            'fromdate': fromdate,
            'daysback': daysback,
            'groupsize': groupsize,
            'groupcnt': groupcnt,
            'first_day': first_day,
            'first_day_group': first_day_group,
            'last_day': last_day,
            '_': _,
        }

        add_stylesheet(req, 'tracmetrix/css/dashboard.css')
        add_script(req, 'common/js/folding.js')
        add_script(req, 'tracmetrix/javascript/prototype.js')
        add_script(req, 'tracmetrix/javascript/js-ofc-library/ofc.js')
        add_script(req, 'tracmetrix/javascript/js-ofc-library/data.js')
        add_script(req, 'tracmetrix/javascript/js-ofc-library/charts/area.js')
        add_script(req, 'tracmetrix/javascript/js-ofc-library/charts/bar.js')
        add_script(req, 'tracmetrix/javascript/js-ofc-library/charts/line.js')
        add_script(req, 'tracmetrix/javascript/js-ofc-library/charts/pie.js')
        add_script(req, 'tracmetrix/javascript/chart_reports.js')

        if req.path_info.startswith('/pdashboard/user'):
            return self._render_user_stats(req, data)

        return self._render_project_stats(req, data)

    def _enabled_metrics(self, req, defaults):
        enabled = set([m for m in defaults if req.args.has_key(m)])
        if enabled:
            metrics = {k: (k in enabled) for k in defaults}
        else:
            metrics = defaults.copy()
        return metrics

    def _render_user_stats(self, req, data):
        project_id = req.data['project_id']
        user = req.args.get('user')
        if not user:
            user = req.authname

        users = ProjectManagement(self.env).get_project_users(project_id)
        data.update({
            'user': user,
            'users': users,
        })
        if not user in users:
            users.insert(0, user)

        defaults = {
            # summary
            # time range
            # time groups
            'tkt_activity': True,
            'repos_activity': True,
            'wiki_activity': True,
        }
        metrics = self._enabled_metrics(req, defaults)
        data['metrics'] = metrics

        groupsize = data['groupsize']
        groupcnt  = data['groupcnt']
        first_day       = data['first_day']
        first_day_group = data['first_day_group']
        last_day        = data['last_day']

        db = self.env.get_read_db()

        data_json = {}

        if metrics['tkt_activity']:
            data['tkt_activity'] = reports.ticket_activity_user(project_id, user,
                                              first_day_group, last_day, groupsize, groupcnt,
                                              db, req)
            data_json['tkt_activity'] = simplejson.dumps(data['tkt_activity'].get_data())

        if metrics['repos_activity']:
            data['repos_activity'] = reports.repository_activity_user(project_id, user,
                                              first_day_group, last_day, groupsize, groupcnt,
                                              db, req)
            data_json['repos_activity'] = simplejson.dumps(data['repos_activity'].get_data())

        if metrics['wiki_activity']:
            data['wiki_activity'] = reports.wiki_activity_user(project_id, user,
                                              first_day_group, last_day, groupsize, groupcnt,
                                              db, req)
            data_json['wiki_activity'] = simplejson.dumps(data['wiki_activity'].get_data())

        data['json'] = data_json

        return ('udashboard.html', data, None)

    def _render_project_stats(self, req, data):
        project_id = req.data['project_id']

        defaults = {
            # summary
            'tkt_summary': True,
            'milestones_stats': True,
            'tkt_extra_stats': False,
            # time range
            'tkt_activity': False,
            'repos_stats': True,
            'backlog_daily': True,
            # time groups
            'repos_activity': True,
            'backlog_table': False,
            'wiki_activity': True,
        }
        metrics = self._enabled_metrics(req, defaults)

        show_completed = req.args.has_key('show_completed')

        data.update({
            'metrics': metrics,
            'show_completed': show_completed,
        })

        groupsize = data['groupsize']
        groupcnt  = data['groupcnt']
        first_day       = data['first_day']
        first_day_group = data['first_day_group']
        last_day        = data['last_day']

        db = self.env.get_read_db()

        if metrics['milestones_stats']:
            # Get list of milestone object for the project
            milestones = list(Milestone.select(self.env, project_id, show_completed, db))
            stats = []

            for milestone in milestones:
                tickets = get_tickets_for_milestone(self.env, db, milestone, 'owner')
                stat = get_ticket_stats(self.stats_provider, tickets, project_id)
                stats.append(milestone_stats_data(self.env, req, stat, milestone))

            add_stylesheet(req, 'common/css/roadmap.css')
            data.update({
                'milestones': milestones,
                'milestone_stats': stats,
            })

        project_tickets = get_project_tickets(self.env, project_id)

        if metrics['tkt_summary']:
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

        if metrics['backlog_daily'] or metrics['backlog_table'] or metrics['tkt_extra_stats']:
            tkt_group_metrics = TicketGroupMetrics(self.env, project_tickets)

            if metrics['tkt_extra_stats']:
                tkt_frequency_stats = tkt_group_metrics.get_frequency_metrics_stats()
                tkt_duration_stats = tkt_group_metrics.get_duration_metrics_stats()
                data.update({
                    'ticket_frequency_stats': tkt_frequency_stats,
                    'ticket_duration_stats': tkt_duration_stats,
                })

            if metrics['backlog_table']:
                bmi_stats = []
                d = first_day_group
                fday = datetime(d.year, d.month, d.day, tzinfo=req.tz)
                for _i in xrange(groupcnt):
                    lday = fday + timedelta(groupsize, microseconds=-1)
                    bstats = tkt_group_metrics.get_bmi_stats(fday, lday)
                    bmi_stats.append(('%s - %s' % (format_date(fday), format_date(lday)),) + bstats)
                    fday += timedelta(groupsize)
                data['project_bmi_stats'] = bmi_stats

            if metrics['backlog_daily']:
                # get daily backlog history
                backlog_history = tkt_group_metrics.get_daily_backlog_history(first_day, last_day)
                daily_backlog_chart = tkt_group_metrics.get_daily_backlog_chart(backlog_history)
                data['ds_daily_backlog'] = daily_backlog_chart


        if metrics['repos_stats']:
            # Get daily commits history
            changeset_group_stats = ChangesetsStats(self.env, project_id, first_day, last_day)
            commits_by_date = changeset_group_stats.get_commit_by_date()
            commits_by_date_chart = changeset_group_stats.get_commit_by_date_chart(commits_by_date)
            data['ds_commit_by_date'] = commits_by_date_chart


        data_json = {}

        if metrics['tkt_activity']:
            data['ticket_activity'] = reports.ticket_activity(project_id,
                                          first_day, last_day,
                                          db, req)
            data_json['ticket_activity'] = simplejson.dumps(data['ticket_activity'].get_data())

        if metrics['repos_activity']:
            data['repository_activity'] = reports.repository_activity(project_id,
                                              first_day_group, last_day, groupsize, groupcnt,
                                              db, req, authors_limit=self.tm.authors_limit_repos)
            data_json['repository_activity'] = simplejson.dumps(data['repository_activity'].get_data())

        if metrics['wiki_activity']:
            data['wiki_activity'] = reports.wiki_activity(project_id,
                                          first_day, last_day, groupsize, groupcnt,
                                          db, req, authors_limit=self.tm.authors_limit_wiki)
            data_json['wiki_activity'] = simplejson.dumps(data['wiki_activity'].get_data())

        data['json'] = data_json

        return ('pdashboard.html', data, None)

    # ITemplateProvider methods
    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

    def get_htdocs_dirs(self):
        from pkg_resources import resource_filename
        return [('tracmetrix', resource_filename(__name__, 'htdocs'))]
