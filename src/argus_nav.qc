/*  argus_nav.qc — runtime navigation for Argus. Pure vanilla QuakeC.

    Nodes are invisible entities spawned by generated per-map files
    (argus_nav_<map>.qc via argus_nav_dispatch.qc). Links are directed:
    walk links appear in both directions; drop, teleporter, jump,
    rocket-jump and lift links in one.

    Routing is breadth-first search over the node graph, sliced across
    server frames to stay far inside the interpreter's runaway budget.
    One search runs at a time. The search walks FORWARD from the bot's
    node; on completion the parent chain is flipped into per-bot
    "next hop" fields, which the bot then follows. Marks use a
    generation counter, so nothing is ever cleared.
*/

float ANQ_POPS = 48;        // node expansions per server frame

.entity an_l0; .entity an_l1; .entity an_l2; .entity an_l3;
.entity an_l4; .entity an_l5; .entity an_l6; .entity an_l7;
.float  an_nlinks;
.float  an_jumpmask;        // bit i set = link slot i needs a jump
.float  an_rjmask;          // bit i set = link slot i needs a rocket jump
.float  an_liftmask;        // bit i set = link slot i rides a plat
.float  an_swimmask;        // bit i set = link slot i swims out of water
.float  an_trainmask;       // bit i set = link slot i rides a func_train
.float  an_doormask;        // bit i set = link slot i crosses a door
.float  an_mark;            // generation stamp
.entity an_par;             // BFS parent (shared; one search at a time)
.entity an_qnext;           // BFS queue linkage
.entity an_next0;           // next hop toward goal, bot slot 0
.entity an_next1;           // next hop toward goal, bot slot 1
.entity an_next2;
.entity an_next3;
.float  an_ng0;             // route generation stamps per slot: a next
.float  an_ng1;             // pointer is only valid for the route that
.float  an_ng2;             // wrote it, or bots follow hops from routes
.float  an_ng3;             // long dead (the cross-map wedge march)
.entity an_cnext;           // shared route cache: next hop toward
.float  an_cgen;            // an_cachegoal; valid iff == an_cachegen

entity  anq_head;
entity  anq_tail;
float   an_gen;
float   an_busy;
entity  an_bot;             // bot whose search is running
entity  an_goalnode;
entity  an_cachegoal;       // goal node of the last completed flood
float   an_cachegen;        // stamps an_cgen along that route
float   an_cachetime;       // freshness: adoptions stop after 10 s

.float  ar_slot;            // on bots: 0..3 (roster cap 4)
.entity ar_node;            // on bots: current waypoint target
.float  ar_pending;         // on bots: waiting for router
.float  ar_routefail;
.float  ar_hopjump;         // on bots: current hop crosses a jump link
.float  ar_hoprj;           // on bots: 1 = rocket-jump armed, 2 = airborne
.float  ar_hoplift;         // on bots: current hop rides a plat
.float  ar_liftwait;        // on bots: parked on the plat this frame
.float  ar_liftstart;       // on bots: when the lift hop began
.float  ar_hopswim;         // on bots: current hop swims out of water
.float  ar_hoptrain;        // on bots: current hop rides a func_train
.float  ar_hopdoor;         // on bots: current hop crosses a door
.float  ar_routegen;        // on bots: increments per completed route
.entity ar_laststart;       // on bots: start node of the last search
.entity ar_lastfailnode;    // on bots: start node of the previous fail
.float  ar_failstreak;      // on bots: consecutive fails from that node
                            // (the trapped-bot detector; see argus.qc
                            // routefail handling for the story)

// ---------------------------------------------------------------- builders

entity(vector org) Argus_NavNode =
{
    local entity n;
    n = spawn ();
    n.classname = "argus_node";
    n.solid = SOLID_NOT;
    n.movetype = MOVETYPE_NONE;
    setorigin (n, org);
    return n;
};

