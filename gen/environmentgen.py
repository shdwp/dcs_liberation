import logging
import typing
import random
from datetime import datetime, timedelta, time

from dcs.mission import Mission
from dcs.triggers import *
from dcs.condition import *
from dcs.action import *
from dcs.unit import Skill
from dcs.point import MovingPoint, PointProperties
from dcs.action import *
from dcs.weather import *

from game import db
from theater import *
from gen import *

WEATHER_CLOUD_BASE = 2000, 3000
WEATHER_CLOUD_DENSITY = 1, 8
WEATHER_CLOUD_THICKNESS = 100, 400
WEATHER_CLOUD_BASE_MIN = 1600

WEATHER_FOG_CHANCE = 20
WEATHER_FOG_VISIBILITY = 2500, 5000
WEATHER_FOG_THICKNESS = 100, 500

RANDOM_TIME = {
    "night": 7,  # chosen by a fair dice roll. guaranteed to be random.
    "dusk": 40,
    "dawn": 40,
    "day": 100,
}

DAY_TIME_MAP = {
    'dawn': (6, 8),
    'day': (8, 16),
    'dusk': (16, 18),
    'night': (0, 5),
}

RANDOM_WEATHER = {
    1: 0,  # thunderstorm
    2: 20,  # rain
    3: 80,  # clouds
    4: 100,  # clear
}


class EnvironmentSettings:
    weather_dict = None
    start_time = None


class EnviromentGenerator:
    def __init__(self, mission: Mission, conflict: Conflict, game):
        self.mission = mission
        self.conflict = conflict
        self.game = game

    def _gen_random_time(self):
        self._set_time(_gen_random_time(self.game.settings.night_disabled)['start_time'])

    def _set_time(self, the_time):
        self.mission.start_time = the_time

    def _generate_wind(self, wind_speed, wind_direction=None):
        self._set_wind(_generate_wind(wind_speed, wind_direction))

    def _set_wind(self, wind):
        self.mission.weather.wind_at_ground = Wind(wind['atGround']['dir'], wind['atGround']['speed'])
        self.mission.weather.wind_at_2000 = Wind(wind['at2000']['dir'], wind['at2000']['speed'])
        self.mission.weather.wind_at_8000 = Wind(wind['at8000']['dir'], wind['at8000']['speed'])

    def _generate_base_weather(self):
        self._set_base_weather(_generate_base_weather())

    def _set_base_weather(self, weather):
        # clouds
        if 'base' in weather['clouds']:
            self.mission.weather.clouds_base = weather['clouds']['base']
        if 'density' in weather['clouds']:
            self.mission.weather.clouds_density = weather['clouds']['density']
        if 'thickness' in weather['clouds']:
            self.mission.weather.clouds_thickness = weather['clouds']['thickness']
        # winds
        self._set_wind(weather['wind'])
        # fog
        if 'fog' in weather and 'visibility' in weather['fog'] and 'thickness' in weather['fog']:
            self.mission.weather.fog_visibility = weather['fog']['visibility']
            self.mission.weather.fog_thickness = weather['fog']['thickness']

    def _gen_random_weather(self):
        for k, v in RANDOM_WEATHER.items():
            if random.randint(0, 100) <= v:
                weather_type = k
                break

        weather = _gen_random_weather(weather_type)
        self._set_base_weather(weather)

        logging.info("generated weather {}".format(weather_type))
        if weather_type == 1:
            # thunderstorm
            self.mission.weather.clouds_iprecptns = Weather.Preceptions.Thunderstorm
        elif weather_type == 2:
            # rain
            self.mission.weather.clouds_iprecptns = Weather.Preceptions.Rain

    def generate(self) -> EnvironmentSettings:
        self._gen_random_time()
        self._gen_random_weather()

        settings = EnvironmentSettings()
        settings.start_time = self.mission.start_time
        settings.weather_dict = self.mission.weather.dict()
        return settings

    def load(self, settings: EnvironmentSettings):
        self.mission.start_time = settings.start_time
        self.mission.weather.load_from_dict(settings.weather_dict)


def _gen_random_time(night_disabled=False):
    start_time = datetime.strptime('May 25 2018 12:00AM', '%b %d %Y %I:%M%p')

    time_range = None
    for k, v in RANDOM_TIME.items():
        if night_disabled and k == "night":
            continue

        if random.randint(0, 100) <= v:
            time_range = DAY_TIME_MAP[k]
            break

    start_time += timedelta(hours=random.randint(*time_range))
    logging.info("time - {}, slot - {}, night skipped - {}".format(
        str(start_time),
        str(time_range),
        night_disabled))
    return {'start_time': start_time}


def _generate_wind(wind_speed, wind_direction=None):
    # wind
    if not wind_direction:
        wind_direction = random.randint(0, 360)

    return {
        'atGround': Wind(wind_direction, wind_speed).dict(),
        'at2000': Wind(wind_direction, wind_speed * 2).dict(),
        'at8000': Wind(wind_direction, wind_speed * 3).dict(),
    }


def _generate_base_weather():
    data = {
        'clouds': {
            'base': random.randint(*WEATHER_CLOUD_BASE),
            'density': random.randint(*WEATHER_CLOUD_DENSITY),
            'thickness': random.randint(*WEATHER_CLOUD_THICKNESS),
        },
        'wind': _generate_wind(random.randint(0, 4)),
        'fog': {}
    }

    # fog
    if random.randint(0, 100) < WEATHER_FOG_CHANCE:
        data['fog']['visibility'] = random.randint(*WEATHER_FOG_VISIBILITY)
        data['fog']['thickness'] = random.randint(*WEATHER_FOG_THICKNESS)
    return data


def _gen_random_weather(weather_type=None):
    data = {
        'clouds': {},
    }
    if not weather_type:
        for k, v in RANDOM_WEATHER.items():
            if random.randint(0, 100) <= v:
                weather_type = k
                break

    logging.info("generated weather {}".format(weather_type))
    if weather_type == 1:
        # thunderstorm
        data = _generate_base_weather()
        data['wind'] = _generate_wind(random.randint(8, 12))
        data['clouds']['density'] = random.randint(9, 10)
        data['clouds']['iprecptns'] = Weather.Preceptions.Thunderstorm
    elif weather_type == 2:
        # rain
        data = _generate_base_weather()
        data['wind'] = _generate_wind(random.randint(4, 8))
        data['clouds']['density'] = random.randint(5, 8)
        data['clouds']['iprecptns'] = Weather.Preceptions.Rain
    elif weather_type == 3:
        # clouds
        data = _generate_base_weather()
    elif weather_type == 4:
        # clear
        # front line smokes look silly w/o any wind
        data['wind'] = _generate_wind(1)

    if 'density' in data['clouds']:
        # sometimes clouds are randomized way too low and need to be fixed
        data['clouds']['base'] = max(data['clouds']['base'], WEATHER_CLOUD_BASE_MIN)
    return data


def generate():
    settings = EnvironmentSettings()
    settings.start_time = _gen_random_time()['start_time']
    settings.weather_dict = _gen_random_weather()
    return settings
