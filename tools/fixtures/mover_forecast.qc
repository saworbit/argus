// Isolated component controls. Setup owns placement and collision geometry.
// Thereafter only production Argus_Physics and engine physics move the actor.
// These are forecast/physics contracts, not end-to-end route completion.
float mc_started, mc_done, mc_case, mc_when, mc_previous, mc_dt, mc_frames;
float mc_forecast, mc_jump, mc_lost, mc_wet, mc_depth, mc_dry, mc_floor;
float mc_initial_state, mc_initial_gap, mc_blocked, mc_target_contents;
float mc_probe, mc_allowed, mc_invalid, mc_checks, mc_refused, mc_accepted;
float mc_wasair;
float mc_pool_floor, mc_pool_surface;
entity mc_bot, mc_mover, mc_goal, mc_node;
vector mc_seed, mc_target, mc_forecast_landing;

void(float allowed, float yaw, float speed) MoverForecastDecision =
{
    if (!mc_started || mc_done || self != mc_bot || mc_probe) return;
    mc_checks = mc_checks + 1;
    if (allowed) { mc_accepted = mc_accepted + 1; mc_allowed = 1; }
    else mc_refused = mc_refused + 1;
    dprint ("MCFIX decision frame "); dprint (ftos (mc_frames));
    dprint (" allowed "); dprint (ftos (allowed));
    dprint (" yaw "); dprint (ftos (yaw));
    dprint (" speed "); dprint (ftos (speed));
    dprint (" pos "); dprint (vtos (self.origin)); dprint ("\n");
};

void() MoverForecastSetup =
{
    local entity b, saved, trigger, block;
    local vector direction, center, shift, p;
    mc_started = 1; mc_when = time; mc_case = cvar ("scratch2");
    b = argus_bots;
    while (b != world)
    {
        Argus_Nav_Abort (b);
        if (b.ar_slot == 0) mc_bot = b;
        b.think = SUB_Null; b.nextthink = 0;
        if (b.ar_slot != 0)
        {
            b.health = 0; b.solid = SOLID_NOT; b.movetype = MOVETYPE_NONE;
            b.ar_respawntime = time + 3600;
        }
        b = b.ar_chain;
    }
    saved = self; self = mc_bot; Argus_BaseStats ();
    setorigin (self, '625 1425 24');
    mc_mover = Argus_NearestMover (320);
    if (mc_mover.classname != "plat") error ("MCFIX missing real platform");
    // Disable only this platform's triggers during setup. The undocked arm
    // has a real upward velocity and remains below pos1 during observation.
    trigger = nextent (world);
    while (trigger != world)
    {
        if (trigger.enemy == mc_mover && trigger.solid == SOLID_TRIGGER)
            trigger.solid = SOLID_NOT;
        trigger = nextent (trigger);
    }
    mc_mover.think = SUB_Null; mc_mover.nextthink = 0;
    mc_mover.velocity = '0 0 0'; mc_mover.state = STATE_TOP;
    setorigin (mc_mover, mc_mover.pos1);
    mc_seed = '657 1441 344'; mc_target = '529 1393 344';
    if (mc_case == 3) mc_target_z = mc_target_z + 32;
    if (mc_case == 4)
    {
        setorigin (mc_mover, mc_mover.pos1 - '0 0 16');
        mc_mover.state = STATE_UP; mc_mover.velocity = '0 0 1';
        mc_mover.nextthink = mc_mover.ltime + 60;
        mc_seed_z = mc_seed_z - 16;
    }
    if (mc_case == 5)
    {
        // The real e1m6 pool has floor -112 and water surface -64.
        // Move the real brush platform beside it. Do not fake liquid fields.
        center = (mc_mover.mins + mc_mover.maxs) * 0.5;
        shift = '1200 400 -64' - center;
        shift_z = -64 - mc_mover.maxs_z;
        setorigin (mc_mover, shift);
        mc_mover.pos1 = shift; mc_mover.pos2 = shift - '0 0 16';
        mc_seed = '1200 368 -40'; mc_target = '1200 240 -88';
    }
    if (mc_case == 2)
    {
        // A real BSP brush blocks the rising arc; nomonsters traces must
        // see it. A SOLID_BBOX prop would not test this production predictor.
        block = spawn (); setmodel (block, mc_mover.model);
        block.solid = SOLID_BSP; block.movetype = MOVETYPE_PUSH;
        center = (block.mins + block.maxs) * 0.5;
        setorigin (block, '561 1393 336' - center);
        traceline ('625 1417 380', '529 1393 380', TRUE, self);
        mc_blocked = trace_fraction < 1 && trace_ent == block;
    }
    setorigin (self, mc_seed); setsize (self, '-16 -16 -24', '16 16 32');
    self.movetype = MOVETYPE_STEP; self.flags = FL_ONGROUND;
    self.groundentity = mc_mover; self.ar_enemy = world;
    self.ar_node = world; self.ar_hopjump = 0; self.ar_hoprj = 0;
    self.ar_hoptrain = 0; self.ar_hopswim = 0; self.ar_hopdoor = 0;
    self.ar_sprintstate = 0; self.ar_hopair = 0; self.ar_jump = 0;
    self.ar_hoplift = 1; self.ar_liftwait = 0; self.ar_mode = 2;
    self.ar_tactic = 0; self.ar_tactic_settle = 0;
    self.ar_gaitpause = 0; self.ar_gapjump = 0;
    self.ar_feettype = CONTENT_EMPTY; self.ar_wetlevel = 0;
    mc_node = spawn (); mc_node.origin = mc_target; self.ar_node = mc_node;
    mc_goal = spawn (); mc_goal.classname = "argus_task_goal";
    mc_goal.solid = SOLID_TRIGGER; mc_goal.flags = FL_ITEM;
    setorigin (mc_goal, mc_target); setsize (mc_goal, '-1 -1 -1', '1 1 1');
    self.ar_goal = mc_goal; self.ar_taskgoal = mc_goal;
    self.ar_taskdeadline = time + 60; self.ar_goalstart = time + 3600;
    direction = mc_target - mc_seed; direction_z = 0;
    self.ar_moveyaw = vectoyaw (direction);
    self.velocity = normalize (direction) * 140;
    mc_initial_state = mc_mover.state;
    mc_initial_gap = mc_mover.pos1_z - mc_mover.origin_z;
    mc_target_contents = pointcontents (mc_target);
    // Measure the real pool column independently of actor waterlevel.
    if (mc_case == 5)
    {
        traceline (mc_target, mc_target - '0 0 128', TRUE, self);
        mc_pool_floor = trace_endpos_z;
        p = trace_endpos + '0 0 0.1';
        while (pointcontents (p) == CONTENT_WATER && mc_depth < 256)
        { mc_depth = mc_depth + 1; p_z = p_z + 1; }
        mc_pool_surface = p_z;
    }
    dprint ("BHVRPL begin mover_forecast\n");
    dprint ("MCFIX begin dt_ms "); dprint (ftos (mc_dt * 1000));
    dprint (" layout 1 case "); dprint (ftos (mc_case)); dprint ("\n");
    self = saved;
};