void(entity a, entity b) Argus_NavLink =
{
    if (a.an_nlinks == 0)      a.an_l0 = b;
    else if (a.an_nlinks == 1) a.an_l1 = b;
    else if (a.an_nlinks == 2) a.an_l2 = b;
    else if (a.an_nlinks == 3) a.an_l3 = b;
    else if (a.an_nlinks == 4) a.an_l4 = b;
    else if (a.an_nlinks == 5) a.an_l5 = b;
    else if (a.an_nlinks == 6) a.an_l6 = b;
    else if (a.an_nlinks == 7) a.an_l7 = b;
    else
    {
        // navgen budgets 8 slots per node; a 9th call means the
        // generator and this runtime disagree — say so instead of
        // silently dropping the link (lqdm2 n126 lost its
        // teleporter this way; Shane's fix-now list)
        dprint ("ARGUS navlink overflow\n");
        return;
    }
    a.an_nlinks = a.an_nlinks + 1;
};

// a link the bot must jump across (gap too wide to walk, verified by
// the nav compiler's trajectory check)
void(entity a, entity b) Argus_NavLinkJump =
{
    local float slot;

    slot = a.an_nlinks;
    if (slot > 7)
        return;
    Argus_NavLink (a, b);
    if (slot == 0)      a.an_jumpmask = a.an_jumpmask | 1;
    else if (slot == 1) a.an_jumpmask = a.an_jumpmask | 2;
    else if (slot == 2) a.an_jumpmask = a.an_jumpmask | 4;
    else if (slot == 3) a.an_jumpmask = a.an_jumpmask | 8;
    else if (slot == 4) a.an_jumpmask = a.an_jumpmask | 16;
    else if (slot == 5) a.an_jumpmask = a.an_jumpmask | 32;
    else if (slot == 6) a.an_jumpmask = a.an_jumpmask | 64;
    else                a.an_jumpmask = a.an_jumpmask | 128;
};

// a link the bot must rocket-jump: pay health, ride the blast. The
// router only hands these to bots holding launcher, rockets and the
// health to spare (Argus_BotCanRJ below).
void(entity a, entity b) Argus_NavLinkRocket =
{
    local float slot;

    slot = a.an_nlinks;
    if (slot > 7)
        return;
    Argus_NavLink (a, b);
    if (slot == 0)      a.an_rjmask = a.an_rjmask | 1;
    else if (slot == 1) a.an_rjmask = a.an_rjmask | 2;
    else if (slot == 2) a.an_rjmask = a.an_rjmask | 4;
    else if (slot == 3) a.an_rjmask = a.an_rjmask | 8;
    else if (slot == 4) a.an_rjmask = a.an_rjmask | 16;
    else if (slot == 5) a.an_rjmask = a.an_rjmask | 32;
    else if (slot == 6) a.an_rjmask = a.an_rjmask | 64;
    else                a.an_rjmask = a.an_rjmask | 128;
};

// a link ridden on a func_plat: walk onto the slab at the bottom
// waypoint and stand still; the plat's own trigger does the lifting.
// Bidirectional in spirit but emitted one-way up (coming down is an
// ordinary drop link the generator already makes).
void(entity a, entity b) Argus_NavLinkLift =
{
    local float slot;

    slot = a.an_nlinks;
    if (slot > 7)
        return;
    Argus_NavLink (a, b);
    if (slot == 0)      a.an_liftmask = a.an_liftmask | 1;
    else if (slot == 1) a.an_liftmask = a.an_liftmask | 2;
    else if (slot == 2) a.an_liftmask = a.an_liftmask | 4;
    else if (slot == 3) a.an_liftmask = a.an_liftmask | 8;
    else if (slot == 4) a.an_liftmask = a.an_liftmask | 16;
    else if (slot == 5) a.an_liftmask = a.an_liftmask | 32;
    else if (slot == 6) a.an_liftmask = a.an_liftmask | 64;
    else                a.an_liftmask = a.an_liftmask | 128;
};

