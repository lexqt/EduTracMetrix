from setuptools import setup

PACKAGE = 'tracmetrix'

extra = {} 
try:
    from trac.util.dist import get_l10n_cmdclass
    cmdclass = get_l10n_cmdclass()
    if cmdclass:
        extra['cmdclass'] = cmdclass
        extractors = [
            ('**.py',                'python', None),
            ('**/templates/**.html', 'genshi', None),
            ('**/templates/**.txt',  'genshi', {
                'template_class': 'genshi.template:NewTextTemplate',
            }),
        ]
        extra['message_extractors'] = {
            PACKAGE: extractors,
        }
except ImportError:
    pass

setup(
    description='Plugin to provide Trac project metrics and statistics',
    keywords='trac plugin metrics statistics',
    version='0.2',
    url='',
    license='http://www.opensource.org/licenses/bsd-license.php',
    author='Bhuricha Sethanandha, Aleksey A. Porfirov',
    author_email='lexqt@yandex.ru',
    long_description="""
    This Trac 0.12 (EduTrac) plugin provides support for project metrics and statistics.

    Original plugin: http://trac-hacks.org/wiki/TracMetrixPlugin
    """,
    name = 'EduTracMetrix',
    packages = [PACKAGE],
    entry_points = {
        'trac.plugins': [
            'tracmetrix.mdashboard = tracmetrix.mdashboard',
            'tracmetrix.web_ui = tracmetrix.web_ui',
            'tracmetrix.model = tracmetrix.model'
        ]
    },
    package_data={PACKAGE: ['templates/*.html', 
                            'htdocs/css/*.css', 
                            'locale/*/LC_MESSAGES/*.mo']},
    **extra
)

#### AUTHORS ####
## Author of original TracMetrixPlugin:
## Bhuricha Sethanandha at Portland State University
## khundeen@gmail.com
##
## Maintainer of original TracMetrixPlugin:
## Ryan J Ollos
## ryano@physiosonics.com
##
## Author of EduTrac adaptation, a lot of fixes and enhancements:
## Aleksey A. Porfirov
## lexqt@yandex.ru
## github: lexqt
