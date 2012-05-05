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

from datetime import date

from trac.core import Component, implements
from trac.ticket import Ticket, model
from trac.ticket.roadmap import ITicketGroupStatsProvider, TicketGroupStats
from trac.util.datefmt import utc, to_utimestamp, to_datetime, format_date

from tracmetrix.api import date_generator, _



class ProgressTicketGroupStatsProvider(Component):
    implements(ITicketGroupStatsProvider)

    # TODO: options
    done_resolutions = ('fixed', 'done')
    waste_types = ('defect',)
    new_statuses = ('new', 'approved')

    def get_ticket_group_stats(self, ticket_ids, pid):

        total_cnt = len(ticket_ids)
        if total_cnt:

            db = self.env.get_db_cnx()
            cursor = db.cursor()

            closed_cnt = cursor.execute('''
                SELECT COUNT(*) FROM ticket
                WHERE status = 'closed' AND project_id=%s AND id IN %s
                ''', (pid, tuple(ticket_ids)))
            closed_cnt = cursor.fetchone()[0]

            active_cnt = cursor.execute('''
                SELECT COUNT(*) FROM ticket
                WHERE project_id=%s AND status IN %s AND id IN %s
                ''', (pid, tuple(self.new_statuses), tuple(ticket_ids)))
            active_cnt = cursor.fetchone()[0]

        else:
            closed_cnt = 0
            active_cnt = 0

        inprogress_cnt = total_cnt - ( active_cnt + closed_cnt)

        stat = TicketGroupStats(_('ticket status'), '')
        stat.add_interval(_('Closed'), closed_cnt,
                          {'status': 'closed', 'group': 'resolution'},
                          'closed', True)
        stat.add_interval(_('In progress'), inprogress_cnt,
                          {'status': ['!closed']+['!'+st for st in self.new_statuses]},
                          'inprogress', False)
        stat.add_interval(_('New'), active_cnt,
                          {'status': self.new_statuses},
                          'new', False)

        stat.refresh_calcs()
        return stat

    def get_ticket_resolution_group_stats(self, ticket_ids, pid):

        stat = TicketGroupStats(_('ticket resolution'), '')

        if len(ticket_ids):
            db = self.env.get_db_cnx()
            cursor = db.cursor()

            count_by_resolution = [] # list of dictionaries with keys name and count
            for resolution in model.Resolution.select(self.env, pid=pid, db=db):
                cursor.execute('''
                    SELECT COUNT(*) FROM ticket
                    WHERE project_id=%s AND status = 'closed' AND resolution=%s AND id IN %s
                    ''', (pid, resolution.name, tuple(ticket_ids)))

                count = cursor.fetchone()[0]
                if count > 0:
                    count_by_resolution.append({'name': resolution.name, 'count': count})

            for t in count_by_resolution:
                if t['name'] in self.done_resolutions:
                    stat.add_interval(t['name'], t['count'],
                                      {'resolution': t['name']}, 'value', True)
                else:
                    stat.add_interval(t['name'], t['count'],
                                      {'resolution': t['name']}, 'waste', False)

        stat.refresh_calcs()
        return stat

    def get_ticket_type_group_stats(self, ticket_ids, pid):

        total_cnt = len(ticket_ids)
        if total_cnt:

            db = self.env.get_db_cnx()
            cursor = db.cursor()

            type_count = [] # list of dictionary with key name and count

            for type_ in model.Type.select(self.env, pid=pid):

                count = cursor.execute('''
                    SELECT COUNT(*) FROM ticket
                    WHERE project_id=%s AND type = %s AND id IN %s
                    ''', (pid, type_.name, tuple(ticket_ids)))
                count = cursor.fetchone()[0]
                if count > 0:
                    type_count.append({'name':type_.name, 'count':count})

        else:
            type_count = []

        stat = TicketGroupStats(_('ticket type'), '')


        for type in type_count:

            if type['name'] not in self.waste_types:

                stat.add_interval(type['name'], type['count'],
                                  {'type': type['name']}, 'value', True)

            else:
                stat.add_interval(type['name'], type['count'],
                                  {'type': type['name']}, 'waste', False)

        stat.refresh_calcs()
        return stat

