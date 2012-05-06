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

import re
from itertools import groupby

from trac.core import Component, implements
from trac.config import ExtensionOption
from trac.resource import ResourceNotFound

from trac.ticket import Milestone, TicketSystem
from trac.ticket.roadmap import ITicketGroupStatsProvider, get_ticket_stats, get_tickets_for_milestone, milestone_stats_data
from trac.util.compat import sorted
from trac.util.datefmt import to_datetime, format_date, utc
from trac.web import IRequestHandler

from trac.web.chrome import add_stylesheet, INavigationContributor, add_ctxtnav
from genshi.builder import tag

from tracmetrix.api import TracMetrix, date_generator, _


__all__ = ['MDashboard']


def get_every_tickets_in_milestone(db, project_id, milestone):
    """
    Get the list of ticket id that have ever been in this milestone.
    This includes the ticket that was assigned to the milestone and
    later reassigned to a different milestone.
    """
    cursor = db.cursor()

    cursor.execute('''
        SELECT id FROM ticket WHERE id IN
            (SELECT DISTINCT ticket FROM ticket_change
            WHERE ticket_change.field='milestone' AND
                ticket_change.oldvalue=%s
            ) AND project_id=%s
        UNION
        SELECT id FROM ticket WHERE milestone=%s AND project_id=%s
        ''', (milestone, project_id, milestone, project_id))

    tickets = []
    for tkt_id, in cursor:
        tickets.append(tkt_id)

    return tickets


def collect_tickets_status_history(db, ticket_ids, milestone):

    history = {}

    def add_milestone_event(history, time, event, ticket_id):
#        time = to_datetime(time).date()
        if history.has_key(time):
            history[time][event].add(ticket_id)
        else:
            history[time]={'Enter':set(), 'Leave':set(), 'Finish':set()}
            #make the list of ticket as set so that there is no duplicate
            #this is to handle the case where many ticket fields are changed
            #at the same time.
            history[time][event].add(ticket_id)

    def add_ticket_status_event(history, time, old_status, status, tkt_id):
        # ticket was closed
        if status == 'closed':
            add_milestone_event(history, time, 'Finish', tkt_id)
        # ticket was reopened
        elif old_status == 'closed':
            add_milestone_event(history, time, 'Enter', tkt_id)

    q = '''
        SELECT ticket.id AS tid, ticket.type, ticket.time, ticket.status,
            ticket_change.time AS change_time, ticket.milestone, ticket_change.field,
            ticket_change.oldvalue, ticket_change.newvalue
        FROM ticket JOIN ticket_change ON ticket.id = ticket_change.ticket
            AND (ticket_change.field='status' OR ticket_change.field='milestone')
        WHERE ticket.id IN %s
        UNION
        SELECT ticket.id AS tid, ticket.type, ticket.time, ticket.status,
            ticket.time AS change_time, ticket.milestone, null, null, null FROM ticket
        WHERE ticket.time = ticket.changetime AND ticket.id IN %s
        ORDER BY tid, change_time ASC
    '''
    ids = tuple(ticket_ids)
    cursor = db.cursor()
    cursor.execute(q, (ids, ids))

    event_history = cursor.fetchall()

    # TODO The tricky thing about this is that we have to deterimine 5 different type of ticket.
    # 1) created with milestone and remain in milestone (new and modified)
    # 2) create with milestone then later leave milestone
    # 3) created with milestone and leave milestone and come back and remain in milestone
    # 4) create w/o milestone and later assigned to milestone and remain in the milestone
    # 5) create w/o milestone then later assigned to milestone but then later leave milestone
    # 6) Create w/o milestone and closed then later assigned to milestone
    # 7) create with different milestone then later assigned to milestone
    # Need to find the first time each ticket enters the milestone

    # key is the tuple (tkt_id, tkt_createdtime)
    for ticket, events in groupby(event_history, lambda l: (l[0], l[2])):

        status_events = []
        # flag to determine whether the milestone has changed for the first time
        milestone_changed = False

        # Assume that ticket is created with out milestone.
        # The event will be store in the list until we find out what milestone do the
        # event belong to.
        current_milestone = None
        current_status    = None
        for tkt_id, tkt_type, tkt_createdtime, tkt_status, tkt_changedtime, \
            tkt_milestone, tkt_field, tkt_oldvalue, tkt_newvalue in events:

            # If the ticket was modified
            if tkt_createdtime != tkt_changedtime:

                # Ticket that was created with out milestone
                if tkt_field == 'milestone':

                    # Ticket was created with blank milestone or other milestone
                    if tkt_newvalue == milestone.name:

                        current_milestone = milestone.name

                        # in case that closed ticket was assigned to the milestone
                        if current_status == 'closed':
                            add_milestone_event(history, tkt_changedtime, 'Enter', tkt_id)
                            add_ticket_status_event(history, tkt_changedtime, tkt_oldvalue, tkt_status, tkt_id)
                        else:
                            add_milestone_event(history, tkt_changedtime, 'Enter', tkt_id)

                    # Ticket leave the milestone
                    elif tkt_oldvalue == milestone.name:

                        current_milestone = tkt_newvalue

                        # Ticket was create with milestone
                        if not milestone_changed:
                            # update the enter event
                            add_milestone_event(history, tkt_createdtime, 'Enter', tkt_id)
                            # it means that the eariler status event has to be in the milestone.
                            for stkt_changedtime, stkt_oldvalue, stkt_newvalue, stkt_id in status_events:
                                add_ticket_status_event(history, stkt_changedtime, stkt_oldvalue, stkt_newvalue, stkt_id)

                        add_milestone_event(history, tkt_changedtime, 'Leave', tkt_id)

                    milestone_changed = True

                elif tkt_field == 'status':

                    current_status = tkt_newvalue

                    # this event happen before milestone is changed
                    if not milestone_changed:
                        status_events.append((tkt_changedtime, tkt_oldvalue, tkt_newvalue, tkt_id))
                    else:
                        # only add ticket status that happen in the milestone
                        if current_milestone == milestone.name:
                            add_ticket_status_event(history, tkt_changedtime, tkt_oldvalue, tkt_newvalue, tkt_id)

            # new ticket that was created and assigned to the milestone
            else:
                add_milestone_event(history, tkt_createdtime, 'Enter', tkt_id)

        # if milestone never changed it means that the ticket was assing to the milestone.
        if not milestone_changed:

            add_milestone_event(history, tkt_createdtime, 'Enter', tkt_id)
            # it means that the eariler status event has to be in the milestone.
            for tkt_changedtime, tkt_oldvalue, tkt_newvalue, tkt_id in status_events:
                add_ticket_status_event(history, tkt_changedtime, tkt_oldvalue, tkt_newvalue, tkt_id)

    return history