void() MoverForecastObserve =
{
    local float retained, dry;
    retained = mc_bot.ar_goal == mc_goal && mc_bot.ar_taskgoal == mc_goal
        && mc_bot.ar_node == mc_node;
    if (!retained) mc_lost = 1;
    if (!mc_wasair && mc_bot.ar_hopair && mc_bot.velocity_z == AR_JUMPVEL)
    {
        mc_jump = 1;
        if (!mc_allowed) mc_invalid = 1;
        dprint ("MCFIX launch frame "); dprint (ftos (mc_frames));
        dprint (" accepted "); dprint (ftos (mc_allowed)); dprint ("\n");
    }
    if (mc_bot.ar_wetlevel > mc_wet) mc_wet = mc_bot.ar_wetlevel;
    dry = mc_bot.ar_wetlevel == 0 && mc_bot.ar_feettype != CONTENT_WATER
        && mc_bot.ar_feettype != CONTENT_LAVA && mc_bot.ar_feettype != CONTENT_SLIME;
    if ((mc_bot.flags & FL_ONGROUND) && mc_bot.groundentity == world)
    { mc_floor = 1; if (dry) mc_dry = 1; }
};

void() MoverForecastFrame =
{
    local entity saved;
    if (mc_previous > 0) mc_dt = time - mc_previous;
    mc_previous = time;
    if (time < 2) { Argus_FrameAll (); return; }
    if (!mc_started) MoverForecastSetup ();
    if (mc_done) return;
    saved = self; self = mc_bot;
    // One component call at the seeded 140 u/s seat. No actor fields are
    // changed afterwards by the fixture until the terminal freeze.
    if (mc_frames == 0)
    {
        mc_probe = 1;
        mc_forecast = Argus_MoverGapJumpOK (self.ar_moveyaw, 140);
        mc_forecast_landing = trace_endpos;
        mc_probe = 0;
    }
    mc_frames = mc_frames + 1;
    mc_allowed = 0; mc_wasair = self.ar_hopair;
    Argus_Physics ();
    MoverForecastObserve ();
    if (time >= mc_when + 1.5 || mc_bot.health <= 0)
    {
        mc_done = 1;
        dprint ("MCFIX result case "); dprint (ftos (mc_case));
        dprint (" forecast "); dprint (ftos (mc_forecast));
        dprint (" jump "); dprint (ftos (mc_jump));
        dprint (" invalid_jump "); dprint (ftos (mc_invalid));
        dprint (" checks "); dprint (ftos (mc_checks));
        dprint (" refused "); dprint (ftos (mc_refused));
        dprint (" accepted "); dprint (ftos (mc_accepted));
        dprint (" alive "); dprint (ftos (mc_bot.health > 0));
        dprint (" retained "); dprint (ftos (!mc_lost));
        dprint (" wetlevel "); dprint (ftos (mc_wet));
        dprint (" depth "); dprint (ftos (mc_depth));
        dprint (" dry_floor "); dprint (ftos (mc_dry));
        dprint (" world_floor "); dprint (ftos (mc_floor));
        dprint (" state "); dprint (ftos (mc_initial_state));
        dprint (" dock_gap "); dprint (ftos (mc_initial_gap));
        dprint (" blocked "); dprint (ftos (mc_blocked));
        dprint (" target_contents "); dprint (ftos (mc_target_contents));
        dprint (" frames "); dprint (ftos (mc_frames));
        dprint (" seconds "); dprint (ftos (time - mc_when));
        dprint (" predicted "); dprint (vtos (mc_forecast_landing));
        dprint (" pos "); dprint (vtos (mc_bot.origin));
        dprint (" pool_floor "); dprint (ftos (mc_pool_floor));
        dprint (" pool_surface "); dprint (ftos (mc_pool_surface));
        dprint (" final_gap "); dprint (ftos (mc_mover.pos1_z - mc_mover.origin_z));
        dprint ("\n");
        self.velocity = '0 0 0'; self.movetype = MOVETYPE_NONE;
        self.think = SUB_Null; self.nextthink = 0;
    }
    self = saved;
};
