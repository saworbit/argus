// First attack/cover/return milestone: two engine-proven route candidates.
// Coordinates identify existing nodes; no generated graph is changed. All
// tactical storage belongs to the bot, independent of the item-route BFS.
// Runtime geometry decides eligibility relative to OBSERVED enemy position.

void(string why) Argus_TacticLog =
{
    dprint ("ARGEVT "); dprint (self.netname); dprint (" tactic ");
    dprint (why); dprint ("\n");
};

// Evaluation ticks, not independent encounters or proof of a hit (#517).
void(string stage) Argus_TacticCheck =
{
    dprint ("TACTICCHECK "); dprint (self.netname);
    dprint (" t "); dprint (ftos (time));
    dprint (" stage "); dprint (stage); dprint ("\n");
};

void() Argus_TacticReset =
{
    if (self.ar_tactic)
    {
        self.ar_tactic_settle = time + 0.5;
        self.ar_jump = 0;
    }
    self.ar_tactic = 0; self.ar_tactic_speed = 0;
    self.ar_tactic_enemy = world; self.ar_tactic_hop = world;
    self.ar_tactic_cover = world; self.ar_tactic_exit = world;
};

void(string why) Argus_TacticAbort =
{
    Argus_BehaviourEvent (why);
    Argus_TacticLog (why);
    Argus_TacticReset ();
    self.ar_tactic_cool = time + 10;
    self.ar_liftwait = 0;
};

entity(vector p) Argus_TacticNode =
{
    local entity n;
    n = find (world, classname, "argus_node");
    while (n != world)
    {
        if (vlen (n.origin - p) < 1) return n;
        n = find (n, classname, "argus_node");
    }
    return world;
};

float(vector p, vector observer) Argus_TacticHidden =
{
    local float i;
    local vector q;
    // Centre plus all eight corners of the standing hull. In particular,
    // dm2 n104 fails the near-side corner although its centre is hidden.
    i = 0;
    while (i < 9)
    {
        q = p;
        if (i < 8)
        {
            q_x = q_x - 16 + 32 * (i & 1);
            q_y = q_y - 16 + 16 * (i & 2);
            q_z = q_z - 24 + 14 * (i & 4);
        }
        traceline (observer + '0 0 22', q, TRUE, self);
        if (trace_fraction == 1) return FALSE;
        i = i + 1;
    }
    return TRUE;
};

float(vector p, vector observer) Argus_TacticShotLine =
{
    if (pointcontents (p + '0 0 22') == CONTENT_SOLID) return FALSE;
    // A torso sightline can clear a ledge while a foot-aimed rocket from
    // the lower muzzle still hits it. Both lanes must clear for this RL move.
    traceline (p + '0 0 16', observer - '0 0 16', TRUE, self);
    if (trace_fraction < 1) return FALSE;
    traceline (p + '0 0 22', observer + '0 0 8', TRUE, self);
    return (trace_fraction == 1);
};

float(vector p) Argus_TacticAngle =
{
    local vector a, b;
    a = self.ar_tactic_open - self.ar_tactic_enemypos; a_z = 0;
    b = p - self.ar_tactic_enemypos; b_z = 0;
    // cos(30 degrees): horizontal angle as experienced by the opponent.
    return (normalize (a) * normalize (b) <= 0.866);
};

float(vector a, vector b) Argus_TacticWalk =
{
    local float i, count;
    local vector p, off;
    local entity t;
    if (fabs (a_z - b_z) > 8 || vlen (b - a) > 260) return FALSE;
    if (Argus_AvoidLine (a, b, TRUE)) return FALSE;
    // Conservative swept body clearance; floor support every 24 units.
    i = 0;
    while (i < 4)
    {
        off = '-15 -15 0';
        if (i & 1) off_x = 15;
        if (i & 2) off_y = 15;
        traceline (a + off, b + off, TRUE, self);
        if (trace_fraction < 1) return FALSE;
        i = i + 1;
    }
    count = ceil (vlen (b - a) / 24); if (count < 1) count = 1;
    i = 0;
    while (i <= count)
    {
        p = a + (b - a) * (i / count);
        if (!Argus_BoxClear (p)) return FALSE;
        if (pointcontents (p - '0 0 23') != CONTENT_EMPTY) return FALSE;
        traceline (p, p - '0 0 32', TRUE, self);
        if (trace_fraction == 1 || trace_ent != world) return FALSE;
        // Teleports are untyped links. Reject their expanded trigger bounds
        // explicitly, even when their entrance and exit are close together.
        t = find (world, classname, "trigger_teleport");
        while (t != world)
        {
            if (Argus_InTriggerBox (t, p))
                return FALSE;
            t = find (t, classname, "trigger_teleport");
        }
        i = i + 1;
    }
    return TRUE;
};