def prepare_to_cumulate(sorted_events):
    dhist = {}
    for date, date_events in groupby(sorted_events, lambda (t, events): to_datetime(t).date()):
        evset = {'Enter': set(), 'Leave': set(), 'Finish': set()}
        dhist[date] = evset
        date_events_list = list(date_events)
        for (t, events) in date_events_list:
            for k, ids in events.iteritems():
                evset[k] |= ids
        # resolve Enter / Leave conflicts
        enter_leave_ids = evset['Enter'] & evset['Leave']
        if enter_leave_ids:
            evs = {'Enter': None, 'Leave': None}
            last = {'Enter': None, 'Leave': None}
            for k in ('Enter', 'Leave'):
                evs[k] = sorted([(t, evs['Enter']) for (t, evs) in date_events_list],
                                key=lambda (t, ids): t)
            for id in enter_leave_ids:
                for k in ('Enter', 'Leave'):
                    last[k] = 0
                    for t, ids in reversed(evs[k]):
                        if id in ids:
                            last[k] = t
                            break
                to_del = (last['Enter'] > last['Leave']) and 'Leave' or 'Enter'
                evset[to_del].remove(id)
    return dhist

def make_cumulative_data(dates, history):
    tkt_counts = {'Enter':[], 'Leave':[], 'Finish':[]}
    tktset = {'Enter': set(), 'Leave': set(), 'Finish': set()}

    for idx, date in enumerate(dates):
        if date in history:
            event = history[date]
            for id in event['Enter']:
                if id in tktset['Finish']:
                    tktset['Finish'].remove(id)
                if id not in tktset['Enter']:
                    tktset['Enter'].add(id)
                if id in tktset['Leave']:
                    tktset['Leave'].remove(id)
            for id in event['Finish']:
                tktset['Finish'].add(id)
            for id in event['Leave']:
                if id in tktset['Enter']:
                    tktset['Enter'].remove(id)
                if id in tktset['Finish']:
                    tktset['Finish'].remove(id)
                tktset['Leave'].add(id)

        for k in tkt_counts:
            tkt_counts[k].append(len(tktset[k]))

    return tkt_counts