// a link ridden on a func_train: wait on the boarding pad until the
// patrolling car docks, board, hold while carried, walk off at the
// far pad. dm2's t4/t5 car at z 304 is the west-to-east upper deck
// bridge (the GL's reachability pocket).
void(entity a, entity b) Argus_NavLinkTrain =
{
    local float slot;

    slot = a.an_nlinks;
    if (slot > 7)
        return;
    Argus_NavLink (a, b);
    if (slot == 0)      a.an_trainmask = a.an_trainmask | 1;
    else if (slot == 1) a.an_trainmask = a.an_trainmask | 2;
    else if (slot == 2) a.an_trainmask = a.an_trainmask | 4;
    else if (slot == 3) a.an_trainmask = a.an_trainmask | 8;
    else if (slot == 4) a.an_trainmask = a.an_trainmask | 16;
    else if (slot == 5) a.an_trainmask = a.an_trainmask | 32;
    else if (slot == 6) a.an_trainmask = a.an_trainmask | 64;
    else                a.an_trainmask = a.an_trainmask | 128;
};

// a walk link whose beeline pierces a func_door AABB. Hull 1 never
// contains door brushes, so the graph treats the doorway as empty
// floor; at runtime the slab is solid until opened. The advance
// sets ar_hopdoor; physics then walks in (touch-open), detours to
// the button (targetname set), or waits for STATE_TOP.
void(entity a, entity b) Argus_NavLinkDoor =
{
    local float slot;

    slot = a.an_nlinks;
    if (slot > 7)
        return;
    Argus_NavLink (a, b);
    if (slot == 0)      a.an_doormask = a.an_doormask | 1;
    else if (slot == 1) a.an_doormask = a.an_doormask | 2;
    else if (slot == 2) a.an_doormask = a.an_doormask | 4;
    else if (slot == 3) a.an_doormask = a.an_doormask | 8;
    else if (slot == 4) a.an_doormask = a.an_doormask | 16;
    else if (slot == 5) a.an_doormask = a.an_doormask | 32;
    else if (slot == 6) a.an_doormask = a.an_doormask | 64;
    else                a.an_doormask = a.an_doormask | 128;
};

// a link that swims out of water: from an underwater waypoint to a
// dry waypoint at the surface lip. The physics waterjump only fires
// on these hops — and navgen only emits them for CONTENTS_WATER, so
// dm4's lava can never see a vault (the regression that killed the
// first waterjump).
void(entity a, entity b) Argus_NavLinkSwim =
{
    local float slot;

    slot = a.an_nlinks;
    if (slot > 7)
        return;
    Argus_NavLink (a, b);
    if (slot == 0)      a.an_swimmask = a.an_swimmask | 1;
    else if (slot == 1) a.an_swimmask = a.an_swimmask | 2;
    else if (slot == 2) a.an_swimmask = a.an_swimmask | 4;
    else if (slot == 3) a.an_swimmask = a.an_swimmask | 8;
    else if (slot == 4) a.an_swimmask = a.an_swimmask | 16;
    else if (slot == 5) a.an_swimmask = a.an_swimmask | 32;
    else if (slot == 6) a.an_swimmask = a.an_swimmask | 64;
    else                a.an_swimmask = a.an_swimmask | 128;
};

entity(entity n, float i) Argus_NavGetLink =
{
    if (i == 0) return n.an_l0;
    if (i == 1) return n.an_l1;
    if (i == 2) return n.an_l2;
    if (i == 3) return n.an_l3;
    if (i == 4) return n.an_l4;
    if (i == 5) return n.an_l5;
    if (i == 6) return n.an_l6;
    return n.an_l7;
};

// nonzero when the link a -> b is rocket-jump-typed
float(entity a, entity b) Argus_LinkIsRocket =
{
    local float i, bit;

    i = 0;
    bit = 1;
    while (i < a.an_nlinks)
    {
        if (Argus_NavGetLink (a, i) == b)
            return (a.an_rjmask & bit);
        i = i + 1;
        bit = bit * 2;
    }
    return 0;
};

