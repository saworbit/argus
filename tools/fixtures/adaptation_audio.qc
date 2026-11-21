// Stock-map witnesses retained from the hearing and portal study.
float af_done;
void() player_nail2;
void() player_light2;
extern entity s;

void(string name, float ok) AfCheck =
{
    dprint ("AUDIOFIX "); dprint (name); dprint (" ");
    dprint (ftos (ok)); dprint ("\n");
};

void(entity jacket, entity actor) AfPickup =
{
    local entity saved, savedother;
    saved = self;
    savedother = other;
    actor.armorvalue = 0;
    actor.armortype = 0;
    jacket.solid = SOLID_TRIGGER;
    self = jacket;
    other = actor;
    armor_touch ();
    self = saved;
    other = savedother;
};

void(float held) AfEquip =
{
    self.weapon = held;
    self.items = IT_AXE | IT_LIGHTNING | IT_SHOTGUN | IT_SUPER_SHOTGUN
                 | IT_NAILGUN | IT_SUPER_NAILGUN;
    self.ammo_cells = 12;
    self.ammo_shells = 10;
    self.ammo_nails = 10;
    self.waterlevel = 0;
    self.watertype = CONTENT_EMPTY;
    self.v_angle = '0 90 0';
    W_SetCurrentAmmo ();
};

void() AfLoadedSwitches =
{
    local float i, crossed, cells;
    local vector dry;

    AfEquip (IT_SHOTGUN);
    self.items = self.items | IT_ROCKET_LAUNCHER | IT_GRENADE_LAUNCHER;
    self.ammo_rockets = 8;
    self.ammo_cells = 0;
    Argus_SelectWeapon (229, 180);
    self.button0 = 1;
    W_Attack ();
    AfCheck ("loaded_nailgun_fires_below_splash_band", self.weapon == IT_SUPER_NAILGUN
             && self.ammo_nails == 8 && self.think == player_nail2);
    self.ar_fireweapon = IT_SUPER_NAILGUN;
    self.ar_fireburst = time + 1;
    Argus_SelectWeapon (231, 180);
    AfCheck ("splash_crossing_cancels_outgoing_nail_chain", self.weapon == IT_ROCKET_LAUNCHER
             && self.think != player_nail2 && !self.ar_fireweapon && !self.ar_fireburst && !self.button0);

    crossed = 1;
    i = 0;
    while (i < 3)
    {
        Argus_SelectWeapon (229, 180);
        if (self.weapon != IT_SUPER_NAILGUN) crossed = 0;
        Argus_SelectWeapon (231, 180);
        if (self.weapon != IT_ROCKET_LAUNCHER) crossed = 0;
        i = i + 1;
    }
    AfCheck ("loaded_switches_follow_repeated_splash_crossings", crossed);

    self.ammo_nails = 1;
    Argus_SelectWeapon (229, 180);
    W_Attack ();
    AfCheck ("nail_depletion_selects_a_firing_shotgun", self.weapon == IT_SUPER_SHOTGUN
             && self.ammo_shells == 8 && self.ammo_nails == 1);
    self.items = self.items - (self.items & IT_ROCKET_LAUNCHER);
    Argus_SelectWeapon (231, 180);
    W_Attack ();
    AfCheck ("grenade_launcher_fires_when_rockets_are_unavailable", self.weapon == IT_GRENADE_LAUNCHER
             && self.ammo_rockets == 7);

    self.items = self.items | IT_ROCKET_LAUNCHER;
    self.ammo_cells = 4;
    Argus_SelectWeapon (479, 180);
    self.button0 = 1;
    W_Attack ();
    self.ar_fireweapon = IT_LIGHTNING;
    self.ar_fireburst = time - 0.05;
    Argus_SelectWeapon (490, 180);
    AfCheck ("expired_beam_releases_to_loaded_rockets", self.weapon == IT_ROCKET_LAUNCHER
             && self.ammo_cells == 3 && self.think != player_light2 && !self.ar_fireweapon);

    Argus_SelectWeapon (200, 180);
    self.button0 = 1;
    W_Attack ();
    self.ar_fireweapon = IT_LIGHTNING;
    self.ar_fireburst = time + 1;
    cells = self.ammo_cells;
    dry = self.origin;
    setsize (self, '-16 -16 -24', '16 16 32');
    if (mapname == "dm2") setorigin (self, '1297 -1063 33');
    else setorigin (self, '433 -1087 -239');
    self.watertype = pointcontents (self.origin);
    self.ar_wetlevel = Argus_Waterlevel ();
    self.waterlevel = self.ar_wetlevel;
    Argus_SelectWeapon (200, 180);
    W_Attack ();
    AfCheck ("water_entry_cancels_lightning_and_fires_safe_fallback", self.ar_wetlevel > 1
             && self.weapon == IT_SUPER_SHOTGUN && self.ammo_shells == 6
             && self.ammo_cells == cells && self.think != player_light2 && !self.ar_fireweapon);
    setorigin (self, dry);
    self.watertype = CONTENT_EMPTY;
    self.ar_wetlevel = 0;
    self.waterlevel = 0;
};

