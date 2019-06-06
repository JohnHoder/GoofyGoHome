#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from configparser import ConfigParser


class ConfigValidator(ConfigParser):
    def __init__(self, config_file, file=False):
        super(ConfigValidator, self).__init__()

        if file == True:
            self.read(config_file)
        else:
            self.read_string(config_file)
        self.validate_config()

    def validate_config(self):
        required_values = {
            'general': {
                'SOCKET_PATH': None,
                'DAEMON_SLEEP': None,
                'DB_EVENT_CHECK_SLEEP': None,
                'JAILTIME': None
            }
        }

        for section, keys in required_values.items():
            if section not in self:
                raise Exception('Missing section [%s] in the config file' % section)

            for key, values in keys.items():
                if key not in self[section] or self[section][key] == '':
                    raise Exception(('Missing value for %s under section [%s] in ' + 'the config file') % (key, section))

                if values:
                    if self[section][key] not in values:
                        raise Exception(('Invalid value for %s under section [%s] in ' + 'the config file') % (key, section))