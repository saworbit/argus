// Learn directed links from traversal on maps without an authored graph.
float AL_WALK = 0;
float AL_JUMP = 1;
float AL_DROP = 2;
float AL_PORTAL = 3;
float AL_PLAT = 4;
float AL_TRAIN = 5;
float AL_DOOR = 6;
float AL_SWIM = 7;

entity al_nodes;
float al_count;
float al_peak_edicts;
.entity al_next;
.entity al_seat;
.entity al_mover;
.float al_sample;
.float al_air;
.float al_jump;
.float al_wet;
.float al_door_until;
.float al_item_scan;
.float al_swim_until;
.vector al_swim_wish;

// When exploration reaches a pool with no route, retain the clearest
// channel long enough to get out of a wall pocket. The swim physics still
// owns depth, breathing and the vault across any bank found.
vector(vector wish) Argus_LiveSwimWish =
{
    local float i, base, angle, score, bestscore, water;
    local vector direction, chosen, start, target;

    if (time < self.al_swim_until) return self.al_swim_wish;
    self.al_swim_until = time + 0.55;
    chosen = wish;
    bestscore = -1;
    base = vectoyaw (wish);
    start = self.origin + '0 0 8';
    i = 0;
    while (i < 8)
    {
        angle = base + i * 45;
        makevectors (angle * '0 1 0');
        direction = v_forward;
        target = start + direction * 105;
        traceline (start, target, TRUE, self);
        score = trace_fraction * 105;
        if (!trace_startsolid && score > 12)
        {
            water = pointcontents (trace_endpos - direction * 6);
            if (water == CONTENT_LAVA || water == CONTENT_SLIME)
                score = -1;
            else if (trace_fraction == 1 && water == CONTENT_EMPTY)
            {
                traceline (target, target - '0 0 40', TRUE, self);
                if (trace_fraction < 1 && trace_plane_normal_z > 0.65
                    && pointcontents (trace_endpos + '0 0 2') == CONTENT_EMPTY)
                    score = score + 28;
            }
            if (score >= 0) score = score + direction * wish * 14;
            if (score > bestscore)
            {
                bestscore = score;
                chosen = direction;
            }
        }
        i = i + 1;
    }
    self.al_swim_wish = chosen;
    return chosen;
};

// Check clearance at the centre and both shoulders. Check support separately,
// because a chest ray over a gap is a valid shot and an invalid walk.
float(vector from, vector to) Argus_LiveWalk =
{
    local vector side, ray;
    local float distance, step, contents;

    ray = to - from;
    ray_z = 0;
    distance = vlen (ray);
    if (distance > 136 || fabs (to_z - from_z) > 22)
        return FALSE;
    side = normalize (ray);
    side = side_y * '-14 0 0' + side_x * '0 14 0';
    traceline (from + '0 0 8', to + '0 0 8', TRUE, self);
    if (trace_fraction < 1 || trace_startsolid) return FALSE;
    traceline (from + side, to + side, TRUE, self);
    if (trace_fraction < 1 || trace_startsolid) return FALSE;
    traceline (from - side, to - side, TRUE, self);
    if (trace_fraction < 1 || trace_startsolid) return FALSE;
    step = 16;
    while (step <= distance + 12 && distance > 0)
    {
        if (step > distance) step = distance;
        ray = from + (to - from) * (step / distance);
        traceline (ray + '0 0 8', ray - '0 0 48', TRUE, self);
        if (trace_fraction == 1 || trace_startsolid) return FALSE;
        contents = pointcontents (trace_endpos + '0 0 2');
        if (contents != CONTENT_EMPTY) return FALSE;
        step = step + 16;
    }
    return TRUE;
};

entity(vector point, float radius) Argus_LiveNear =
{
    local entity node, best;
    local float dist;

    node = al_nodes;
    best = world;
    while (node != world)
    {
        dist = vlen (node.origin - point);
        if (dist < radius && fabs (node.origin_z - point_z) < 19)
        {
            traceline (point, node.origin, TRUE, self);
            if (trace_fraction == 1 && !trace_startsolid)
            {
                best = node;
                radius = dist;
            }
        }
        node = node.al_next;
    }
    return best;
};

