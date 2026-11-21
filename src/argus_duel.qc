// Movement and damage models shared by the deathmatch decisions.
float() Argus_Advanced =
{
    return (!argus_duel_ab || self.ar_abarm);
};

float() Argus_EffectiveStack =
{
    return self.health + self.armortype * self.armorvalue;
};

float(vector wish) Argus_MomentumLaunch =
{
    local vector horizontal, dir, middle, landing;
    local float speed, gravity, distance;
    local entity next;

    if (!Argus_Advanced () || !deathmatch || coop || self.ar_skill < 1.5 || self.ar_enemy != world
        || self.ar_taskgoal != world || self.ar_liftwait
        || self.ar_door != world || self.ar_hopjump || self.ar_hoprj || self.ar_hoptrain
        || self.ar_hoplift || self.ar_hopswim || self.ar_hopdoor
        || self.ar_feettype != CONTENT_EMPTY || self.groundentity != world
        || self.ar_hazhold || time < self.ar_momentum_next)
        return FALSE;
    horizontal = self.velocity;
    horizontal_z = 0;
    speed = vlen (horizontal);
    if (speed < 280 || speed > 398) return FALSE;
    dir = normalize (horizontal);
    if (dir * wish < 0.985) return FALSE;
    self.ar_momentum_next = time + 0.3;

    gravity = Argus_Gravity ();
    distance = 398 * 360 / gravity;
    if (distance < 120 || distance > 220) return FALSE;
    if (self.ar_node != world)
    {
        middle = self.ar_node.origin - self.origin;
        if (vlen (middle) < distance)
        {
            next = Argus_GetNext (self.ar_node, self);
            if (next == world || Argus_LinkIsTyped (self.ar_node, next)) return FALSE;
            middle = next.origin - self.origin;
        }
        if (vlen (middle) < distance || fabs (middle_z) > 16
            || normalize (middle) * dir < 0.965)
            return FALSE;
    }
    else if (self.ar_mode == 0)
    {
        if (self.ar_wanderturn < time + 0.55) return FALSE;
    }
    else
    {
        if (self.ar_goal == world) return FALSE;
        if (vlen (Argus_GoalPoint (self.ar_goal) - self.origin) < distance)
            return FALSE;
    }
    middle = self.origin + dir * (0.5 * distance);
    landing = self.origin + dir * distance;
    if (!Argus_LiveWalk (self.origin, middle)) return FALSE;
    if (!Argus_LiveWalk (middle, landing)) return FALSE;
    traceline (self.origin + '0 0 54', landing + '0 0 54', TRUE, self);
    if (trace_fraction < 1 || trace_startsolid) return FALSE;

    self.ar_momentum_flight = TRUE;
    self.ar_momentum_next = time + 0.72;
    self.velocity_z = 180;
    self.flags = self.flags - (self.flags & FL_ONGROUND);
    Argus_Event ("momentum");
    return TRUE;
};

vector(vector desired) Argus_MomentumWish =
{
    local vector along, side, horizontal;
    local float speed, projection, accel;

    horizontal = self.velocity;
    horizontal_z = 0;
    speed = vlen (horizontal);
    if (speed < 240 || speed >= 390) return desired;
    along = normalize (horizontal);
    if (along * desired < 0.95) return desired;
    side = along_y * '-1 0 0' + along_x * '0 1 0';
    if (side * desired < 0) side = '0 0 0' - side;
    accel = AR_ACCEL * frametime * AR_MAXSPEED;
    projection = (AR_AIRWISH - accel) / speed;
    if (projection < 0) projection = 0;
    return normalize (side + along * projection);
};

float(vector impact, float radiusDamage) Argus_SurvivesSplash =
{
    local float points, saved;
    local vector centre;

    if (self.invincible_finished > time) return TRUE;
    centre = self.origin + (self.mins + self.maxs) * 0.5;
    points = (radiusDamage - 0.5 * vlen (impact - centre)) * 0.5;
    if (points <= 0) return TRUE;
    if (self.super_damage_finished > time)
    {
        points = points * 4;
        if (deathmatch_supermode()) points = points * 2;
    }
    saved = ceil (points * self.armortype);
    if (saved > self.armorvalue) saved = self.armorvalue;
    return self.health - ceil (points - saved) > 8;
};

