// Private physical regression: a fixed blocked command models combat
// repeatedly choosing the same bad travel line. Production combat still
// perceives, aims and shoots; production physics must find the exit.
float fr_started, fr_done, fr_starttime, fr_lasttime, fr_dt;
float fr_maxmove, fr_firstexit, fr_shots, fr_lastammo, fr_badstep;
float fr_checks, fr_failures, fr_nextdamage, fr_nextunstick, fr_warps;
float fr_rescuecase;
float fr_visible_sec;
vector fr_startpos, fr_previous;
entity fr_bot, fr_foe, fr_goal;

void(string label, float ok) FreezeRecoveryCheck =
{
    fr_checks = fr_checks + 1;
    if (!ok) fr_failures = fr_failures + 1;
    dprint ("FRFIX check "); dprint (label); dprint (" ");
    dprint (ftos (ok)); dprint ("\n");
};

#ifdef RECOVERY_CANDIDATE
void() FreezeRecoveryArm =
{
    self.ar_blockedfrom = time - 2; self.ar_blockedlast = time;
    self.ar_blockedpos = self.origin; self.ar_recoveryuntil = 0;
    self.ar_recoverycheck = 0; self.ar_moveyaw = 0;
};

void() FreezeRecoveryGuards =
{
    local entity obstruction;
    local vector ahead;
    local float heldyaw;
    setorigin (self, fr_startpos); self.velocity = '0 0 0';
    self.flags = self.flags | FL_ONGROUND;
    self.ar_hopair = 0; self.ar_enemy = fr_foe;
    FreezeRecoveryArm ();
    FreezeRecoveryCheck ("clear_exit_armed", Argus_RecoveryWalk ());
    heldyaw = self.ar_recoveryyaw;
    makevectors ('0 0 0' + heldyaw * '0 1 0'); ahead = self.origin + v_forward * 32;
    obstruction = spawn (); obstruction.solid = SOLID_BBOX;
    setsize (obstruction, '-16 -16 -24', '16 16 32'); setorigin (obstruction, ahead);
    FreezeRecoveryCheck ("live_body_cancels_exit", !Argus_RecoveryWalk ()
        && !self.ar_recoveryuntil);
    remove (obstruction);
    FreezeRecoveryArm (); self.ar_liftwait = 1;
    FreezeRecoveryCheck ("mover_wait_held", !Argus_RecoveryWalk () && !self.ar_recoveryuntil);
    self.ar_liftwait = 0;
    self.ar_stucktime = time - 4; self.ar_stuckpos = self.origin;
    self.ar_hurttime = time; self.ar_stuckhurt = time - 2;
    self.ar_stuckstalls = self.ar_stalls; self.ar_hoplift = 1;
    FreezeRecoveryCheck ("mover_rescue_held", !Argus_Unstick ()); self.ar_hoplift = 0;
    FreezeRecoveryArm (); self.ar_hopjump = 1;
    FreezeRecoveryCheck ("typed_jump_held", !Argus_RecoveryWalk ()); self.ar_hopjump = 0;
    FreezeRecoveryArm (); self.ar_wetlevel = 2;
    FreezeRecoveryCheck ("swim_held", !Argus_RecoveryWalk ()); self.ar_wetlevel = 0;
    FreezeRecoveryArm (); self.ar_taskgoal = fr_goal;
    FreezeRecoveryCheck ("task_held", !Argus_RecoveryWalk ()); self.ar_taskgoal = world;
    FreezeRecoveryArm (); self.ar_enemy = world; self.ar_pursuing = 0;
    self.ar_retreating = 0; self.ar_dodgetime = 0; self.ar_gaitpause = time + 1;
    FreezeRecoveryCheck ("chosen_pause_held", !Argus_RecoveryWalk ()); self.ar_gaitpause = 0;
    FreezeRecoveryArm (); self.flags = self.flags - (self.flags & FL_ONGROUND);
    self.velocity_z = 100; setorigin (self, self.origin + '0 0 64');
    FreezeRecoveryCheck ("airborne_held", !Argus_RecoveryWalk () && self.velocity_z == 100);
    setorigin (self, fr_startpos); self.velocity = '0 0 0';
    FreezeRecoveryArm (); self.ar_recoveryuntil = time + 1;
    Argus_BaseStats ();
    FreezeRecoveryCheck ("respawn_clears_recovery", !self.ar_blockedfrom && !self.ar_recoveryuntil
        && !self.ar_hurttime && !self.ar_stuckhurt && !self.ar_stucktime);
};
#endif

