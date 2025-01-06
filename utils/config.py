import os
import yaml


def get_config():
    env = os.getenv('ENV', 'prod')
    config_path = os.path.join(os.path.dirname('__file__'), 'res', env, 'application.yml')
    with open(config_path, 'r') as file:
        config_data = yaml.safe_load(file)
        config_data['env'] = env
    return config_data


config = get_config()