void(vector position, float weaponbit, float age) AfMemory =
{
    self.ar_sndpos = position;
    self.ar_sndtime = time - age;
    self.ar_sndweap = weaponbit;
    self.ar_sndspent = 0;
};

entity(string key) AfGate =
{
    local entity gate;
    gate = find (world, classname, "trigger_teleport");
    while (gate != world && gate.target != key)
        gate = find (gate, classname, "trigger_teleport");
    return gate;
};

void(entity gate, entity rider) AfWarp =
{
    local entity saved, savedother;
    saved = self;
    savedother = other;
    setorigin (rider, (gate.absmin + gate.absmax) * 0.5);
    self = gate;
    other = rider;
    gate.touch ();
    self = saved;
    other = savedother;
};

void(entity listener, entity rider, entity gate) AfTeleportCue =
{
    local entity saved, fog;
    local vector soundpos;

    saved = self;
    listener.ar_sndtime = 0;
    listener.ar_sndweap = 0;
    AfWarp (gate, rider);
    fog = s;
    soundpos = fog.origin;
    setorigin (listener, soundpos + '0 0 24');
    AfCheck ("warp_waits_for_audible_playback", listener.ar_sndtime == 0);
    self = fog;
    self.think ();
    AfCheck ("warp_exit_is_a_neutral_audible_cue",
             listener.ar_sndtime == time && listener.ar_sndpos == soundpos
             && listener.ar_sndent == rider && listener.ar_sndweap == 0);

    listener.ar_sndweap = IT_LIGHTNING;
    AfWarp (gate, rider);
    self = s;
    self.think ();
    AfCheck ("warp_respects_recent_shot_priority", listener.ar_sndweap == IT_LIGHTNING);
    self = saved;
};

void() AfStraightFlight =
{
    local vector offset;
    local float flight;

    offset = '400 0 0';
    flight = Argus_StraightFlight (offset, '320 0 0', 0.4);
    AfCheck ("receding_target_lead", fabs (flight - 400 / 680) < 0.025);
    flight = Argus_StraightFlight (offset, '-320 0 0', 0.4);
    AfCheck ("closing_target_lead", fabs (flight - 400 / 1320) < 0.015);
    flight = Argus_StraightFlight (offset, '0 320 0', 0.4);
    AfCheck ("crossing_target_lead", fabs (flight - 0.4222) < 0.006);
    AfCheck ("extreme_speed_retains_legacy_lead",
             Argus_StraightFlight (offset, '0 600 0', 0.4) == 0.4);
};

