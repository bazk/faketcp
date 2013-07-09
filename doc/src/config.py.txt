import logging
import time

LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'verbose': {
            'format': '[ %(asctime)s ] [%(levelname)s] %(message)s'
        },
        'test': {
            '()': 'config.MyFormatter',
            'format': '[ %(asctime)s ] [ %(process)d ] [%(levelname)s] %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'null': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler',
        },
        'console':{
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'test'
        }
    },
    'loggers': {
        'rdp': {
            'handlers': ['console'],
            'level': 'INFO'
        }
    }
}

class MyFormatter(logging.Formatter):
    beginning = time.time()

    def formatTime(self, record, datefmt=None):
        return '%.8f' % (record.created - self.beginning)