// can this bot pay for a rocket jump right now?
float(entity bot) Argus_BotCanRJ =
{
    if (!(bot.items & IT_ROCKET_LAUNCHER))
        return FALSE;
    if (bot.ammo_rockets < 1)
        return FALSE;
    // self-splash runs about 80-110: bare health 70 often kills the
    // jumper after the rocket is already away, so require effective
    // (armour-absorbed) capacity. Bisected 2026-08-18 against the
    // bimodal lava storms and acquitted: those were the trapped-bot
    // routefail shelf contagion, not this bar.
    if (bot.health + bot.armorvalue * bot.armortype < 100)
        return FALSE;
    // quad multiplies the self-splash: a point-blank floor rocket
    // under quad gibs the jumper on launch (Shane's review, fix 2)
    if (bot.super_damage_finished > time)
        return FALSE;
    return TRUE;
};

// nonzero when the link a -> b is swim-typed
float(entity a, entity b) Argus_LinkIsSwim =
{
    local float i, bit;

    i = 0;
    bit = 1;
    while (i < a.an_nlinks)
    {
        if (Argus_NavGetLink (a, i) == b)
            return (a.an_swimmask & bit);
        i = i + 1;
        bit = bit * 2;
    }
    return 0;
};

// nonzero when the link a -> b is train-typed
float(entity a, entity b) Argus_LinkIsTrain =
{
    local float i, bit;

    i = 0;
    bit = 1;
    while (i < a.an_nlinks)
    {
        if (Argus_NavGetLink (a, i) == b)
            return (a.an_trainmask & bit);
        i = i + 1;
        bit = bit * 2;
    }
    return 0;
};

// nonzero when the link a -> b is door-typed
float(entity a, entity b) Argus_LinkIsDoor =
{
    local float i, bit;

    i = 0;
    bit = 1;
    while (i < a.an_nlinks)
    {
        if (Argus_NavGetLink (a, i) == b)
            return (a.an_doormask & bit);
        i = i + 1;
        bit = bit * 2;
    }
    return 0;
};

// nonzero when the link a -> b is lift-typed
float(entity a, entity b) Argus_LinkIsLift =
{
    local float i, bit;

    i = 0;
    bit = 1;
    while (i < a.an_nlinks)
    {
        if (Argus_NavGetLink (a, i) == b)
            return (a.an_liftmask & bit);
        i = i + 1;
        bit = bit * 2;
    }
    return 0;
};

// nonzero when the link a -> b is jump-typed
float(entity a, entity b) Argus_LinkIsJump =
{
    local float i, bit;

    i = 0;
    bit = 1;
    while (i < a.an_nlinks)
    {
        if (Argus_NavGetLink (a, i) == b)
            return (a.an_jumpmask & bit);
        i = i + 1;
        bit = bit * 2;
    }
    return 0;
};

void(entity n, entity bot, entity val) Argus_SetNext =
{
    if (bot.ar_slot == 0)      { n.an_next0 = val; n.an_ng0 = bot.ar_routegen; }
    else if (bot.ar_slot == 1) { n.an_next1 = val; n.an_ng1 = bot.ar_routegen; }
    else if (bot.ar_slot == 2) { n.an_next2 = val; n.an_ng2 = bot.ar_routegen; }
    else                       { n.an_next3 = val; n.an_ng3 = bot.ar_routegen; }
};

entity(entity n, entity bot) Argus_GetNext =
{
    if (bot.ar_slot == 0)
    {
        if (n.an_ng0 != bot.ar_routegen) return world;
        return n.an_next0;
    }
    if (bot.ar_slot == 1)
    {
        if (n.an_ng1 != bot.ar_routegen) return world;
        return n.an_next1;
    }
    if (bot.ar_slot == 2)
    {
        if (n.an_ng2 != bot.ar_routegen) return world;
        return n.an_next2;
    }
    if (n.an_ng3 != bot.ar_routegen) return world;
    return n.an_next3;
};

