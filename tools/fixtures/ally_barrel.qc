// Private real-hull and stock-weapon regression. No replacement traces,
// perception, attack routines or movement controllers.
float ab_done, ab_checks, ab_failures, ab_yaw;
vector ab_origin, ab_target;

void(entity attacker, float damage) AllyBarrelPain = {};
void(string label, float ok) AllyBarrelCheck =
{
    ab_checks = ab_checks + 1;
    if (!ok) ab_failures = ab_failures + 1;
    dprint ("ABFIX check "); dprint (label); dprint (" ");
    dprint (ftos (ok != 0)); dprint ("\n");
};

void(entity actor, vector pos, string cls) AllyBarrelBody =
{
    actor.classname = cls; actor.health = 1000;
    actor.movetype = MOVETYPE_NONE; actor.solid = SOLID_SLIDEBOX;
    actor.takedamage = DAMAGE_AIM; actor.th_pain = AllyBarrelPain;
    actor.th_die = SUB_Null; actor.flags = FL_ONGROUND;
    setsize (actor, '-16 -16 -24', '16 16 32'); setorigin (actor, pos);
};

void(float kind, string label) AllyBarrelShot =
{
    local entity saved, b, foe, ally;
    local vector oldseat, oldvisible, rayangle, src, where;
    local float aimally, barrelally, owned, ammo, damage, enemyhurt, ok;
    saved = self; oldseat = ar_pf_seat; oldvisible = ar_pf_visible;
    foe = spawn (); ally = spawn (); b = spawn ();
    AllyBarrelBody (foe, ab_target, "monster_fixture");
    // A broad target makes the allowed-shot control independent of pellet
    // spread. The ally retains the actual 32 by 56 player hull.
    setsize (foe, '-32 -32 -24', '32 32 56'); setorigin (foe, ab_target);
    rayangle = '0 0 0'; rayangle_y = ab_yaw;
    if (kind == 2) rayangle_y = ab_yaw + 8;
    makevectors (rayangle); where = ab_origin + v_forward * 256;
    AllyBarrelBody (ally, where, "player");
    ar_pf_seat = ab_origin; ar_pf_visible = ab_target;
    Argus_PerceptionProbe (b, IT_SHOTGUN, 100);
    ar_pf_seat = oldseat; ar_pf_visible = oldvisible;
    self = b; self.netname = "barrel_fixture";
    self.ar_enemy = foe; self.ar_obsenemy = foe; self.ar_teammate = ally;
    self.ar_spring_k = 0; self.ar_aimrate = 0;
    self.ar_targetscan = time + 10; self.ar_targethold = time + 10;
    self.angles = '0 0 0'; self.angles_y = ab_yaw;
    if (kind == 1) self.angles_y = ab_yaw + 8;
    self.attack_finished = time - 1; self.ar_react = time - 1;
    self.ammo_shells = 5; W_SetCurrentAmmo ();
    src = self.origin + '0 0 22';
    traceline (src, ab_target + '0 0 12', FALSE, self);
    aimally = (trace_ent == ally);
    self.v_angle = vectoangles (ab_target + '0 0 12' - src);
    self.v_angle_x = 0 - self.v_angle_x; self.v_angle_y = self.angles_y;
    makevectors (self.v_angle);
    traceline (src + v_forward * 10, src + v_forward * 512, FALSE, self);
    barrelally = (trace_ent == ally);
    owned = Argus_Combat ();
    owned = (owned && self.ar_enemy == foe && self.ar_obsenemy == foe
        && self.ar_seen == time && self.weapon == IT_SHOTGUN);
    ammo = 5 - self.ammo_shells; damage = 1000 - ally.health;
    enemyhurt = 1000 - foe.health;
    ok = (owned && aimally == (kind == 2) && barrelally == (kind == 0));
    if (kind == 0)
        ok = (ok && ammo == 0 && damage == 0 && !self.button0);
    else
        ok = (ok && ammo == 1 && damage == 0 && self.button0);
    if (kind == 1 && enemyhurt <= 0) ok = 0;
    dprint ("ABFIX shot "); dprint (label);
    dprint (" ammo "); dprint (ftos (ammo));
    dprint (" ally_damage "); dprint (ftos (damage));
    dprint (" enemy_damage "); dprint (ftos (enemyhurt));
    dprint (" aim_ally "); dprint (ftos (aimally));
    dprint (" barrel_ally "); dprint (ftos (barrelally));
    dprint (" owned "); dprint (ftos (owned != 0)); dprint ("\n");
    AllyBarrelCheck (label, ok);
    self = saved; remove (b); remove (foe); remove (ally);
};