void() FreezeRecoveryFixture =
{
    local entity bot, saved, wall;
    local vector moved, ep;
    local float dist;
    if (fr_done) return;
    if (fr_lasttime > 0) fr_dt = time - fr_lasttime;
    fr_lasttime = time;
    if (time < 2) return;
    saved = self;
    if (!fr_started)
    {
        fr_started = 1; fr_starttime = time;
        dprint ("FRFIX begin dt_ms "); dprint (ftos (fr_dt * 1000)); dprint ("\n");
        bot = argus_bots;
        while (bot != world)
        {
            Argus_Nav_Abort (bot);
            bot.solid = SOLID_NOT; bot.movetype = MOVETYPE_NONE;
            bot.health = 0; bot.takedamage = DAMAGE_NO;
            bot.think = SUB_Null; bot.nextthink = 0;
            bot = bot.ar_chain;
        }
        fr_bot = argus_bots;
        self = fr_bot; Argus_BaseStats ();
        self.netname = "recoveryfixture";
        self.ar_skill = 2; self.ar_mode = 2;
        self.ar_gaitpause = 0; self.ar_gaitroll = time + 100;
        self.items = IT_SHOTGUN; self.ammo_shells = 100;
        self.ar_react = time; self.ar_retreatlock = time + 100;
        self.view_ofs = '0 0 22';
        if (mapname == "e1m7")
        {
            setorigin (self, '24 80 8');
#ifdef FR_CORNER_SEAT
            setorigin (self, '39.9 71.1 8');
            fr_rescuecase = 1;
#endif
#ifdef FR_SOUTH_SEAT
            setorigin (self, '23.9 48 8');
#endif
            ep = '-104 80 56';
        }
        else if (mapname == "lqdm2")
        {
            setorigin (self, '-40 -311.8 95.8'); ep = '320 -798 184';
            fr_rescuecase = 1;
        }
        else if (mapname == "e1m1")
        {
            setorigin (self, '181.7 1257.8 -184'); ep = '145 1217 -184';
            fr_rescuecase = 1;
        }
        else
        {
            setorigin (self, '929 -1135 -40');
            // A low solid obstruction blocks feet while leaving a gun lane.
            wall = spawn (); wall.solid = SOLID_BBOX;
            wall.movetype = MOVETYPE_NONE;
            setsize (wall, '-8 -64 -24', '8 64 0');
            setorigin (wall, self.origin + '32 0 0');
            ep = self.origin + '180 0 0';
        }
        if (!fr_rescuecase)
        {
            droptofloor ();
            self.flags = self.flags | FL_ONGROUND;
        }
        fr_startpos = self.origin; fr_previous = self.origin;
        fr_foe = spawn (); fr_foe.classname = "player";
        fr_foe.netname = "fixturefoe"; fr_foe.health = 10000;
        fr_foe.solid = SOLID_SLIDEBOX; fr_foe.takedamage = DAMAGE_AIM;
        setsize (fr_foe, '-16 -16 -24', '16 16 32');
        setorigin (fr_foe, ep);
        fr_foe.view_ofs = '0 0 22';
        fr_goal = spawn (); fr_goal.classname = "item_health";
        self.ar_goal = fr_goal;
        self.ar_enemy = fr_foe; self.ar_seen = time;
        self.ar_lastseen = ep;
        self.angles = '0 0 0';
        self.angles_y = vectoyaw (ep - self.origin); self.ar_moveyaw = 0;
        fr_lastammo = self.ammo_shells;
        dprint ("FRFIX start "); dprint (vtos (self.origin)); dprint ("\n");
    }
    self = fr_bot;
    if (time >= fr_nextdamage)
    {
        // Exercise the ordinary pain path without a knockback impulse that
        // could free the control on its own. Real matches cover incoming fire.
        fr_nextdamage = time + 0.3;
        T_Damage (self, world, fr_foe, 2);
    }
    moved = self.origin - fr_previous; moved_z = 0;
    // A recovery must use walking: even a short teleport fails this bound.
    if (vlen (moved) > 2 * AR_MAXSPEED * fr_dt + 3) fr_badstep = 1;
    fr_previous = self.origin;
    if (time >= fr_nextunstick)
    {
        fr_nextunstick = time + 0.2;
        if (Argus_Unstick ())
        {
            fr_warps = fr_warps + 1;
            fr_previous = self.origin;
        }
    }
    moved = self.origin - fr_startpos; moved_z = 0; dist = vlen (moved);
    if (dist > fr_maxmove) fr_maxmove = dist;
    if (!fr_firstexit && dist >= 64) fr_firstexit = time - fr_starttime;
    Argus_Combat ();
    if (self.ar_obsenemy == fr_foe && time <= self.ar_seen + 0.4)
        fr_visible_sec = fr_visible_sec + fr_dt;
    if (self.ammo_shells < fr_lastammo) fr_shots = fr_shots + 1;
    fr_lastammo = self.ammo_shells;
    // Only the desired travel line is constrained, never position, velocity,
    // collision flags, facing, trigger, or any recovery field.
    self.ar_moveyaw = 0;
    self.ar_mode = 2;
    if (!fr_firstexit) Argus_Physics ();
    if (fr_firstexit || time >= fr_starttime + 7)
    {
        fr_done = 1;
        dprint ("FRFIX result maxmove "); dprint (ftos (fr_maxmove));
        dprint (" exit_sec "); dprint (ftos (fr_firstexit));
        dprint (" shots "); dprint (ftos (fr_shots));
        dprint (" rescues "); dprint (ftos (fr_warps));
        dprint (" visible_sec "); dprint (ftos (fr_visible_sec));
        dprint (" pos "); dprint (vtos (self.origin)); dprint ("\n");
#ifdef RECOVERY_CANDIDATE
        if (fr_rescuecase)
        {
            FreezeRecoveryCheck ("rescues_pin_before_freeze", fr_firstexit > 0 && fr_firstexit < 5.5);
            FreezeRecoveryCheck ("bounded_rescue_count", !fr_badstep && fr_warps <= 1);
        }
        else
        {
            FreezeRecoveryCheck ("walks_out_before_freeze", fr_firstexit > 0 && fr_firstexit < 4);
            FreezeRecoveryCheck ("continuous_motion", !fr_badstep && !fr_warps);
        }
#else
        FreezeRecoveryCheck ("control_reproduces_pin", fr_maxmove < 24 && !fr_firstexit);
        FreezeRecoveryCheck ("continuous_motion", !fr_badstep && !fr_warps);
#endif
        if (fr_rescuecase)
            FreezeRecoveryCheck ("fire_when_visible", fr_visible_sec < 1 || fr_shots >= 1);
        else
            FreezeRecoveryCheck ("still_shoots", fr_shots >= 1);
        FreezeRecoveryCheck ("goal_preserved", self.ar_goal == fr_goal);
        FreezeRecoveryCheck ("pain_exercised", self.health <= 90);
        FreezeRecoveryCheck ("alive_and_dry", self.health > 0 && self.ar_wetlevel < 2
            && self.ar_feettype != CONTENT_LAVA && self.ar_feettype != CONTENT_SLIME);
#ifdef RECOVERY_CANDIDATE
        FreezeRecoveryGuards ();
#endif
        self.movetype = MOVETYPE_NONE; self.think = SUB_Null; self.nextthink = 0;
        dprint ("FRFIX end checks "); dprint (ftos (fr_checks));
        dprint (" failures "); dprint (ftos (fr_failures)); dprint ("\n");
    }
    self = saved;
};
