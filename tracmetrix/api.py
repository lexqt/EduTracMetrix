from datetime import date, timedelta

from trac.core import Component
from trac.config import Option

from trac.util.translation import domain_functions



__all__ = ['TeamCalendarSetupParticipant']

_, tag_, N_, add_domain = \
    domain_functions('tracmetrix', ('_', 'tag_', 'N_', 'add_domain'))


class TracMetrix(Component):

    yui_base_url = Option('tracmetrix', 'yui_base_url',
                          default='http://yui.yahooapis.com/2.7.0',
                          doc='Location of YUI API')

    def __init__(self):
        import pkg_resources
        locale_dir = pkg_resources.resource_filename(__name__, 'locale')
        add_domain(self.env.path, locale_dir)


def date_generator(from_date, to_date):
    ONE_DAY = timedelta(days=1)
    fd = from_date
    td = to_date
    from_date = date(fd.year, fd.month, fd.day)
    to_date = date(td.year, td.month, td.day) + ONE_DAY
    if from_date >= to_date:
        return
    while from_date != to_date:
        yield from_date
        from_date = from_date + ONE_DAY

