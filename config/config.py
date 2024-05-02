"""
This module encapsulates the reading and processing of the config file
/etc/sysmanage.yaml and provides callers with a mechanism to access the
various properties specified therein.
"""
import sys
import yaml

# Read/validate the configuration file
try:
    with open('sysmanage.yaml', 'r', encoding="utf-8") as file:
        config = yaml.safe_load(file)
        if not 'hostName' in config.keys():
            config['hostName'] = "localhost"
        if not 'apiPort' in config.keys():
            config['apiPort'] = 8000
        if not 'webPort' in config.keys():
            config['webPort'] = 8080
except yaml.YAMLError as exc:
    if hasattr(exc, 'problem_mark'):
        mark = exc.problem_mark
        print (f"Error reading sysmanage.yaml on line {mark.line+1} in column {mark.column+1}")
        sys.exit(1)

def get_config():
    """
    This function allows a caller to retrieve the config object.
    """
    return config