float(vector target) Argus_DuelSplashClear =
{
    local vector start;
    local float reach;

    if (self.weapon != IT_ROCKET_LAUNCHER && self.weapon != IT_GRENADE_LAUNCHER)
        return TRUE;
    if (!Argus_SurvivesSplash (target, 120)) return FALSE;
    makevectors (self.v_angle);
    start = self.origin + '0 0 16';
    reach = vlen (target - start);
    if (reach > 120) reach = 120;
    traceline (start, start + v_forward * reach, FALSE, self);
    if (trace_fraction == 1) return TRUE;
    return Argus_SurvivesSplash (trace_endpos, 120);
};

float(float d, vector target, float preferred) Argus_DuelWeapon =
{
    local float score, best, w, finish, below;

    if (!Argus_Advanced () || !deathmatch || coop || self.ar_skill < AR_SKILL_LEAD || self.ar_tactic)
        return preferred;
    // Preserve the beam when the range and water checks admit it and
    // there are cells for a burst. Elevation alone does not beat hitscan.
    if (preferred == IT_LIGHTNING && self.ammo_cells >= 8)
        return preferred;
    finish = 0;
    if (self.ar_trade_target == self.ar_enemy && time < self.ar_trade_until
        && self.ar_trade_damage >= 45)
        finish = 20;
    below = self.origin_z - target_z;
    best = 0;
    w = IT_AXE;
    if ((self.items & IT_SHOTGUN) && self.ammo_shells >= 1)
    {
        w = IT_SHOTGUN;
        best = 26;
    }
    if ((self.items & IT_NAILGUN) && self.ammo_nails >= 1)
    {
        score = 36 - d * 0.011;
        if (self.ammo_nails >= 12) score = score + 5;
        if (score > best) { w = IT_NAILGUN; best = score; }
    }
    if ((self.items & IT_SUPER_SHOTGUN) && self.ammo_shells >= 2)
    {
        score = 78 - d * 0.12 + finish;
        if (self.weapon == IT_SUPER_SHOTGUN) score = score + 5;
        if (score > best) { w = IT_SUPER_SHOTGUN; best = score; }
    }
    if ((self.items & IT_SUPER_NAILGUN) && self.ammo_nails >= 2)
    {
        score = 56 - d * 0.027;
        if (self.ammo_nails >= 16) score = score + 11;
        if (self.weapon == IT_SUPER_NAILGUN) score = score + 5;
        if (score > best) { w = IT_SUPER_NAILGUN; best = score; }
    }
    if ((self.items & IT_GRENADE_LAUNCHER) && self.ammo_rockets >= 1
        && time >= self.ar_splashwait && d >= 220 && d < 585 && Argus_SurvivesSplash (target, 120))
    {
        score = 44 - fabs (360 - d) * 0.045;
        if (below > 64) score = score + 18;
        if (score > best) { w = IT_GRENADE_LAUNCHER; best = score; }
    }
    if ((self.items & IT_ROCKET_LAUNCHER) && self.ammo_rockets >= 1
        && time >= self.ar_splashwait && d > 140 && Argus_SurvivesSplash (target, 120))
    {
        score = 76 - fabs (375 - d) * 0.048;
        if (below > 25) score = score + 13;
        if (self.ammo_rockets >= 5) score = score + 7;
        if (self.weapon == IT_ROCKET_LAUNCHER) score = score + 5;
        if (score > best) { w = IT_ROCKET_LAUNCHER; best = score; }
    }
    if ((self.items & IT_LIGHTNING) && self.ammo_cells >= 1 && d < 530
        && self.ar_wetlevel <= 1 && self.watertype > CONTENT_WATER)
    {
        score = 106 - d * 0.062;
        if (self.ammo_cells <= 4) score = score - 10;
        if (self.weapon == IT_LIGHTNING) score = score + 6;
        if (score > best) w = IT_LIGHTNING;
    }
    return w;
};

// Each listener retains its two strongest recent non-global observations.
// Scores fall linearly over the next three seconds and reserve no edicts.
void(entity listener, entity actor, vector point, float weight) Argus_ThreatMark =
{
    local float first, second;

    if (!deathmatch || coop || actor == world || actor == listener
        || actor.classname != "player" || listener.ar_skill < AR_SKILL_MEMORY)
        return;
    first = listener.ar_threat_until0 - time;
    second = listener.ar_threat_until1 - time;
    if (listener.ar_threat_actor0 == actor
        || (listener.ar_threat_actor1 != actor && first <= second && first < weight))
    {
        listener.ar_threat_actor0 = actor;
        listener.ar_threat_pos0 = point;
        if (weight > first) listener.ar_threat_until0 = time + weight;
    }
    else if (listener.ar_threat_actor1 == actor || second < weight)
    {
        listener.ar_threat_actor1 = actor;
        listener.ar_threat_pos1 = point;
        if (weight > second) listener.ar_threat_until1 = time + weight;
    }
};

