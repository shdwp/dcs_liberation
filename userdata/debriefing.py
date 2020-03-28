import logging
import typing
import re
import threading
import time
import os

from dcs.lua import parse
from dcs.mission import Mission

from dcs.unit import Vehicle, Ship
from dcs.vehicles import vehicle_map
from dcs.ships import ship_map
from dcs.planes import plane_map
from dcs.unit import UnitType

from game import db

from .persistency import base_path
from theater.theatergroundobject import CATEGORY_MAP

DEBRIEFING_LOG_EXTENSION = "log"


def parse_mutliplayer_debriefing(contents: str):
    result = {}
    element = None

    in_events = False

    for line in [x.strip() for x in contents.splitlines()]:
        if line.startswith("events ="):
            in_events = True
        elif line.startswith("} -- end of events"):
            in_events = False

        if not in_events:
            continue

        key = None
        if line.startswith("initiator\t"):
            key = "initiator"
            if element is None:
                element = {}
        elif line.startswith("initiatorMissionID\t"):
            key = "initiatorMissionID"
            if element is None:
                element = {}
        elif line.startswith("type\t"):
            key = "type"
            if element is None:
                element = {}
        elif line.startswith("}, -- end of ["):
            result[len(result)] = element
            element = None
            continue
        else:
            continue

        value = re.findall(r"=\s*\"(.*?)\",", line)[0]
        element[key] = value

    return {"debriefing": {"events": result}}


class Debriefing:
    def __init__(self, dead_units, trigger_state):
        self.destroyed_units = {}  # type: typing.Dict[str, typing.Dict[UnitType, int]]
        self.alive_units = {}  # type: typing.Dict[str, typing.Dict[UnitType, int]]
        self.destroyed_objects = []  # type: typing.List[str]

        self._trigger_state = trigger_state
        self._dead_units = dead_units

    @classmethod
    def parse(cls, path: str):
        dead_units = []

        def append_dead_object(object_mission_id_str):
            nonlocal dead_units
            object_mission_id = int(object_mission_id_str)
            if object_mission_id in dead_units:
                logging.error("debriefing: failed to append_dead_object {}: already exists!".format(object_mission_id))
                return

            dead_units.append(object_mission_id)

        def parse_dead_object(event):
            try:
                append_dead_object(event["initiatorMissionID"])
            except KeyError:
                try:
                    append_dead_object([x['initiatorMissionID'] for x in event.values() if 'initiatorMissionID' in x][0])
                except Exception as e:
                    logging.error(e)
            except Exception as e:
                logging.error(e)

        with open(path, "r") as f:
            table_string = f.read()
            try:
                table = parse.loads(table_string)
            except Exception as e:
                table = parse_mutliplayer_debriefing(table_string)

            try:
                events = table["debriefing"].get("events", {})
            except KeyError:
                events = table.get('events', {})
            for event in events.values():
                try:
                    event_type = event["type"]
                except KeyError:
                    # this means we've encountered a different version of the parsed debrief.  This means we must search
                    # for the key we want :|
                    try:
                        event_type = [x['type'] for x in event.values() if 'type' in x][0]
                    except Exception as e:
                        print("Failed to parse event - {} ({})".format(event, e))
                if event_type in ["crash", "dead"]:
                    parse_dead_object(event)

            trigger_state = table.get("debriefing", {}).get("triggers_state", {})

        return Debriefing(dead_units, trigger_state)

    def calculate_units(self, regular_mission: Mission, quick_mission: Mission, player_name: str, enemy_name: str):
        def count_groups(groups: typing.List[UnitType]) -> typing.Dict[UnitType, int]:
            result = {}
            for group in groups:
                for unit in group.units:
                    unit_type = db.unit_type_of(unit)
                    if unit_type in db.EXTRA_AA.values():
                        continue

                    result[unit_type] = result.get(unit_type, 0) + 1

            return result

        mission = regular_mission if len(self._trigger_state) else quick_mission

        player = mission.country(player_name)
        enemy = mission.country(enemy_name)

        player_units = count_groups(player.plane_group + player.vehicle_group + player.ship_group)
        enemy_units = count_groups(enemy.plane_group + enemy.vehicle_group + enemy.ship_group)

        self.destroyed_units = {
            player.name: {},
            enemy.name: {},
        }

        all_groups = {
            player.name: player.plane_group + player.helicopter_group + player.vehicle_group + player.ship_group,
            enemy.name: enemy.plane_group + enemy.helicopter_group + enemy.vehicle_group + enemy.ship_group,
        }

        static_groups = enemy.static_group

        for country_name, country_groups in all_groups.items():
            for group in country_groups:
                for unit in group.units:
                    if unit.id in self._dead_units:
                        unit_type = db.unit_type_of(unit)
                        logging.info("debriefing: found dead unit {} ({}, {})".format(str(unit.name), unit.id, unit_type))

                        assert country_name
                        assert unit_type
                        self.destroyed_units[country_name][unit_type] = self.destroyed_units[country_name].get(unit_type, 0) + 1
                        self._dead_units.remove(unit.id)

        for group in static_groups:
            identifier = group.units[0].id
            if identifier in self._dead_units and group.units[0].type != 'big_smoke':
                logging.info("debriefing: found dead static {} ({})".format(str(group.name), identifier))

                assert str(group.name)
                self.destroyed_objects.append(str(group.name))
                self._dead_units.remove(identifier)

        logging.info("debriefing: unsatistied ids: {}".format(self._dead_units))

        self.alive_units = {
            player.name: {k: v - self.destroyed_units[player.name].get(k, 0) for k, v in player_units.items()},
            enemy.name: {k: v - self.destroyed_units[enemy.name].get(k, 0) for k, v in enemy_units.items()},
        }


def debriefing_directory_location() -> str:
    return os.path.join(base_path(), "liberation_debriefings")


def _logfiles_snapshot() -> typing.Dict[str, float]:
    result = {}
    for file in os.listdir(debriefing_directory_location()):
        fullpath = os.path.join(debriefing_directory_location(), file)
        result[file] = os.path.getmtime(fullpath)

    return result


def _poll_new_debriefing_log(snapshot: typing.Dict[str, float], callback: typing.Callable):
    should_run = True
    while should_run:
        for file, timestamp in _logfiles_snapshot().items():
            if file not in snapshot or timestamp != snapshot[file]:
                debriefing = Debriefing.parse(os.path.join(debriefing_directory_location(), file))
                callback(debriefing)
                should_run = False
                break

        time.sleep(3)


def wait_for_debriefing(callback: typing.Callable):
    if not os.path.exists(debriefing_directory_location()):
        os.mkdir(debriefing_directory_location())

    threading.Thread(target=_poll_new_debriefing_log, args=(_logfiles_snapshot(), callback)).start()

