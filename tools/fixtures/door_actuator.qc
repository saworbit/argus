// PRIVATE target-chain contracts. No motor or route state is scripted.
float da_done, da_checks, da_ok, da_havetarget;

// INSERT_DOOR_DECISION

void(string label, float ok) DoorActuatorCheck =
{
    da_checks = da_checks + 1;
    if (!ok) da_ok = 0;
    dprint ("DAFIX check "); dprint (label); dprint (" "); dprint (ftos (ok)); dprint ("\n");
};

entity(string kind, string output_name, string input_name, vector at) DoorActuatorEntity =
{
    local entity e;
    e = spawn (); e.classname = kind; e.target = output_name; e.targetname = input_name;
    e.movetype = MOVETYPE_NONE; e.solid = SOLID_NOT;
    setsize (e, '-8 -8 -8', '8 8 8'); setorigin (e, at);
    return e;
};

void() DoorActuatorFixture =
{
    local entity saved, b, door, relay, button, link, cycle, goal;
    local vector seat, point;
    local float before, after;
    if (da_done || time < 1) return;
    da_done = 1; da_ok = 1;
    dprint ("BHVRPL begin door_actuator\nDAFIX begin "); dprint (mapname); dprint ("\n");
    seat = '-96 288 320';
    if (mapname == "dm2") seat = '2209 -279 24';
    before = 0; b = nextent (world);
    while (b != world) { before = before + 1; b = nextent (b); }
    saved = self; b = spawn (); self = b;
    self.classname = "door_actuator_fixture"; self.ar_isbot = 1;
    self.health = 100; self.solid = SOLID_NOT; self.movetype = MOVETYPE_NONE;
    setsize (self, '-16 -16 -24', '16 16 32'); setorigin (self, seat);
    door = DoorActuatorEntity ("door", "", "dafix_door", seat);
    button = DoorActuatorEntity ("func_button", "dafix_door", "", seat + '64 0 0');
    Argus_TakeDoor (door);
    DoorActuatorCheck ("direct_button", self.ar_doorbtn == button);
    setorigin (button, seat); button.state = STATE_BOTTOM;
    DoorActuatorCheck ("button_needs_activation", !Argus_DoorPressed (button));
    button.state = STATE_UP;
    DoorActuatorCheck ("moving_button_acknowledged", Argus_DoorPressed (button));
    button.state = STATE_TOP;
    DoorActuatorCheck ("latched_button_acknowledged", Argus_DoorPressed (button));
    button.classname = "trigger_multiple";
    button.state = STATE_BOTTOM;
    DoorActuatorCheck ("trigger_overlap_preserved", Argus_DoorPressed (button));
    setorigin (button, seat);
    point = UseStandPoint (button);
    dprint ("DAGEOM stand "); dprint (vtos (point)); dprint (" seat "); dprint (vtos (seat)); dprint ("\n");
    DoorActuatorCheck ("touch_point_premise", ar_standok
        && pointcontents (point) != CONTENT_SOLID && fabs (point_z - seat_z) <= 24);
    Argus_TakeDoor (door);
    DoorActuatorCheck ("direct_touch_trigger", self.ar_doorbtn == button);
    button.spawnflags = 1;
    Argus_TakeDoor (door);
    DoorActuatorCheck ("notouch_is_not_a_touch_target", self.ar_doorbtn == world);
    button.spawnflags = 0; button.classname = "func_button";
    setorigin (button, seat + '64 0 0');
    button.target = "dafix_relay";
    relay = DoorActuatorEntity ("trigger_once", "dafix_door", "dafix_relay", seat + '0 0 224');
    Argus_TakeDoor (door);
    DoorActuatorCheck ("ceiling_relay_uses_floor_button", self.ar_doorbtn == button);
    relay.classname = "trigger_relay";
    Argus_TakeDoor (door);
    DoorActuatorCheck ("logical_relay_uses_button", self.ar_doorbtn == button);
    link = DoorActuatorEntity ("trigger_relay", "dafix_relay", "dafix_link", seat);
    button.target = "dafix_link";
    Argus_TakeDoor (door);
    DoorActuatorCheck ("two_relays", self.ar_doorbtn == button);
    button.health = 10;
    Argus_TakeDoor (door);
    DoorActuatorCheck ("shoot_button_preserved", self.ar_doorbtn == button);
    button.health = 0; button.target = "dafix_unused";
    cycle = DoorActuatorEntity ("trigger_relay", "dafix_link", "dafix_relay", seat);
    Argus_TakeDoor (door);
    DoorActuatorCheck ("cycle_is_bounded", self.ar_doorbtn == world);
    cycle.target = "dafix_unused";
    button.target = "dafix_link"; setorigin (button, seat + '1500 0 0');
    Argus_TakeDoor (door);
    DoorActuatorCheck ("range_cap", self.ar_doorbtn == world);
    DoorActuatorCheck ("ownership_unchanged", self.ar_door == door && self.origin == seat && self.health == 100);
    door.state = STATE_UP; door.pos1 = door.origin;
    DoorActuatorCheck ("opening_near_waits", Argus_DoorOpeningWait (door, seat + '0 128 0'));
    setorigin (door, seat + '0 512 0'); door.pos1 = door.origin;
    DoorActuatorCheck ("opening_remote_walks", !Argus_DoorOpeningWait (door, seat + '0 768 0'));
    setorigin (door, seat); door.pos1 = door.origin;
    setorigin (self, seat + '0 64 0');
    DoorActuatorCheck ("opening_already_past_walks", !Argus_DoorOpeningWait (door, seat + '0 128 0'));
    setorigin (self, seat);
    door.state = STATE_TOP;
    DoorActuatorCheck ("fully_open_walks", !Argus_DoorOpeningWait (door, seat + '0 128 0'));
    door.state = STATE_DOWN;
    DoorActuatorCheck ("closing_handling_preserved", !Argus_DoorOpeningWait (door, seat + '0 128 0'));
    goal = DoorActuatorEntity ("door_fixture_goal", "", "", seat + '0 128 0');
    goal.solid = SOLID_TRIGGER;
    self.ar_goal = goal; self.ar_door = door; self.ar_doorbtn = button;
    self.ar_liftwait = 0; self.ar_doortime = time + 1; door.state = STATE_UP;
    DoorDecision (goal.origin);
    DoorActuatorCheck ("opening_ack_starts_bounded_phase", self.ar_door == door
        && self.ar_doorbtn == world && self.ar_liftwait && self.ar_goal == goal
        && self.ar_doortime == time + 8);
    self.ar_liftwait = 0; self.ar_doortime = time + 3;
    DoorDecision (goal.origin);
    DoorActuatorCheck ("opening_clock_not_rearmed", self.ar_door == door
        && self.ar_liftwait && self.ar_doortime == time + 3);
    self.ar_liftwait = 0; self.ar_doortime = time - 0.1;
    DoorDecision (goal.origin);
    DoorActuatorCheck ("opening_timeout_releases", self.ar_door == world
        && goal.ar_failtime == time && !self.ar_liftwait && !da_havetarget);
    self.ar_goal = goal; self.ar_door = door; self.ar_liftwait = 0;
    door.state = STATE_TOP;
    DoorDecision (goal.origin);
    DoorActuatorCheck ("open_release_preserves_goal", self.ar_door == world
        && self.ar_goal == goal && !self.ar_liftwait);
    self = saved; remove (b); remove (door); remove (relay); remove (button); remove (link); remove (cycle); remove (goal);
    after = 0; b = nextent (world);
    while (b != world) { after = after + 1; b = nextent (b); }
    DoorActuatorCheck ("cleanup", before == after);
    dprint ("DAFIX end checks "); dprint (ftos (da_checks));
    dprint (" ok "); dprint (ftos (da_ok)); dprint ("\n");
};