entity(vector point) Argus_LiveSeat =
{
    local entity node;
    local float count;

    node = Argus_LiveNear (point, 66);
    if (node != world || al_count >= 104 || an_busy)
        return node;
    // Leave capacity for projectiles, players, body queues and map logic.
    count = 1;
    node = nextent (world);
    while (node != world && count < 456)
    {
        count = count + 1;
        node = nextent (node);
    }
    if (count >= 456) return world;
    node = Argus_NavNode (point);
    node.al_next = al_nodes;
    al_nodes = node;
    al_count = al_count + 1;
    if (count + 1 > al_peak_edicts) al_peak_edicts = count + 1;
    if (al_count == 1 || al_count == 104 || al_count == floor (al_count / 16) * 16)
    {
        dprint ("ARGUS live graph nodes "); dprint (ftos (al_count));
        dprint (" allocated_edicts "); dprint (ftos (al_peak_edicts)); dprint ("\n");
    }
    return node;
};

entity(entity item) Argus_LiveItemSeat =
{
    local vector point;
    local entity seat;

    if (time < item.al_item_scan) return world;
    item.al_item_scan = time + 1.0;
    point = Argus_GoalPoint (item);
    seat = Argus_LiveNear (point + '0 0 22', 90);
    if (seat != world && Argus_LiveWalk (seat.origin, point + '0 0 22'))
        return seat;
    seat = Argus_LiveNear (point, 72);
    if (seat != world && Argus_LiveWalk (seat.origin, point))
        return seat;
    return world;
};

void(entity from, entity to, float kind) Argus_LiveLink =
{
    local float bit;

    if (from == world || to == world || from == to || from.an_nlinks >= 8) return;
    if (Argus_NavGetLinkBit (from, to)) return;
    if (kind == AL_JUMP) Argus_NavLinkJump (from, to, 0);
    else if (kind == AL_PLAT) Argus_NavLinkLift (from, to);
    else if (kind == AL_TRAIN) Argus_NavLinkTrain (from, to);
    else if (kind == AL_DOOR) Argus_NavLinkDoor (from, to);
    else if (kind == AL_SWIM) Argus_NavLinkSwim (from, to);
    else Argus_NavLink (from, to);
    bit = Argus_NavGetLinkBit (from, to);
    if (kind == AL_DROP) from.al_dropmask = from.al_dropmask | bit;
    if (kind == AL_PORTAL)
    {
        from.an_telemask = from.an_telemask | bit;
        from.an_telecost = 224;
    }
    if (!from.al_linkLogged)
    {
        from.al_linkLogged = TRUE;
        dprint ("ARGUS live link "); dprint (ftos (kind)); dprint (" ");
        dprint (vtos (from.origin)); dprint (" -> ");
        dprint (vtos (to.origin)); dprint ("\n");
    }
};

void() Argus_LiveNavReset =
{
    self.al_seat = world;
    self.al_mover = world;
    self.al_sample = 0;
    self.al_air = 0;
    self.al_jump = 0;
    self.al_door_until = 0;
    self.al_wet = 0;
    self.al_swim_until = 0;
};

void(entity actor) Argus_LiveNavDoor =
{
    if (argus_live_nav && actor.classname == "player")
        actor.al_door_until = time + 1.6;
};