// ---------------------------------------------------------------- queries

entity(vector p) Argus_NearestNode =
{
    local entity n, best, bestv;
    local vector d, eye;
    local float dist, bd, bdv;

    best = world;
    bestv = world;
    bd = 999999;
    bdv = 999999;
    eye = p + '0 0 22';
    n = find (world, classname, "argus_node");
    while (n != world)
    {
        d = n.origin - p;
        d_z = d_z * 2;
        dist = vlen (d);
        if (dist < bd)
        {
            bd = dist;
            best = n;
        }
        if (dist < bdv)
        {
            traceline (eye, n.origin + '0 0 8', TRUE, self);
            if (trace_fraction == 1)
            {
                bdv = dist;
                bestv = n;
            }
        }
        n = find (n, classname, "argus_node");
    }
    // a node we can actually see beats a wall neighbour, but only
    // within reason: unbounded, this preference handed bots "nearest"
    // nodes 900u across the map whenever the true neighbours failed
    // the eye trace (origins sit near floor level and ledge lips clip
    // them), and the bot then beelined the whole way into a wall
    if (bestv != world && bdv <= bd * 2 + 100)
        return bestv;
    return best;
};

// ---------------------------------------------------------------- search

float(entity bot, entity startnode, entity goalnode) Argus_Route_Start =
{
    if (an_busy)
        return FALSE;
    if (startnode == world || goalnode == world)
        return FALSE;

    an_busy = 1;
    an_bot = bot;
    an_goalnode = goalnode;
    an_gen = an_gen + 1;

    startnode.an_mark = an_gen;
    startnode.an_par = world;
    startnode.an_qnext = world;
    anq_head = startnode;
    anq_tail = startnode;
    return TRUE;
};

void() Argus_Route_Finish =
{
    local entity cur, prev;
    local float hops;

    if (an_bot.health <= 0)
    {
        an_busy = 0;            // the bot died while we searched
        return;
    }

    // new route, new generation: every next pointer written below is
    // stamped with it, and Argus_GetNext ignores stamps from any other
    an_bot.ar_routegen = an_bot.ar_routegen + 1;

    // flip parent chain (goal -> start) into next-hop fields (start -> goal)
    // - and into the SHARED route cache (Omicron review: their
    // waypoints cached distances to popular goals so routing became a
    // free greedy descent for every bot after the first). One cached
    // route at a time is enough here: the circuit economy converges
    // the roster on the same few majors, so the next bot wanting this
    // goal from anywhere on this path adopts it without a search.
    an_cachegen = an_cachegen + 1;
    an_cachegoal = an_goalnode;
    an_cachetime = time;
    cur = an_goalnode;
    hops = 0;
    Argus_SetNext (cur, an_bot, world);         // route ends at goal node
    cur.an_cnext = world;
    cur.an_cgen = an_cachegen;
    prev = cur.an_par;
    while (prev != world)
    {
        Argus_SetNext (prev, an_bot, cur);
        prev.an_cnext = cur;
        prev.an_cgen = an_cachegen;
        cur = prev;
        prev = cur.an_par;
        hops = hops + 1;
        if (hops > 250)                          // safety
            break;
    }

    an_bot.ar_pending = 0;
    an_bot.ar_failstreak = 0;                    // routes work from here
    an_bot.ar_node = cur;                        // = start node; AI flips to mode 2
    an_bot.ar_hopjump = 0;                       // reaching the start node is a walk
    an_bot.ar_hoprj = 0;
    an_bot.ar_hoplift = 0;
    an_bot.ar_hopswim = 0;
    an_bot.ar_hoptrain = 0;
    an_bot.ar_hopdoor = 0;

    dprint ("ARGEVT ");
    dprint (an_bot.netname);
    dprint (" route ");
    dprint (ftos(hops));
    dprint (" start ");
    dprint (vtos(cur.origin));
    dprint (" goal ");
    dprint (vtos(an_goalnode.origin));
    dprint ("\n");
    an_busy = 0;
};