class MDashboard(Component):

    implements(INavigationContributor, IRequestHandler)

    stats_provider = ExtensionOption('tracmetrix-mdashboard', 'stats_provider',
                                     ITicketGroupStatsProvider,
                                     'ProgressTicketGroupStatsProvider',
        """Name of the component implementing `ITicketGroupStatsProvider`,
        which is used to collect statistics on groups of tickets for display
        in the milestone metrics views.""")

    tickettype_stats_provider = ExtensionOption('tracmetrix-mdashboard', 'tickettype_stats_provider',
                                     ITicketGroupStatsProvider,
                                     'TicketTypeGroupStatsProvider',
        """Name of the component implementing `ITicketGroupStatsProvider`,
        which is used to collect statistics on groups of tickets for display
        in the milestone metrics views.""")

    def __init__(self):
        self.tm = TracMetrix(self.env)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'mdashboard'

    def get_navigation_items(self, req):
        if 'ROADMAP_VIEW' in req.perm:
            yield ('mainnav', 'mdashboard',
                   tag.a(_('Milestone metrics'), href=req.href.mdashboard()))

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info.startswith('/mdashboard')

    def process_request(self, req):
        req.perm.require('MILESTONE_VIEW')
        pid = req.project

        valid_milestone = True

        m = re.match(r'/mdashboard/(.*)', req.path_info)
        if not m:
            valid_milestone = False
        else:
            milestone_id = m.group(1)
            try:
                milestone = Milestone(self.env, pid, milestone_id)
            except ResourceNotFound:
                valid_milestone = False

        add_ctxtnav(req, _('To project statistics'), req.href.pdashboard(), _('Project statistics'))
        add_stylesheet(req, 'tracmetrix/css/dashboard.css')
        add_stylesheet(req, 'common/css/roadmap.css')

        if valid_milestone:
            return self._render_view(req, milestone)
        else:
            return self._render_milestone_list(req)

    def _render_milestone_list(self, req):
        project_id = req.data['project_id']
        milestones = Milestone.select(self.env, project_id, include_completed=True)
        data = {
            'milestones': milestones,
        }
        return 'mdashboard.html', data, None

    def _render_view(self, req, milestone):
        available_groups = []
        component_group_available = False
        project_id = req.data['project_id']
        ticket_fields = TicketSystem(self.env).get_ticket_fields(pid=project_id)

        # collect fields that can be used for grouping
        for name, field in ticket_fields.iteritems():
            if field['type'] == 'select' and name != 'milestone' \
                    or name in ('owner', 'reporter'):
                available_groups.append({'name': name,
                                         'label': field['label']})
                if name == 'component':
                    component_group_available = True

        # determine the field currently used for grouping
        by = None
        if component_group_available:
            by = 'component'
        elif available_groups:
            by = available_groups[0]['name']
        by = req.args.get('by', by)

        db = self.env.get_read_db()
        tickets = get_tickets_for_milestone(self.env, db, milestone, by)
        stat = get_ticket_stats(self.stats_provider, tickets, project_id)
        tstat = get_ticket_stats(self.tickettype_stats_provider, tickets, project_id)

        # Data for milestone and timeline
        data = {
            'milestone': milestone,
            'tickethistory' : [],
            'dates' : [],
            'ticketstat' : {},
            'yui_base_url': self.tm.yui_base_url,
            '_': _,
        }

        data.update(milestone_stats_data(self.env, req, stat, milestone))

        ticketstat = {'name':'ticket type'}
        ticketstat.update(milestone_stats_data(self.env, req, tstat, milestone))
        data['ticketstat'] = ticketstat

        # get list of ticket ids that in the milestone
        everytickets = get_every_tickets_in_milestone(db, project_id, milestone.name)

        if everytickets:
            tkt_history = collect_tickets_status_history(db, everytickets, milestone)
            if tkt_history:

                # Sort the key in the history list
                # returns sorted list of tuple of (key, value)
                sorted_events = sorted(tkt_history.items(), key=lambda(t,events):(t))

                # Get first date that ticket enter the milestone
                min_time = sorted_events[0][0]
                begin_date = to_datetime(min_time, tzinfo=req.tz)

                if milestone.is_completed:
                    end_date = milestone.completed
                else:
                    end_date = None
                end_date = to_datetime(end_date, tzinfo=req.tz)

                dates = list(date_generator(begin_date, end_date))

                #Create a data for the cumulative flow chart.
                date_history = prepare_to_cumulate(sorted_events)
                tkt_cumulative_table = make_cumulative_data(dates, date_history)

                #prepare Yahoo datasource for comulative flow chart
                dscumulative = ''
                for idx, date in enumerate(dates):
                    dscumulative = dscumulative +  '{ date: "%s", enter: %d, leave: %d, finish: %d}, ' \
                          % (format_date(date,tzinfo=utc), tkt_cumulative_table['Enter'][idx], \
                             tkt_cumulative_table['Leave'][idx], tkt_cumulative_table['Finish'][idx])

                data['tickethistory'] = tkt_cumulative_table
                data['dates'] = dates
                data['dscumulative'] = '[ ' + dscumulative + ' ];'

        return 'mdashboard.html', data, None