void() AfFixture =
{
    local entity saved, listener, actor, roster, jacket;
    local entity gatea, gateb, landa, landb, entrya, entryb, to_a, to_b;
    local float bit_a, bit_b, learned, previous;
    local vector source, corner, openleg;
    local string firstkey, secondkey;

    if (af_done || time < 1.55 || cvar ("scratch2") != 2517) return;
    if (mapname != "dm2" && mapname != "dm6") return;
    af_done = 1;
    dprint ("BHVRPL begin adaptation\n");
    AfStraightFlight ();
    saved = self;
    roster = argus_bots;
    listener = spawn ();
    listener.classname = "player";
    listener.netname = "fixture listener";
    listener.ar_slot = 3;
    listener.ar_isbot = 1;
    self = listener;
    Argus_BaseStats ();
    listener.ar_skill = 1;
    listener.flags = FL_ONGROUND;
    actor = spawn ();
    actor.classname = "player";
    actor.ar_isbot = 1;
    actor.health = 100;
    argus_bots = listener;

    if (mapname == "dm2")
    {
        source = '1313 -535 184';
        openleg = '1409 -535 184';
        corner = '1473 -695 184';
    }
    else
    {
        source = '129 -911 136';
        openleg = '97 -783 136';
        corner = '225 -751 136';
    }
    setorigin (listener, source);
    setorigin (actor, source + '64 0 0');
    jacket = spawn ();
    jacket.classname = "item_armor1";
    setorigin (jacket, source + '88 0 0');
    self = actor;
    AfEquip (IT_LIGHTNING);
    AfPickup (jacket, actor);
    AfCheck ("real_pickup_is_audible", actor.armorvalue == 100
             && listener.ar_sndtime == time && listener.ar_sndpos == jacket.origin);
    AfCheck ("pickup_has_no_weapon_class", listener.ar_sndweap == 0);
    W_Attack ();
    AfCheck ("lightning_start_is_audible", listener.ar_sndweap == IT_LIGHTNING
             && listener.ar_sndpos == actor.origin && listener.ar_sndtime == time);
    AfPickup (jacket, actor);
    AfCheck ("pickup_yields_to_fresh_shot", listener.ar_sndweap == IT_LIGHTNING
             && listener.ar_sndpos == actor.origin);
    listener.ar_sndtime = time - 0.65;
    AfPickup (jacket, actor);
    AfCheck ("pickup_replaces_older_shot", listener.ar_sndweap == 0
             && listener.ar_sndpos == jacket.origin && listener.ar_sndtime == time);

    AfEquip (IT_SUPER_SHOTGUN);
    self.ammo_shells = 1;
    W_SetCurrentAmmo ();
    W_Attack ();
    AfCheck ("one_shell_sounds_like_single_shotgun", listener.ar_sndweap == IT_SHOTGUN
             && self.ammo_shells == 0);
    AfEquip (IT_SUPER_SHOTGUN);
    W_Attack ();
    AfCheck ("two_shells_sound_like_double_shotgun", listener.ar_sndweap == IT_SUPER_SHOTGUN
             && self.ammo_shells == 8);
    AfEquip (IT_SUPER_NAILGUN);
    self.button0 = 1;
    previous = time - 0.3;
    listener.ar_sndtime = previous;
    player_nail1 ();
    AfCheck ("continuing_super_nail_fire_is_audible", listener.ar_sndweap == IT_SUPER_NAILGUN
             && listener.ar_sndtime == time && self.ammo_nails == 8);
    self.ammo_nails = 1;
    self.think ();
    AfCheck ("one_nail_sounds_like_single_nailgun", listener.ar_sndweap == IT_NAILGUN
             && self.ammo_nails == 0);
    listener.ar_sndtime = previous;
    player_nail1 ();
    AfCheck ("empty_nail_frame_is_silent", listener.ar_sndtime == previous);
    AfEquip (IT_LIGHTNING);
    self.button0 = 1;
    self.t_width = 0;
    player_light1 ();
    AfCheck ("continuing_lightning_is_audible", listener.ar_sndweap == IT_LIGHTNING
             && listener.ar_sndtime == time && self.ammo_cells == 11);
    listener.ar_sndtime = previous;
    self.think ();
    AfCheck ("lightning_cue_respects_sound_clock", listener.ar_sndtime == previous);
    AfLoadedSwitches ();
    self = listener;
    Argus_BaseStats ();
    AfCheck ("a_new_life_discards_hearing", !self.ar_sndtime && !self.ar_sndweap
             && self.ar_sndpos == '0 0 0' && self.ar_sndent == world);
    listener.ar_skill = 1;
    listener.flags = FL_ONGROUND;
    listener.ar_goal = jacket;

    {
        AfMemory (openleg, IT_LIGHTNING, 0.2);
        AfCheck ("open_floor_keeps_direct_investigation", Argus_InvestigateNoise ()
                 && listener.ar_goal == jacket);
        AfMemory (corner, IT_ROCKET_LAUNCHER, 0.2);
        AfCheck ("near_fresh_shot_can_round_corner", Argus_InvestigateNoise ()
                 && listener.ar_goal == jacket);
        AfMemory (corner, 0, 0.2);
        AfCheck ("pickup_does_not_draw_corner_detour", !Argus_InvestigateNoise ());
        AfMemory (corner, IT_ROCKET_LAUNCHER, 1.3);
        AfCheck ("old_shot_does_not_draw_corner_detour", !Argus_InvestigateNoise ());
        AfMemory (corner, IT_ROCKET_LAUNCHER, 0.2);
        listener.ar_hoptrain = 1;
        AfCheck ("investigation_preserves_mover_commitment", !Argus_InvestigateNoise ());
        listener.ar_hoptrain = 0;
        listener.ar_skill = 0;
        AfCheck ("slow_tier_glances_without_chasing", !Argus_InvestigateNoise ());
        listener.ar_skill = 1;
        AfMemory (source + '40 0 0', IT_LIGHTNING, 0.2);
        learned = !Argus_InvestigateNoise ();
        setorigin (listener, source - '60 0 0');
        AfCheck ("arrival_spends_movement_cue_but_keeps_sound",
                 learned && self.ar_sndspent && listener.ar_sndtime > 0 && !Argus_InvestigateNoise ());
        setorigin (listener, source);
    }

    if (mapname == "dm6")
    {
        firstkey = "t2";
        secondkey = "t3";
        gatea = AfGate (firstkey);
        gateb = AfGate (secondkey);
        landa = find (world, targetname, firstkey);
        landb = find (world, targetname, secondkey);
        entrya = Argus_TeleSeat ((gatea.absmin + gatea.absmax) * 0.5);
        entryb = Argus_TeleSeat ((gateb.absmin + gateb.absmax) * 0.5);
        to_a = Argus_TeleSeat (landa.origin - '0 0 27');
        to_b = Argus_TeleSeat (landb.origin - '0 0 27');
        bit_a = Argus_NavGetLinkBit (entrya, to_a);
        bit_b = Argus_NavGetLinkBit (entryb, to_b);
        if (an_busy) Argus_Nav_Abort (an_bot);
        actor.solid = SOLID_SLIDEBOX;
        listener.ar_goal = world;
        listener.ar_pending = 0;
        setorigin (listener, entrya.origin);
        AfCheck ("two_live_portals_and_graph_search", gatea != world && gateb != world
                 && bit_a && bit_b && Argus_Shop_Start (listener, entrya));

        gateb.targetname = "audio_fixture_triggered";
        gateb.nextthink = time + 1;
        AfWarp (gateb, actor);
        gateb.targetname = string_null;
        gateb.nextthink = 0;
        AfWarp (gatea, actor);
        AfWarp (gatea, actor);
        AfCheck ("busy_routes_keep_previous_cost", an_busy && actor.origin == landa.origin
                 && !(entrya.an_telemask & bit_a) && !(entryb.an_telemask & bit_b));
        Argus_Nav_Abort (listener);
        Argus_Nav_Frame ();
        AfCheck ("repeat_is_safe_and_conditional_gate_is_ignored",
                 (entrya.an_telemask & bit_a) != 0 && !(entryb.an_telemask & bit_b));

        // Re-arm the first gate in this disposable fixture so both new
        // observations arrive in a single active search.
        gatea.ar_telechecked = 0;
        entrya.an_telemask = 0;
        listener.ar_goal = world;
        listener.ar_pending = 0;
        learned = Argus_Shop_Start (listener, entrya);
        AfWarp (gatea, actor);
        AfWarp (gateb, actor);
        AfWarp (gatea, actor);
        AfCheck ("both_warps_leave_active_search_unchanged", learned && an_busy
                 && !(entrya.an_telemask & bit_a) && !(entryb.an_telemask & bit_b));
        Argus_Nav_Abort (listener);
        Argus_Nav_Frame ();
        AfCheck ("both_portals_learned_when_idle", (entrya.an_telemask & bit_a) != 0
                 && (entryb.an_telemask & bit_b) != 0 && an_pendingtelegate == world);
        AfTeleportCue (listener, actor, gatea);
    }

    argus_bots = roster;
    self = saved;
    activator = world;
    remove (jacket);
    remove (actor);
    remove (listener);
};