float(entity a, entity b) Argus_TacticLink =
{
    if (a == world || b == world) return FALSE;
    if (!Argus_NavGetLinkBit (a, b) || Argus_LinkIsTyped (a, b)) return FALSE;
    return Argus_TacticWalk (a.origin, b.origin);
};

void() Argus_TacticBegin =
{
    local vector start, via, cover, finish, p;
    local entity a, b, c, d;
    local float i, exposed, speed, stopdist;
    local vector drift;
    if (self.ar_tactic || time < self.ar_tactic_settle || time < self.ar_tactic_cool
        || time < self.ar_tactic_check) return;
    self.ar_tactic_check = time + 0.5;
    if (coop || !deathmatch || self.ar_slot != 1 || skill != 1 || self.ar_skill < 1)
        return;
    Argus_TacticCheck ("evaluated");
    if (self.ar_enemy == world || self.ar_seen != time)
    { Argus_TacticCheck ("no_visible_target"); return; }
    Argus_TacticCheck ("visible");
    if (self.weapon != IT_ROCKET_LAUNCHER || self.ammo_rockets < 2)
    { Argus_TacticCheck ("loadout"); return; }
    Argus_TacticCheck ("loaded");
    if (self.health + self.armorvalue * self.armortype < 75
        || self.ar_retreating || time < self.ar_dodgetime
        || !(self.flags & FL_ONGROUND) || self.ar_wetlevel
        || self.ar_hopjump || self.ar_hoplift || self.ar_hoprj
        || self.ar_hoptrain || self.ar_hopdoor || self.ar_hopswim)
    { Argus_TacticCheck ("unsafe_state"); return; }
    Argus_TacticCheck ("eligible");
    if (mapname == "dm4")
    { start = '465 -279 -104'; via = '561 -183 -104'; cover = via; finish = '465 -151 -104'; }
    else if (mapname == "dm2")
    { start = '2209 -279 24'; via = '2241 -87 24'; cover = '2177 -23 24'; finish = '2145 -119 24'; }
    else { Argus_TacticCheck ("unsupported_map"); return; }
    if (vlen (self.origin - start) > 48)
    { Argus_TacticCheck ("outside_start"); return; }
    Argus_TacticCheck ("at_start");
    // Validate the whole braking envelope, including the residual velocity
    // after the opening shot. Stop-friction is linear below STOPSPEED and
    // proportional above it; this conservative bound also covers a frame
    // of engine movement. Never begin by sliding off the opening walkway.
    drift = self.velocity; drift_z = 0;
    speed = vlen (drift);
    if (speed > 1)
    {
        if (speed > AR_STOPSPEED)
            stopdist = (speed - AR_STOPSPEED) / AR_FRICTION
                       + AR_STOPSPEED / (2 * AR_FRICTION);
        else
            stopdist = speed * speed / (2 * AR_FRICTION * AR_STOPSPEED);
        stopdist = stopdist + speed * frametime;
        if (!Argus_TacticWalk (self.origin,
                self.origin + normalize (drift) * stopdist))
        { Argus_TacticCheck ("braking"); return; }
    }
    a = Argus_TacticNode (start); b = Argus_TacticNode (via);
    c = Argus_TacticNode (cover); d = Argus_TacticNode (finish);
    if (!Argus_TacticLink (a, b) || !Argus_TacticLink (c, d))
    { Argus_TacticCheck ("route"); return; }
    if (b != c && !Argus_TacticLink (b, c))
    { Argus_TacticCheck ("route"); return; }
    if (!Argus_TacticWalk (self.origin, via))
    { Argus_TacticCheck ("approach"); return; }
    if (!Argus_TacticHidden (cover, self.ar_lastseen)
        || !Argus_TacticShotLine (self.origin, self.ar_lastseen)
        || !Argus_TacticShotLine (finish, self.ar_lastseen))
    { Argus_TacticCheck ("sight_geometry"); return; }
    self.ar_tactic_open = self.origin;
    self.ar_tactic_enemypos = self.ar_lastseen;
    if (!Argus_TacticAngle (finish))
    { Argus_TacticCheck ("angle"); return; }
    // Score FIRST reappearance, not just the endpoint (dm2 D's false win).
    i = 1; exposed = 0;
    while (i <= 12)
    {
        p = cover + (finish - cover) * (i / 12);
        if (!exposed && !Argus_TacticHidden (p, self.ar_tactic_enemypos))
        {
            if (!Argus_TacticAngle (p))
            { Argus_TacticCheck ("early_angle"); return; }
            exposed = 1;
        }
        i = i + 1;
    }
    self.ar_tactic = 1;
    self.ar_tactic_enemy = self.ar_enemy;
    self.ar_tactic_hop = b; self.ar_tactic_cover = c; self.ar_tactic_exit = d;
    self.ar_tactic_until = time + 1.2;
    self.ar_tactic_ammo = self.ammo_rockets;
    self.ar_tactic_progress = time; self.ar_tactic_pos = self.origin;
    self.ar_tactic_check = 0;
    self.ar_jump = 0;
    self.ar_bitem = world; // release an incompatible detour without a penalty
    Argus_TacticLog ("prepare");
};

