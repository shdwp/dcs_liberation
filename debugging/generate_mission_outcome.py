import dcs as pydcs


"""
This file reads the current liberation mission and generates a log file reporting a player having killed all the enemy
    ground units (static and vehicle)
The purpose is to permit easy debugging without having to actually go and fly missions

File isn't really created to be generic or anything, but atm I'm too lazy to update it
"""
mission = pydcs.Mission()

mission.load_file('C:\\users\\tim\\Saved Games\\DCS.openbeta\\Missions\\liberation_nextturn.miz')

# find the player
player_id = None
player_name = None
enemy_units = []

for country in mission.coalition['blue'].countries:
    for plane_group in mission.coalition['blue'].country(country).plane_group:
        for plane in plane_group.units:
            if plane.skill.name == 'Player':
                player_id = plane.id
                player_name = plane.name

# find enemy units
for country in mission.coalition['red'].countries:
    for unit_group in mission.coalition['red'].country(country).vehicle_group:
        for unit in unit_group.units:
            enemy_units.append(unit.id)
            print(unit.name, '|', unit.id)
    for unit_group in mission.coalition['red'].country(country).static_group:
        for unit in unit_group.units:
            if '|' in str(unit.name) and unit.type != 'big_smoke':
                enemy_units.append(unit.id)
                print(unit.name, '|', unit.id)

if not player_id:
    print("Unable to find player unit! giving up")
    exit(1)

if not enemy_units:
    print("Unable to find enemy unit! giving up")
    exit(2)

# generate the log
print(player_id)
print(sorted(enemy_units))

mission_lines = [
    'events =',
    '{',
    '\t[1] =',
    '\t{',
    '\t\ttype\t=\t"mission start",',
    '\t\tt\t=\t57600,',
    '\t}, -- end of [1]',
    '\t[2] =',
    '\t{',
    '\t\ttype\t=\t"under control",',
    '\t\tinitiatorPilotName\t=\t"Wrycu",',
    '\t\ttarget\t=\t"' + str(player_name) + '",',
    '\t\tt\t=\t57600,',
    '\t\ttargetMissionID\t=\t"' + str(player_id) + '",',
    '\t}, -- end of [2]',

]

# used to pick a subset of units instead of all of them
#enemy_units = enemy_units[0:2]

event_id = 3
for unit in enemy_units:
    mission_lines.append('\t[{}] ='.format(event_id))
    mission_lines.append('\t{')
    mission_lines.append('\t\tt\t=\t57601,')
    mission_lines.append('\t\ttype\t=\t"dead",')
    mission_lines.append('\t\tinitiatorMissionID\t=\t"{}",'.format(unit))
    mission_lines.append('\t}, -- end of [' + str(event_id) + ']')
    event_id += 1

mission_lines.append('} -- end of events')
mission_lines.append('callsign\t=\t"PyDCS"')
mission_lines.append('result\t=\t0')
mission_lines.append('world_state =')
mission_lines.append('{')
mission_lines.append('\t[1] =')
mission_lines.append('\t{')
mission_lines.append('\t\ty\t=\t1,')
mission_lines.append('\t\tx\t=\t1,')
mission_lines.append('\t\theading\t=\t0,')
mission_lines.append('\t\tunitId\t=\t{},'.format(player_id))
mission_lines.append('\t\tspeed\t=\t0,')
mission_lines.append('\t\tcoalition\t=\t"blue",')
mission_lines.append('\t\tcountry\t=\t2,')
mission_lines.append('\t\ttype\t=\t"A-10C",')
mission_lines.append('\t}, --end of [1]')
mission_lines.append('} -- end of world_state')
mission_lines.append('')

with open('C:\\users\\tim\\Saved Games\\DCS.openbeta\\\liberation_debriefings\\debrief.log', 'w') as f:
    for line in mission_lines:
        f.write(line + '\n')