void(float mode, float lagged, string label) AllyBarrelPrefire =
{
    local entity saved, b, foe, ally, missile, next;
    local vector oldseat, oldvisible, rayangle;
    local float owned, beforeyaw, turn, limit, ammo, rockets, ok;
    saved = self; oldseat = ar_pf_seat; oldvisible = ar_pf_visible;
    coop = mode; deathmatch = !mode;
    foe = spawn (); ally = spawn (); b = spawn ();
    AllyBarrelBody (foe, ab_target, "player");
    if (mode) foe.classname = "monster_fixture";
    foe.invisible_finished = time + 10;
    rayangle = '0 0 0'; rayangle_y = ab_yaw + 8; makevectors (rayangle);
    AllyBarrelBody (ally, ab_origin + v_forward * 256, "player");
    ar_pf_seat = ab_origin; ar_pf_visible = ab_target;
    Argus_PerceptionProbe (b, IT_ROCKET_LAUNCHER, 100);
    ar_pf_seat = oldseat; ar_pf_visible = oldvisible;
    self = b; self.netname = "prefire_fixture";
    self.ar_enemy = foe; self.ar_obsenemy = foe; self.ar_teammate = ally;
    self.ar_lastseen = ab_target; self.ar_seen = time - 1;
    self.ar_obsvelocity = '0 0 0'; self.ar_obsground = 1;
    self.ar_targetscan = time + 10; self.ar_targethold = time + 10;
    self.ar_glimpse = time + 0.5; self.ar_aimrate = 170;
    self.angles = '0 0 0'; self.angles_y = ab_yaw + 8 - lagged * 90;
    beforeyaw = self.angles_y; limit = self.ar_aimrate * frametime;
    self.attack_finished = time - 1; self.ammo_rockets = 5;
    W_SetCurrentAmmo (); owned = Argus_Combat ();
    owned = (owned && self.ar_enemy == foe && self.ar_obsenemy == foe
        && self.ar_seen == time - 1 && self.weapon == IT_ROCKET_LAUNCHER);
    ammo = 5 - self.ammo_rockets; rockets = 0;
    missile = nextent (world);
    while (missile != world)
    {
        next = nextent (missile);
        if (missile.owner == b && missile.classname == "rocket")
        { rockets = rockets + 1; remove (missile); }
        missile = next;
    }
    turn = self.angles_y - beforeyaw;
    while (turn > 180) turn = turn - 360;
    while (turn < -180) turn = turn + 360;
    turn = fabs (turn);
    ok = (owned && turn <= limit + 0.1);
    if (mode || lagged) ok = (ok && ammo == 0 && rockets == 0 && !self.ar_prefired);
    else ok = (ok && ammo == 1 && rockets == 1 && self.ar_prefired);
    dprint ("ABFIX prefire "); dprint (label);
    dprint (" ammo "); dprint (ftos (ammo));
    dprint (" rockets "); dprint (ftos (rockets));
    dprint (" turn "); dprint (ftos (turn));
    dprint (" limit "); dprint (ftos (limit));
    dprint (" owned "); dprint (ftos (owned != 0)); dprint ("\n");
    AllyBarrelCheck (label, ok);
    self = saved; remove (b); remove (foe); remove (ally); newmis = world;
};

void() AllyBarrelFixture =
{
    local entity saved, node, probe, b, ent;
    local vector rayangle, target;
    local float yaw, geometry, oldcoop, olddm, oldteam, before, after;
    if (ab_done || time < 2) return;
    ab_done = 1; saved = self; oldcoop = coop; olddm = deathmatch; oldteam = teamplay;
    dprint ("BHVRPL begin ally_barrel\nABFIX begin dt_ms ");
    dprint (ftos (frametime * 1000)); dprint (" layout 1\n");
    b = argus_bots;
    while (b != world)
    {
        b.ar_pf_solid = b.solid; b.ar_pf_camera = b.cam_active;
        b.ar_pf_damage = b.takedamage; b.solid = SOLID_NOT;
        b.cam_active = 1; b.takedamage = DAMAGE_NO; b = b.ar_chain;
    }
    probe = spawn (); self = probe; self.health = 100;
    node = find (world, classname, "argus_node");
    while (node != world && !geometry)
    {
        setorigin (self, node.origin); yaw = 0;
        while (yaw < 360 && !geometry)
        {
            rayangle = '0 0 0'; rayangle_y = yaw; makevectors (rayangle);
            traceline (node.origin + '0 0 22', node.origin + '0 0 22' + v_forward * 512, TRUE, self);
            if (trace_fraction == 1)
            {
                rayangle_y = yaw + 8; makevectors (rayangle);
                target = node.origin + v_forward * 512;
                traceline (node.origin + '0 0 16', target, TRUE, self);
                if (trace_fraction == 1)
                {
                    traceline (node.origin + '0 0 22', target + '0 0 12', TRUE, self);
                    if (trace_fraction == 1 && !Argus_MoveHazard (yaw + 8, 48))
                    { geometry = 1; ab_origin = node.origin; ab_target = target; ab_yaw = yaw; }
                }
            }
            yaw = yaw + 15;
        }
        node = find (node, classname, "argus_node");
    }
    self = saved; remove (probe);
    AllyBarrelCheck ("geometry", geometry);
    before = 0; ent = nextent (world);
    while (ent != world) { before = before + 1; ent = nextent (ent); }
    if (geometry)
    {
        coop = 1; deathmatch = 0; teamplay = 0;
        AllyBarrelShot (0, "lagged_barrel_hold");
        AllyBarrelShot (1, "aligned_shot");
        AllyBarrelShot (2, "aim_only_ally");
        AllyBarrelPrefire (1, 0, "coop_prefire_hold");
        AllyBarrelPrefire (0, 1, "prefire_turn_hold");
        AllyBarrelPrefire (0, 0, "aligned_prefire");
    }
    after = 0; ent = nextent (world);
    while (ent != world) { after = after + 1; ent = nextent (ent); }
    AllyBarrelCheck ("cleanup", before == after);
    coop = oldcoop; deathmatch = olddm; teamplay = oldteam;
    b = argus_bots;
    while (b != world)
    {
        b.solid = b.ar_pf_solid; b.cam_active = b.ar_pf_camera;
        b.takedamage = b.ar_pf_damage; b = b.ar_chain;
    }
    self = saved;
    dprint ("ABFIX end checks "); dprint (ftos (ab_checks));
    dprint (" failures "); dprint (ftos (ab_failures)); dprint ("\n");
};
