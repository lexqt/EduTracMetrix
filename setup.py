#!/usr/bin/env python
# -*- coding: utf-8 -*-

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
    version='0.3',
    url='',
    license='http://www.opensource.org/licenses/bsd-license.php',
    author='Aleksey A. Porfirov',
    author_email='lexqt@yandex.ru',
    long_description="""
    This Trac 0.12 (EduTrac) plugin provides support for project metrics and statistics.

    Used plugins:
    http://trac-hacks.org/wiki/TracMetrixPlugin
    http://trac-hacks.org/wiki/StractisticsPlugin
    """,
    name = 'EduTracMetrix',
    packages = [PACKAGE],
    entry_points = {
        'trac.plugins': [
            'tracmetrix = tracmetrix',
        ]
    },
    package_data={PACKAGE: ['templates/*.html',
                            'htdocs/css/*.css',
                            'htdocs/javascript/*.*', 
                            'htdocs/javascript/js-ofc-library/*.*',
                            'htdocs/javascript/js-ofc-library/charts/*.*',
                            'htdocs/swf/*.*',
                            'locale/*/LC_MESSAGES/*.mo']},
    **extra
)

#### AUTHORS ####
## Author of original TracMetrixPlugin:
## Bhuricha Sethanandha at Portland State University
## khundeen@gmail.com
##
## Authors of original StractisticsPlugin:
## GMV SGI Team <http://www.gmv-sgi.es>
## Daniel Gómez Brito, Manuel Jesús Recena Soto
## dagomez@gmv.com, mjrecena@gmv.com
##
## Maintainer of TracMetrixPlugin and StractisticsPlugin:
## Ryan J Ollos
## ryano@physiosonics.com
##
## Author of EduTrac adaptation, a lot of fixes and enhancements:
## Aleksey A. Porfirov
## lexqt@yandex.ru
## github: lexqt


# From Stractistics README.txt
#Stractistics
#Copyright (C) 2008 GMV SGI Team <http://www.gmv-sgi.es>
#
#Developed by:
#    Daniel Gómez Brito <dagomez@gmv.com>
#
#Contributors:
#    Manuel Jesús Recena Soto <mjrecena@gmv.com>
#
#GMV Soluciones Globales Internet, S.A.
#Avda. Américo Vespucio, Nº5
#Edificio Cartuja, Bloque E, 1ª Planta
#41092 Sevilla (España)