void() Argus_TacticSteer =
{
    local float dist;
    if (self.ar_tactic == 1 || self.ar_tactic == 4)
    {
        self.ar_tactic_speed = 0;
        return;
    }
    dist = vlen (self.ar_tactic_hop.origin - self.origin);
    self.ar_moveyaw = Argus_MotionTurn (self.ar_moveyaw,
        vectoyaw (self.ar_tactic_hop.origin - self.origin), "tactic_route");
    self.ar_tactic_speed = dist * 4;
    if (self.ar_tactic_speed > 280) self.ar_tactic_speed = 280;
    // Below 60, ground stop-friction exceeds acceleration: the bot would
    // creep to a halt just short of the seat instead of completing the leg.
    if (self.ar_tactic_speed < 80) self.ar_tactic_speed = 80;
};

float() Argus_TacticThink =
{
    local float visible, dist;
    local vector to;
    if (!self.ar_tactic) return FALSE;
    if (self.health <= 0 || self.ar_enemy != self.ar_tactic_enemy
        || self.ar_enemy == world)
    { Argus_TacticAbort ("abort target"); return FALSE; }
    if (time > self.ar_tactic_until)
    { Argus_TacticAbort ("abort timeout"); return FALSE; }
    if (self.weapon != IT_ROCKET_LAUNCHER || skill != 1 || self.ar_skill < 1)
    { Argus_TacticAbort ("abort weapon"); return FALSE; }
    if (self.ar_tactic == 1 && vlen (self.origin - self.ar_tactic_open) > 48)
    { Argus_TacticAbort ("abort displaced"); return FALSE; }
    visible = (self.ar_seen == time);
    if (self.ar_tactic == 4 && !visible)
    { Argus_TacticAbort ("abort sight"); return FALSE; }
    if (visible && vlen (self.ar_lastseen - self.ar_tactic_enemypos) > 80)
    { Argus_TacticAbort ("abort moved"); return FALSE; }
    if (self.health + self.armorvalue * self.armortype < 70
        || self.ar_retreating || self.ammo_rockets < 1)
    { Argus_TacticAbort ("abort survival"); return FALSE; }
    if (self.ar_wetlevel || fabs (self.origin_z - self.ar_tactic_cover.origin_z) > 12
        || self.velocity_z > 100 || time < self.teleport_time)
    { Argus_TacticAbort ("abort displaced"); return FALSE; }
    if (time > self.ar_dodgecheck)
    { self.ar_dodgecheck = time + 0.15; Argus_DodgeScan (); }
    if (time < self.ar_dodgetime)
    {
        Argus_TacticAbort ("abort missile");
        self.ar_moveyaw = Argus_MotionTurn (self.ar_moveyaw, self.ar_dodgeyaw, "tactic_dodge");
        self.button0 = 0;
        return TRUE;
    }
    // The normal combat refresh only runs with a visible primary target.
    // Keep watching for a new attacker while the primary is behind cover.
    if (time > self.ar_secondaryscan)
    {
        self.ar_secondaryscan = time + 0.2;
        self.ar_secondary = Argus_FindSecondaryThreat (self.ar_enemy);
    }
    if (self.ar_secondary != world && Argus_CanSee (self.ar_secondary))
    { Argus_TacticAbort ("abort crossfire"); return FALSE; }
    if (self.ar_tactic == 2 || self.ar_tactic == 3)
    {
        dist = vlen (self.ar_tactic_hop.origin - self.origin);
        if (vlen (self.origin - self.ar_tactic_pos) > 12)
        { self.ar_tactic_pos = self.origin; self.ar_tactic_progress = time; }
        if (time > self.ar_tactic_progress + 0.6)
        { Argus_TacticAbort ("abort blocked"); return FALSE; }
        if (dist < 18 && self.ar_tactic == 2)
        {
            if (self.ar_tactic_hop != self.ar_tactic_cover)
                self.ar_tactic_hop = self.ar_tactic_cover;
            else if (Argus_TacticHidden (self.origin, self.ar_tactic_enemypos))
            {
                self.ar_tactic = 3; self.ar_tactic_hop = self.ar_tactic_exit;
                Argus_TacticLog ("covered");
            }
            else
            { Argus_TacticAbort ("abort cover"); return FALSE; }
        }
        if (self.ar_tactic == 3 && !Argus_TacticHidden (self.origin, self.ar_tactic_enemypos))
        {
            if (!Argus_TacticAngle (self.origin))
            { Argus_TacticAbort ("abort early"); return FALSE; }
            // At the lab's 0.1 s cadence the minimum step is 8 units.
            // Current angle and shot geometry still validate the actual seat.
            if (visible && dist < 16
                && Argus_TacticShotLine (self.origin, self.ar_lastseen))
            {
                self.ar_tactic = 4; self.ar_tactic_ammo = self.ammo_rockets;
                self.ar_tactic_progress = time;
                if (self.ar_tactic_until > time + 0.6)
                    self.ar_tactic_until = time + 0.6;
                Argus_TacticLog ("reappear");
            }
        }
        if (time >= self.ar_tactic_check)
        {
            self.ar_tactic_check = time + 0.12;
            if (!Argus_TacticWalk (self.origin, self.ar_tactic_hop.origin))
            { Argus_TacticAbort ("abort route"); return FALSE; }
        }
    }
    Argus_TacticSteer ();
    if (visible) return FALSE; // existing aim, reaction and trigger own the shot
    // Keep the route through sight loss without reading hidden coordinates.
    // Pre-aim with a bounded turn toward the remembered position, never fire.
    to = self.ar_tactic_enemypos - self.origin;
    self.ar_aimvel = 0; // concealed ChangeYaw replaces the spring this frame
    self.ideal_yaw = vectoyaw (to);
    self.yaw_speed = AR_TURNRATE * frametime;
    ChangeYaw ();
    self.button0 = 0;
    return TRUE;
};

void() Argus_TacticShot =
{
    // Called only after an actual W_Attack, independent of ammo pickups or
    // unlimited-ammo rules. A net ammo delta is not a firing acknowledgement.
    if (!self.ar_tactic || self.weapon != IT_ROCKET_LAUNCHER) return;
    if (self.ar_tactic == 1)
    {
        self.ar_tactic_open = self.origin; // angle starts at the ACTUAL shot
        self.ar_tactic = 2; self.ar_tactic_until = time + 2.8;
        self.ar_tactic_progress = time; self.ar_tactic_pos = self.origin;
        self.button0 = 0;
        Argus_TacticSteer (); // physics runs this frame, including at 0.1 s
        Argus_TacticLog ("opening");
    }
    else if (self.ar_tactic == 4 && self.ar_seen == time)
    {
        Argus_TacticLog ("returnshot");
        Argus_TacticReset ();
        self.ar_tactic_cool = time + 14;
        self.ar_liftwait = 0;
    }
};