void(entity rider, entity gate, vector entry) Argus_LiveNavWarp =
{
    local entity from, to, saved;

    if (!argus_live_nav || rider.classname != "player" || rider.health <= 0)
        return;
    if (rider.ar_node != world && rider.ar_node.al_gate == gate)
        rider.ar_node = rider.ar_node.al_exit;
    saved = self;
    self = rider;
    Argus_LiveNavReset ();
    if (!an_busy && gate.targetname == string_null)
    {
        from = Argus_LiveSeat (entry);
        to = Argus_LiveSeat (rider.origin);
        if (from != world && to != world && from != to && from.al_gate == world)
        {
            Argus_LiveLink (from, to, AL_PORTAL);
            if (Argus_NavGetLinkBit (from, to) & from.an_telemask)
            {
                from.al_gate = gate;
                from.al_exit = to;
            }
        }
        self.al_seat = to;
    }
    self = saved;
};

void() Argus_LiveNavSample =
{
    local entity from, to, support;
    local float contents, distance, kind;
    local vector feet, delta;

    if (!argus_live_nav || self.health <= 0 || self.cam_active || self.ar_taskgoal != world)
        return;
    if (self.teleport_time > time) return;
    feet = self.origin + '0 0 -23';
    contents = pointcontents (feet);
    if (contents < CONTENT_WATER)
    {
        Argus_LiveNavReset ();
        return;
    }
    if (!(self.flags & FL_ONGROUND) && contents != CONTENT_WATER)
    {
        self.al_air = TRUE;
        if (self.velocity_z > 120) self.al_jump = TRUE;
        return;
    }
    support = self.groundentity;
    if (self.flags & FL_ONGROUND)
        if (support.classname == "plat" || support.classname == "train")
        {
            if (self.al_seat != world) self.al_mover = support;
            return;
        }
    if (an_busy || time < self.al_sample) return;
    self.al_sample = time + 0.21;
    from = self.al_seat;
    if (from != world && vlen (self.origin - from.origin) < 56)
    {
        self.al_air = 0;
        self.al_jump = 0;
        self.al_mover = world;
        return;
    }
    to = Argus_LiveSeat (self.origin);
    if (to == world || from == to) return;
    if (from != world)
    {
        delta = to.origin - from.origin;
        distance = vlen (delta);
        kind = -1;
        if (self.al_mover != world && distance < 720)
        {
            kind = AL_PLAT;
            if (self.al_mover.classname == "train") kind = AL_TRAIN;
        }
        else if (self.al_wet && contents != CONTENT_WATER && distance < 155)
            kind = AL_SWIM;
        else if (contents == CONTENT_WATER && distance < 135)
        {
            traceline (from.origin, to.origin, TRUE, self);
            if (trace_fraction == 1) kind = AL_WALK;
        }
        else if (Argus_LiveWalk (from.origin, to.origin))
            kind = AL_WALK;
        else if (!self.al_air && time < self.al_door_until && distance < 136
                 && fabs (delta_z) < 24)
            kind = AL_DOOR;
        else if (self.al_air && delta_z < -22 && delta_z >= -176 && distance < 220)
            kind = AL_DROP;
        else if (self.al_jump && delta_z > -30 && delta_z < 44 && distance < 180)
            kind = AL_JUMP;
        if (kind >= 0) Argus_LiveLink (from, to, kind);
        if (kind == AL_WALK && contents != CONTENT_WATER
            && Argus_LiveWalk (to.origin, from.origin))
            Argus_LiveLink (to, from, AL_WALK);
    }
    self.al_seat = to;
    self.al_air = 0;
    self.al_jump = 0;
    self.al_mover = world;
    self.al_wet = (contents == CONTENT_WATER);
};

void() Argus_LiveNavReject =
{
    local entity from;
    local float bit;

    if (!argus_live_nav || self.ar_node == world) return;
    from = self.al_seat;
    if (from == world || from == self.ar_node) from = self.ar_laststart;
    if (from == world) return;
    bit = Argus_NavGetLinkBit (from, self.ar_node);
    if (!bit) return;
    if (from.al_badbit != bit || time > from.al_baduntil + 20)
        from.al_failures = 0;
    from.al_badbit = bit;
    if (from.al_failures < 4) from.al_failures = from.al_failures + 1;
    from.al_baduntil = time + 5 * from.al_failures;
};