class TicketTypeGroupStatsProvider(Component):
    implements(ITicketGroupStatsProvider)

    # TODO: option
    waste_types = ('defect',)

    def get_ticket_group_stats(self, ticket_ids, pid):

        total_cnt = len(ticket_ids)
        if total_cnt:

            db = self.env.get_db_cnx()
            cursor = db.cursor()

            type_count = [] # list of dictionary with key name and count

            for type in model.Type.select(self.env, pid=pid):

                cursor.execute('''
                    SELECT COUNT(*) FROM ticket
                    WHERE project_id=%s AND type = %s AND id IN %s
                    ''', (pid, type.name, tuple(ticket_ids)))
                count = cursor.fetchone()[0]
                if count > 0:
                    type_count.append({'name':type.name, 'count':count})

        else:
            type_count = []

        stat = TicketGroupStats(_('ticket type'), '')


        for type in type_count:

            if type['name'] not in self.waste_types:

                stat.add_interval(type['name'], type['count'],
                                  {'type': type['name']}, 'value', True)

            else:
                stat.add_interval(type['name'], type['count'],
                                  {'type': type['name']}, 'waste', False)

        stat.refresh_calcs()
        return stat

class TicketGroupMetrics(object):

    def __init__(self, env, tkt_ids):

        self.env = env
        self.ticket_ids = tkt_ids
        self.num_tickets = len(tkt_ids)

        self.tickets = [Ticket(env,id) for id in tkt_ids]
        self.ticket_metrics = [TicketMetrics(env,ticket) for ticket in self.tickets ]

    def get_num_comment_stats(self):

        data = [tkt_metrics.num_comment for tkt_metrics in self.ticket_metrics]
        stats = DescriptiveStats(data)
        return stats

    def get_num_closed_stats(self):

        data = [tkt_metrics.num_closed for tkt_metrics in self.ticket_metrics]
        stats = DescriptiveStats(data)
        return stats

    def get_num_milestone_stats(self):

        data = [tkt_metrics.num_milestone for tkt_metrics in self.ticket_metrics]
        stats = DescriptiveStats(data)
        return stats

    def get_frequency_metrics_stats(self):

        return {_("Number of comments per ticket"): self.get_num_comment_stats(),
                _("Number of milestone changed per ticket"): self.get_num_milestone_stats(),
                _("Number of closed per ticket"): self.get_num_closed_stats()}

    def get_duration_metrics_stats(self):

        return {_("Lead time"): self.get_lead_time_stats(),
                _("Closed time"): self.get_closed_time_stats()}

    def get_lead_time_stats(self):

        data = [tkt_metrics.lead_time for tkt_metrics in self.ticket_metrics]
        stats = DescriptiveStats(data)
        return stats

    def get_closed_time_stats(self):
        data = [tkt_metrics.closed_time for tkt_metrics in self.ticket_metrics]
        stats = DescriptiveStats(data)
        return stats

    def get_tickets_created_during(self, start_date, end_date):

        end_date = end_date.replace(hour=23, minute=59, second=59)

        tkt_ids = []

        for ticket in self.tickets:
            if start_date <= ticket.time_created <= end_date:
                tkt_ids.append(ticket.id)

        return tkt_ids

    def get_remaning_opened_ticket_on(self, end_date):

        end_date = end_date.replace(hour=23, minute=59, second=59)

        tkt_ids = []

        for ticket in self.tickets:

            # only consider the ticket that was created before the end date.
            if ticket.time_created <= end_date:

                if ticket.values['status'] == 'closed':

                    was_opened = True
                    # check change log to find the date when the ticket was closed.
                    for t, author, field, oldvalue, newvalue, permanent in ticket.get_changelog():
                        if field == 'status':

                            if newvalue == 'closed':
                                if t <= end_date:
                                    was_opened = False

                            else:
                                if t <= end_date:
                                    was_opened = True

                    if was_opened == True:
                        tkt_ids.append(ticket.id)

                # Assume that ticket that is not closed are opened
                else:
                    # only add the ticket that was created before the end date
                    if end_date >= ticket.time_created:
                        tkt_ids.append(ticket.id)

        return tkt_ids


    def get_tickets_closed_during(self, start_date, end_date):

        end_date = end_date.replace(hour=23, minute=59, second=59)

        tkt_ids = []

        for ticket in self.tickets:
            for t, author, field, oldvalue, newvalue, permanent in ticket.get_changelog():
                if field == 'status' and \
                    newvalue == 'closed' and \
                    start_date <= t <= end_date:

                    tkt_ids.append(ticket.id)

                    #only count the first closed
                    break

        return tkt_ids

    def get_bmi_stats(self, start_date, end_date):

        created_tickets = self.get_tickets_created_during(start_date, end_date)
        opened_tickets = self.get_remaning_opened_ticket_on(end_date)
        closed_tickets = self.get_tickets_closed_during(start_date, end_date)

        if opened_tickets == []:
            bmi = 0
        else:
            bmi = float(len(closed_tickets)) * 100 / float(len(opened_tickets))

        return (created_tickets,
                opened_tickets,
                closed_tickets,
                bmi)

    def get_daily_backlog_history(self, start_date, end_date):
        """
            returns list of tuple (date,stats)
                date is date value in epoc time
                stats is dictionary of {'created':[], 'opened':[], 'closed':[]}
        """

        dates = list(date_generator(start_date, end_date))
        end_date = end_date.replace(hour=23, minute=59, second=59)


        # each key is the list of list of ticket.  The index of the list is corresponding
        # to the index of the date in dates list.
        backlog_stats = {'created':[], 'opened':[], 'closed':[]}

        # initialize backlog_stats

        for date in dates:
            for key in backlog_stats:
                backlog_stats[key].append([])

        # start by getting the list of opened ticket at the end of the start date.
        backlog_stats['opened'][0] = self.get_remaning_opened_ticket_on(start_date)

        for ticket in self.tickets:

            # only consider the ticket that was created before end dates.
            if ticket.time_created <= end_date:

                # only track the ticket that create since start_date
                if ticket.time_created >= start_date:
                    # determine index
                    date = ticket.time_created.date()
                    #get index of day in the dates list
                    index = dates.index(date)

                    # add ticket created ticket list
                    backlog_stats['created'][index].append(ticket.id)

                for t, author, field, oldvalue, newvalue, permanent in ticket.get_changelog():

                    if field == 'status' and start_date <= t <= end_date and \
                            'closed' in (newvalue, oldvalue):
                        index = dates.index(t.date())
                        if newvalue == 'closed':
                            backlog_stats['closed'][index].append(ticket.id)
                        else:
                            backlog_stats['opened'][index].append(ticket.id)

        # update opened ticket list
        for idx, list_ in enumerate(backlog_stats['opened']):

            if idx > 0:

                # merge list of opened ticket from previous day
                list_.extend(backlog_stats['opened'][idx-1])

                # add created ticket to opened ticket list
                list_.extend(backlog_stats['created'][idx])

                # remove closed ticket from opened ticket list.
                for id in backlog_stats['closed'][idx]:
                    try:
                        list_.remove(id)
                    except ValueError, e:
                        pass


                list_.sort()

        return (dates, backlog_stats)

    def get_daily_backlog_chart(self, backlog_history):
        '''
        return data point based on Yahoo JSArray format
        '''

        dates = backlog_history[0]
        backlog_stats = backlog_history[1]

        # create counted list.
        opened_tickets_dataset  = [len(set(list)) for list in backlog_stats['opened']]
        created_tickets_dataset = [len(set(list)) for list in backlog_stats['created']]
        closed_tickets_dataset  = [len(set(list)) for list in backlog_stats['closed']]