float(entity actor) Argus_ThreatConfidence =
{
    if (self.ar_threat_actor0 == actor && self.ar_threat_until0 > time)
        return self.ar_threat_until0 - time;
    if (self.ar_threat_actor1 == actor && self.ar_threat_until1 > time)
        return self.ar_threat_until1 - time;
    return 0;
};

vector() Argus_ThreatBearing =
{
    if (self.ar_threat_until0 > time && self.ar_threat_until0 >= self.ar_threat_until1)
        return self.ar_threat_pos0;
    if (self.ar_threat_until1 > time) return self.ar_threat_pos1;
    return self.ar_sndpos;
};

void(entity victim, entity attacker, float take, float saved) Argus_DuelDamage =
{
    if (victim == attacker)
    {
        if (take > 0)
        {
            dprint ("ARGEVT "); dprint (attacker.netname);
            dprint (" self_damage_v1 "); dprint (ftos (take)); dprint ("\n");
        }
        return;
    }
    if (attacker.ar_obsenemy != victim || time > attacker.ar_seen + 0.45) return;
    if (attacker.ar_trade_target != victim || time >= attacker.ar_trade_until)
        attacker.ar_trade_damage = 0;
    attacker.ar_trade_target = victim;
    attacker.ar_trade_damage = attacker.ar_trade_damage + take + saved * 0.5;
    attacker.ar_trade_until = time + 2.5;
};

float(entity item, float value, float arrival) Argus_MajorTiming =
{
    local float wait;

    wait = item.nextthink - time - arrival;
    if (wait > 10) return 0;
    if (Argus_Advanced () && Argus_MajorName (item) != "" && Argus_EffectiveStack () >= 95
        && wait >= 1 && wait <= 5)
        return value * 1.12;
    if (wait > 3) return value * 0.55;
    return value;
};

float() Argus_ContestNearby =
{
    local entity item, best;
    local vector point, delta;
    local float seconds, dist, score, bestscore;

    if (!Argus_Advanced () || !deathmatch || coop || self.ar_skill < AR_SKILL_DENIAL
        || self.ar_enemy != world || self.ar_taskgoal != world
        || self.ar_mode != 1 || self.ar_liftwait || self.ar_door != world
        || self.ar_goal.solid != SOLID_TRIGGER || Argus_MajorName (self.ar_goal) != ""
        || time < self.ar_contest_scan || Argus_EffectiveStack () < 95
        || !(self.flags & FL_ONGROUND) || self.ar_feettype != CONTENT_EMPTY)
        return FALSE;
    self.ar_contest_scan = time + 1.1;
    best = world;
    bestscore = 0;
    item = argus_itemchain;
    while (item != world)
    {
        seconds = item.nextthink - time;
        if (item.solid == SOLID_NOT && item.think == SUB_regen
            && seconds >= 3 && seconds <= 5 && Argus_MajorName (item) != ""
            && !(item.ar_failtime && time < item.ar_failtime + 20)
            && !(item.claimed_by != world && item.claimed_by != self
                 && item.claimed_by.health > 0 && time < item.claim_time + 3))
        {
            point = Argus_GoalPoint (item);
            dist = vlen (point - self.origin);
            if (dist >= 55 && dist <= 128)
            {
                score = Argus_ItemValue (item, Argus_ItemClass (item)) - dist * 0.2;
                delta = point + '0 0 24';
                if (score > bestscore && Argus_LiveWalk (self.origin, delta))
                {
                    best = item;
                    bestscore = score;
                }
            }
        }
        item = item.ar_nextitem;
    }
    if (best == world) return FALSE;
    if (!TryClaim (best)) return FALSE;
    if (self.ar_goal.claimed_by == self)
        self.ar_goal.claimed_by = world;
    self.ar_goal = best;
    self.ar_goalstart = time;
    self.ar_localgoal = 0;
    self.ar_planfinal = Argus_ItemClass (best);
    self.ar_planwant = self.ar_planfinal;
    Argus_LogPickupGoal (best);
    Argus_Event ("contest");
    return TRUE;
};