// adopt the shared cached route: when the last completed flood served
// the SAME goal node and this bot's start sits on that path (its
// cache stamp is current), copy the chain into the bot's own slots -
// zero search frames, no an_busy contention. The walk re-checks the
// rocket toll per hop, because the original searcher's equipment
// authorised those links, not ours; any unpayable hop aborts the
// adoption and the bot falls back to a normal search.
float(entity bot, entity startnode, entity goalnode) Argus_Route_Adopt =
{
    local entity cur, nx;
    local float hops;

    if (goalnode == world || startnode == world)
        return FALSE;
    if (an_cachegoal != goalnode || time > an_cachetime + 10)
        return FALSE;
    if (startnode.an_cgen != an_cachegen)
        return FALSE;

    // verify the chain first: tolls payable, length sane
    cur = startnode;
    hops = 0;
    while (cur != goalnode)
    {
        if (cur.an_cgen != an_cachegen)
            return FALSE;               // stale splice mid-path
        nx = cur.an_cnext;
        if (nx == world)
            return FALSE;
        if (Argus_LinkIsRocket (cur, nx) && !Argus_BotCanRJ (bot))
            return FALSE;
        cur = nx;
        hops = hops + 1;
        if (hops > 250)
            return FALSE;
    }

    bot.ar_routegen = bot.ar_routegen + 1;
    cur = startnode;
    while (cur != goalnode)
    {
        Argus_SetNext (cur, bot, cur.an_cnext);
        cur = cur.an_cnext;
    }
    Argus_SetNext (goalnode, bot, world);

    bot.ar_pending = 0;
    bot.ar_failstreak = 0;
    bot.ar_node = startnode;
    bot.ar_hopjump = 0;
    bot.ar_hoprj = 0;
    bot.ar_hoplift = 0;
    bot.ar_hopswim = 0;
    bot.ar_hoptrain = 0;
    bot.ar_hopdoor = 0;

    // plain console marker, deliberately NOT an ARGEVT: adoption
    // emits the same route event as a search, and this line is how
    // a tape proves the cache actually fired (grep "routecache")
    dprint ("ARGUS routecache adopt\n");
    dprint ("ARGEVT ");
    dprint (bot.netname);
    dprint (" route ");
    dprint (ftos (hops));
    dprint (" start ");
    dprint (vtos (startnode.origin));
    dprint (" goal ");
    dprint (vtos (goalnode.origin));
    dprint ("\n");
    return TRUE;
};

void() Argus_Route_Fail =
{
    an_bot.ar_pending = 0;
    an_bot.ar_routefail = 1;
    dprint ("ARGEVT ");
    dprint (an_bot.netname);
    dprint (" routefail\n");
    an_busy = 0;
};

void() Argus_Nav_Frame =
{
    local entity cur, nb;
    local float pops, i;

    if (!an_busy)
        return;

    pops = 0;
    while (pops < ANQ_POPS)
    {
        if (anq_head == world)
        {
            Argus_Route_Fail ();
            return;
        }
        cur = anq_head;
        anq_head = cur.an_qnext;
        if (anq_head == world)
            anq_tail = world;

        if (cur == an_goalnode)
        {
            Argus_Route_Finish ();
            return;
        }

        i = 0;
        while (i < cur.an_nlinks)
        {
            nb = Argus_NavGetLink (cur, i);
            if (nb.an_mark != an_gen)
            {
                // rocket-jump links exist only for bots equipped to
                // pay the toll right now
                if (!Argus_LinkIsRocket (cur, nb) || Argus_BotCanRJ (an_bot))
                {
                    nb.an_mark = an_gen;
                    nb.an_par = cur;
                    nb.an_qnext = world;
                    if (anq_tail == world)
                        anq_head = nb;
                    else
                        anq_tail.an_qnext = nb;
                    anq_tail = nb;
                }
            }
            i = i + 1;
        }
        pops = pops + 1;
    }
};
