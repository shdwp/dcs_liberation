from dcs.helicopters import helicopter_map

from ui.eventresultsmenu import *

from game import *
from game.event import *
from .styles import STYLES, RED


class EventMenu(Menu):
    scramble_entries = None  # type: typing.Dict[typing.Type[Task], typing.Dict[typing.Type[UnitType], typing.Tuple[Entry, Entry]]]
    ca_slot_entry = None  # type: Entry
    error_label = None  # type: Label
    awacs = None  # type: IntVar

    def __init__(self, window: Window, parent, game: Game, event: event.Event):
        super(EventMenu, self).__init__(window, parent, game)

        self.event = event
        self.scramble_entries = {k: {} for k in self.event.tasks}

        if self.event.attacker_name == self.game.player:
            self.base = self.event.departure_cp.base
        else:
            self.base = self.event.to_cp.base

        self.frame = self.window.right_pane
        self.awacs = IntVar()

    def display(self):
        self.window.clear_right_pane()
        row = 0

        def header(text, style="strong"):
            nonlocal row
            head = Frame(self.frame, **STYLES["header"])
            head.grid(row=row, column=0, sticky=N+EW, columnspan=8)
            Label(head, text=text, **STYLES[style]).grid()
            row += 1

        def label(text, _row=None, _column=None, columnspan=None, sticky=None):
            nonlocal row
            new_label = Label(self.frame, text=text, **STYLES["widget"])
            new_label.grid(row=_row and _row or row, column=_column and _column or 0, columnspan=columnspan, sticky=sticky)

            if _row is None:
                row += 1

            return new_label

        def scrable_row(task_type, unit_type, unit_count, client_slots: bool):
            nonlocal row
            Label(self.frame, text="{} ({})".format(db.unit_type_name(unit_type), unit_count), **STYLES["widget"]).grid(row=row, sticky=W)

            scramble_entry = Entry(self.frame, width=2)
            scramble_entry.grid(column=1, row=row, sticky=E, padx=5)
            scramble_entry.insert(0, "0")
            Button(self.frame, text="+", command=self.scramble_one(task_type, unit_type), **STYLES["btn-primary"]).grid(column=2, row=row)
            Button(self.frame, text="-", command=self.descramble_one(task_type, unit_type), **STYLES["btn-primary"]).grid(column=3, row=row, stick=W)

            if client_slots:
                client_entry = Entry(self.frame, width=2)
                client_entry.grid(column=4, row=row, sticky=E, padx=5)
                client_entry.insert(0, "0")
                Button(self.frame, text="+", command=self.client_plus_one(task_type, unit_type), **STYLES["btn-primary"]).grid(column=5, row=row)
                Button(self.frame, text="-", command=self.client_minus_one(task_type, unit_type), **STYLES["btn-primary"]).grid(column=6, row=row, stick=W, padx=5)
            else:
                client_entry = None

            self.scramble_entries[task_type][unit_type] = scramble_entry, client_entry

            row += 1

        # Header
        header("Mission Menu", "title")

        # Mission Description
        Label(self.frame, text="{}".format(self.event), **STYLES["mission-preview"]).grid(row=row, column=0, columnspan=8, sticky=S+EW, padx=5)
        row += 1
        Label(self.frame, text="{}".format(self.event.environment_settings.start_time), **STYLES["mission-time"]).grid(
            row=row,
            column=0,
            columnspan=8,
            sticky=S + EW,
            pady=5,
            padx=5
        )
        row += 1

        Label(self.frame, text="Amount", **STYLES["widget"]).grid(row=row, column=1, columnspan=3)
        Label(self.frame, text="Client slots", **STYLES["widget"]).grid(row=row, column=4, columnspan=3)
        row += 1

        for flight_task in self.event.tasks:
            header("{}:".format(self.event.flight_name(flight_task)))
            if flight_task == PinpointStrike:
                if not self.base.armor:
                    label("No units")
                for t, c in self.base.armor.items():
                    scrable_row(flight_task, t, c, client_slots=False)
            else:
                if not self.base.aircraft:
                    label("No units")
                for t, c in self.base.aircraft.items():
                    scrable_row(flight_task, t, c, client_slots=True)

        header("Support:")
        # Options
        awacs_enabled = self.game.budget >= AWACS_BUDGET_COST and NORMAL or DISABLED
        Label(self.frame, text="AWACS ({}m)".format(AWACS_BUDGET_COST), **STYLES["widget"]).grid(row=row, column=0, sticky=W, pady=5)
        Checkbutton(self.frame, var=self.awacs, state=awacs_enabled,  **STYLES["radiobutton"]).grid(row=row, column=4, sticky=E)
        row += 1

        Label(self.frame, text="Combined Arms Slots", **STYLES["widget"]).grid(row=row, sticky=W)
        self.ca_slot_entry = Entry(self.frame,  width=2)
        self.ca_slot_entry.insert(0, "0")
        self.ca_slot_entry.grid(column=3, row=row, sticky=E, padx=5)
        Button(self.frame, text="+", command=self.add_ca_slot, **STYLES["btn-primary"]).grid(column=4, row=row, padx=5, sticky=W)
        row += 1

        header("Ready?")
        self.error_label = label("", columnspan=4)
        self.error_label["fg"] = RED
        Button(self.frame, text="Commit", command=self.start, **STYLES["btn-primary"]).grid(column=0, row=row, sticky=E, padx=5, pady=(10,10))
        Button(self.frame, text="Back", command=self.dismiss, **STYLES["btn-warning"]).grid(column=3, row=row, sticky=E, padx=5, pady=(10,10))
        row += 1

    def scramble_half(self, task: typing.Type[UnitType], unit_type: UnitType) -> typing.Callable:
        def action():
            entry = self.scramble_entries[task][unit_type][0]  # type: Entry
            value = entry.get()

            total_units = self.base.total_units_of_type(unit_type)

            amount = int(value and value or "0")
            entry.delete(0, END)
            entry.insert(0, str(amount + int(math.ceil(total_units/2))))

        return action

    def scramble_one(self, task: typing.Type[UnitType], unit_type: UnitType) -> typing.Callable:
        def action():
            entry = self.scramble_entries[task][unit_type][0]  # type: Entry
            value = entry.get()

            total_units = self.base.total_units_of_type(unit_type)

            entry.delete(0, END)
            entry.insert(0, str(min(int(value) + 1, int(total_units))))

        return action

    def descramble_one(self, task: typing.Type[UnitType], unit_type: UnitType) -> typing.Callable:
        def action():
            entry = self.scramble_entries[task][unit_type][0]  # type: Entry
            value = entry.get()

            entry.delete(0, len(value))
            entry.insert(0, str(max(int(value) - 1, 0)))

        return action

    def add_ca_slot(self):
        value = self.ca_slot_entry.get()
        amount = int(value and value or "0")
        self.ca_slot_entry.delete(0, END)
        self.ca_slot_entry.insert(0, str(amount+1))

    def client_plus_one(self, task: typing.Type[Task], unit_type: UnitType) -> typing.Callable:
        def action():
            entry = self.scramble_entries[task][unit_type][1]  # type: Entry
            value = entry.get()
            amount = int(value and value or "0")
            entry.delete(0, END)
            entry.insert(0, str(amount+1))
        return action

    def client_minus_one(self, task: typing.Type[UnitType], unit_type: UnitType) -> typing.Callable:
        def action():
            entry = self.scramble_entries[task][unit_type][1]  # type: Entry
            value = entry.get()

            entry.delete(0, len(value))
            entry.insert(0, str(max(int(value) - 1, 0)))

        return action

    def start(self):
        if type(self.event) == UnitsDeliveryEvent:
            self.error_label["text"] = "You do not actually play a delivery mission"
            return
        if self.awacs.get() == 1:
            self.event.is_awacs_enabled = True
            self.game.awacs_expense_commit()
        else:
            self.event.is_awacs_enabled = False

        ca_slot_entry_value = self.ca_slot_entry.get()
        try:
            ca_slots = int(ca_slot_entry_value and ca_slot_entry_value or "0")
        except:
            ca_slots = 0
        self.event.ca_slots = ca_slots

        flights = {k: {} for k in self.event.tasks}  # type: db.TaskForceDict
        units_scramble_counts = {}  # type: typing.Dict[typing.Type[UnitType], int]
        tasks_scramble_counts = {}  # type: typing.Dict[typing.Type[Task], int]
        tasks_clients_counts = {}  # type: typing.Dict[typing.Type[Task], int]

        def dampen_count(for_task: typing.Type[Task], unit_type: typing.Type[UnitType], count: int) -> int:
            nonlocal units_scramble_counts
            total_count = self.base.total_units_of_type(unit_type)

            total_scrambled = units_scramble_counts.get(unit_type, 0)
            dampened_value = count if count + total_scrambled < total_count else total_count - total_scrambled
            units_scramble_counts[unit_type] = units_scramble_counts.get(unit_type, 0) + dampened_value

            return dampened_value

        for task_type, dict in self.scramble_entries.items():
            for unit_type, (count_entry, clients_entry) in dict.items():
                try:
                    count = int(count_entry.get())
                except:
                    count = 0

                try:
                    clients_count = int(clients_entry and clients_entry.get() or 0)
                except:
                    clients_count = 0

                dampened_count = dampen_count(task_type, unit_type, count)
                tasks_clients_counts[task_type] = tasks_clients_counts.get(task_type, 0) + clients_count
                tasks_scramble_counts[task_type] = tasks_scramble_counts.get(task_type, 0) + dampened_count

                flights[task_type][unit_type] = dampened_count, clients_count

        for task in self.event.ai_banned_tasks:
            if tasks_clients_counts.get(task, 0) == 0 and tasks_scramble_counts.get(task, 0) > 0:
                self.error_label["text"] = "Need at least one player in flight {}".format(self.event.flight_name(task))
                return

        for task in self.event.player_banned_tasks:
            if tasks_clients_counts.get(task, 0) != 0:
                self.error_label["text"] = "Players are not allowed on flight {}".format(self.event.flight_name(task))
                return

        if self.game.is_player_attack(self.event):
            if isinstance(self.event, FrontlineAttackEvent) or isinstance(self.event, FrontlinePatrolEvent):
                if self.event.from_cp.base.total_armor == 0:
                    self.error_label["text"] = "No ground vehicles available to attack!"
                    return

            self.event.player_attacking(flights)
        else:
            if isinstance(self.event, FrontlineAttackEvent) or isinstance(self.event, FrontlinePatrolEvent):
                if self.event.to_cp.base.total_armor == 0:
                    self.error_label["text"] = "No ground vehicles available to defend!"
                    return

            self.event.player_defending(flights)

        ignore_slots = [
            'Pinpoint Strike',
        ]
        slot_count = 0
        for flight_details in flights.items():
            if flight_details[0].name in ignore_slots:
                continue
            for flight in flight_details[1:]:
                for aircraft in flight.items():
                    slot_count += aircraft[1][0]
        if slot_count > len(self.game.theater.terrain.airports[self.event.from_cp.full_name].parking_slots):
            self.error_label["text"] = "You've assigned more aircraft ({}) than the airport has parking for ({})!".format(
                slot_count,
                len(self.game.theater.terrain.airports[self.event.from_cp.full_name].parking_slots)
            )
            return

        self.game.initiate_event(self.event)
        EventResultsMenu(self.window, self.parent, self.game, self.event).display()

