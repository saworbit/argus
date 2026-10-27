// PRIVATE actual-trigger fixture. Never compiled into production.
float mc_done, mc_checks, mc_ok;
vector mc_origin, mc_target, mc_angles, mc_embed;

void(string label, float ok) MuzzleCombatCheck =
{
    mc_checks = mc_checks + 1;
    if (!ok) mc_ok = 0;
    dprint ("MCFIX check "); dprint (label); dprint (" "); dprint (ftos (ok)); dprint ("\n");
};

void(string label, vector origin, vector target, float yaw, float blocked) MuzzleCombatCase =
{
    local entity saved, foe, b, missile, next;
    local vector oldseat, oldvisible;
    local float gates, owned, shots, before, ok;
    saved = self; oldseat = ar_pf_seat; oldvisible = ar_pf_visible;
    foe = spawn (); foe.classname = "player"; foe.netname = "muzzle_target";
    foe.health = 100; foe.solid = SOLID_NOT; foe.movetype = MOVETYPE_NONE;
    foe.flags = FL_ONGROUND; setorigin (foe, target);
    b = spawn (); ar_pf_seat = origin; ar_pf_visible = target;
    Argus_PerceptionProbe (b, IT_ROCKET_LAUNCHER, 100);
    ar_pf_seat = oldseat; ar_pf_visible = oldvisible;
    self = b; self.ar_skill = 0; self.ar_spring_k = 0;
    self.ar_enemy = foe; self.ar_obsenemy = foe;
    self.angles = '0 0 0'; self.angles_y = yaw;
    self.attack_finished = time - 1; self.ar_react = time - 1;
    self.velocity = '23 7 0'; self.ar_moveyaw = 10000;
    self.ammo_rockets = 2; W_SetCurrentAmmo ();
    mc_actor = b; gates = mc_gates; before = self.ammo_rockets;
    owned = Argus_Combat ();
    shots = 0; missile = nextent (world);
    while (missile != world)
    {
        next = nextent (missile);
        if (missile.owner == b && missile.classname == "rocket")
        { shots = shots + 1; remove (missile); }
        missile = next;
    }
    ok = owned && mc_gates == gates + 1 && self.ar_seen == time;
    ok = ok && self.ar_enemy == foe && self.ar_obsenemy == foe;
    ok = ok && self.weapon == IT_ROCKET_LAUNCHER && !self.ar_tactic;
    ok = ok && self.ar_moveyaw != 10000 && self.ar_moveyaw == mc_motor;
    ok = ok && self.velocity == '23 7 0';
    if (blocked)
    {
        if (self.ammo_rockets != before) ok = 0;
        if (shots != 0) ok = 0;
        if (self.button0) ok = 0;
    }
    else
    {
        if (self.ammo_rockets != before - 1) ok = 0;
        if (shots != 1) ok = 0;
        if (!self.button0) ok = 0;
    }
    dprint ("MCFIX outcome "); dprint (label);
    dprint (" gates "); dprint (ftos (mc_gates - gates));
    dprint (" ammo "); dprint (ftos (before - self.ammo_rockets));
    dprint (" rockets "); dprint (ftos (shots));
    dprint (" motor "); dprint (ftos (self.ar_moveyaw)); dprint ("\n");
    MuzzleCombatCheck (label, ok);
    mc_actor = world; self = saved; remove (b); remove (foe); newmis = world;
};

void() MuzzleCombatFixture =
{
    local entity node, ent, saved, b;
    local vector src, angles, target, shot, backdrop, oldseat, oldvisible;
    local float yaw, side, wall, geometry, distance, fraction, startsolid, allsolid;
    local float before, after, allowed;
    if (mc_done || time < 1) return;
    mc_done = 1; mc_ok = 1;
    dprint ("MCFIX begin dm4\n");
    // Find a world wall in the imperfect direction and a visible target
    // eight degrees beside it. Both premises use independent BSP traces.
    node = find (world, classname, "argus_node");
    while (node != world && !geometry)
    {
        src = node.origin + '0 0 16'; yaw = 0;
        while (yaw < 360 && !geometry)
        {
            angles = '0 0 0'; angles_y = yaw; makevectors (angles);
            traceline (src, src + v_forward * 240, TRUE, world);
            distance = trace_fraction * 240;
            wall = distance > 180 && distance < 230 && !trace_startsolid && !trace_allsolid;
            if (wall)
            {
                mc_embed = src + v_forward * (distance + 8);
                backdrop = node.origin + v_forward * (distance - 32);
                side = -1;
                while (side <= 1 && !geometry)
                {
                    angles_y = yaw + side * 8; makevectors (angles);
                    target = node.origin + v_forward * 320;
                    traceline (node.origin + '0 0 22', target + '0 0 22', TRUE, world);
                    if (trace_fraction == 1 && pointcontents (target) != CONTENT_SOLID)
                    {
                        shot = vectoangles (target + '0 0 12' - (node.origin + '0 0 22'));
                        shot_x = 0 - shot_x; shot_y = yaw; makevectors (shot);
                        traceline (src, src + v_forward * 240, TRUE, world);
                        if (trace_fraction < 1 && !trace_startsolid && !trace_allsolid
                            && pointcontents (mc_embed) == CONTENT_SOLID)
                        {
                            geometry = 1; mc_origin = node.origin;
                            mc_target = target; mc_angles = shot;
                        }
                    }
                    side = side + 2;
                }
            }
            yaw = yaw + 15;
        }
        node = find (node, classname, "argus_node");
    }
    MuzzleCombatCheck ("geometry", geometry);
    if (geometry)
    {
        before = 0; ent = nextent (world);
        while (ent != world) { before = before + 1; ent = nextent (ent); }
        MuzzleCombatCase ("combat_blocked", mc_origin, mc_target, mc_angles_y, 1);
        // Align the same actor/target geometry so the firing lane clears.
        angles = vectoangles (mc_target - mc_origin);
        MuzzleCombatCase ("combat_clear", mc_origin, mc_target, angles_y, 0);
        MuzzleCombatCase ("combat_backdrop", mc_origin, backdrop, mc_angles_y, 0);
        // Observe the embedded contract without firing a projectile.
        saved = self; b = spawn (); self = b;
        self.ar_isbot = 1; self.weapon = IT_ROCKET_LAUNCHER;
        setorigin (self, mc_embed - '0 0 16'); self.v_angle = '0 0 0';
        self.v_angle_y = mc_angles_y; makevectors (self.v_angle);
        traceline (mc_embed, mc_embed + v_forward * 240, TRUE, self);
        fraction = trace_fraction; startsolid = trace_startsolid; allsolid = trace_allsolid;
        allowed = Argus_MuzzleClear (mc_embed + v_forward * 320);
        dprint ("MCFIX embedded fraction "); dprint (ftos (fraction));
        dprint (" startsolid "); dprint (ftos (startsolid));
        dprint (" allsolid "); dprint (ftos (allsolid));
        dprint (" allowed "); dprint (ftos (allowed)); dprint ("\n");
        MuzzleCombatCheck ("embedded_contract", pointcontents (mc_embed) == CONTENT_SOLID
            && startsolid && allowed == (fraction == 1));
        self = saved; remove (b);
        after = 0; ent = nextent (world);
        while (ent != world) { after = after + 1; ent = nextent (ent); }
        MuzzleCombatCheck ("cleanup", before == after);
    }
    dprint ("MCFIX end checks "); dprint (ftos (mc_checks));
    dprint (" ok "); dprint (ftos (mc_ok)); dprint ("\n");
};