#        bmi_dataset = []
#        for i in range(len(opened_tickets_dataset)):
#            if opened_tickets_dataset[i] == 0:
#                bmi_dataset.append(0.0)
#            else:
#                bmi_dataset.append(float(closed_tickets_dataset[i])*100/float(opened_tickets_dataset[i]))

        ds_daily_backlog = ''

        for idx, date_ in enumerate(dates):
                    ds_daily_backlog = ds_daily_backlog +  '{ date: "%s", opened: %d, closed: %d, created: %d}, ' \
                          % (format_date(date_, tzinfo=utc), opened_tickets_dataset[idx], \
                             closed_tickets_dataset[idx], created_tickets_dataset[idx])

        return '[ ' + ds_daily_backlog + ' ];'



class TicketMetrics(object):

    def __init__(self, env, ticket):
        self.lead_time = 0
        self.closed_time = 0
        self.num_comment = 0
        self.num_closed = 0
        self.num_milestone = 0

        self.__collect_history_data(ticket)

    def __inseconds(self, duration):
        # convert timedelta object to interger value in seconds
        return duration.days*24*3600 + duration.seconds

    def __collect_history_data(self, ticket):

        previous_status = 'new'
        previous_status_change = ticket.time_created

        tkt_log = ticket.get_changelog()

        first_milestone_change = True

        for t, author, field, oldvalue, newvalue, permanent in tkt_log:

            if field == 'milestone' and first_milestone_change and oldvalue != '':
                self.num_milestone += 1;
                first_milestone_change = False

            elif field == 'milestone':
                if newvalue != '':
                    self.num_milestone += 1;

            elif field == 'status':

                elapsed_time = self.__inseconds(t-previous_status_change)
                if newvalue == 'closed':
                    self.num_closed += 1
                    self.lead_time += elapsed_time
                elif oldvalue == 'closed':
                    self.closed_time += elapsed_time
                else:
                    self.lead_time += elapsed_time

                previous_status = newvalue
                previous_status_change = t

            elif field == 'comment':
                if newvalue != '':
                    self.num_comment += 1

        # Calculate the ticket time up to current.
        time_to_now = self.__inseconds(to_datetime(None, utc)- previous_status_change)
        if previous_status == 'closed':
            self.closed_time += time_to_now
        else:
            self.lead_time += time_to_now

    def get_all_metrics(self):
        return {'lead_time':self.lead_time,
                'closed_time':self.closed_time,
                'num_comment':self.num_comment,
                'num_closed':self.num_closed,
                'num_milestone':self.num_milestone}

class DescriptiveStats(object):

    def __init__(self, sequence):
        # sequence of numbers we will process
        # convert all items to floats for numerical processing
        self.sequence = [float(item) for item in sequence]


    def sum(self):
        if len(self.sequence) < 1:
            return None
        else:
            return sum(self.sequence)

    def count(self):
        return len(self.sequence)

    def min(self):
        if len(self.sequence) < 1:
            return None
        else:
            return min(self.sequence)

    def max(self):
        if len(self.sequence) < 1:
            return None
        else:
            return max(self.sequence)

    def avg(self):
        if len(self.sequence) < 1:
            return None
        else:
            return sum(self.sequence) / len(self.sequence)

    def median(self):
        if len(self.sequence) < 1:
            return None
        else:
            self.sequence.sort()
            return self.sequence[len(self.sequence) // 2]

    def stdev(self):
        if len(self.sequence) < 1:
            return None
        else:
            avg = self.avg()
            sdsq = sum([(i - avg) ** 2 for i in self.sequence])
            stdev = (sdsq / (len(self.sequence) - 1 or 1)) ** .5
            return stdev

    def __iter__(self):
        yield self.avg()
        yield self.median()
        yield self.max()
        yield self.min()
        yield self.stdev()


class ChangesetsStats(object):

    def __init__(self, env, pid, start_date=None, stop_date=None):

        self.env = env
        self.pid = pid

        self.start_date = start_date
        self.stop_date = stop_date
        self.first_rev = self.last_rev = None

        if start_date != None and stop_date !=None:
            self.set_date_range(start_date, stop_date)

    def set_date_range(self, start_date, stop_date):

        db = self.env.get_read_db()
        cursor = db.cursor()

        cursor.execute('''
            SELECT rev, time, author
            FROM revision
            WHERE repos IN (
                SELECT id FROM repository
                WHERE name='project_id' AND value=%s
            ) AND time >= %s AND time < %s
            ORDER BY time
            ''', (str(self.pid), to_utimestamp(start_date), to_utimestamp(stop_date)))

        self.changesets = []
        for rev, time, author in cursor:
            self.changesets.append((rev,time,author))

        self.start_date = start_date
        self.stop_date = stop_date
        if not self.changesets:
            self.first_rev = self.last_rev = 0
        else:
            self.first_rev = self.changesets[0][0]
            self.last_rev = self.changesets[-1][0]

    def get_commit_by_date(self):

        dates = list(date_generator(self.start_date, self.stop_date))
        numcommits = [0 for i in dates]

        for rev, time, author in self.changesets:
            date_ = to_datetime(time, utc).date()
            index = dates.index(date_)
            numcommits[index] += 1

        return (dates, numcommits)

    # Return Yahoo JSARRAY format
    def get_commit_by_date_chart(self, commit_history):

        numdates = commit_history[0]
        numcommits = commit_history[1]

        ds_commits = ''

        for idx, date_ in enumerate(numdates):
                    ds_commits = ds_commits +  '{ date: "%s", commits: %d}, ' \
                          % (format_date(date_, tzinfo=utc), numcommits[idx])

        return '[ ' + ds_commits + ' ];'


