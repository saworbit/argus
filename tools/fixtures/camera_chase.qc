// Component check with real BSP brush collision. The fixture constructs a
// pinched chase, then observes the unchanged production camera function.
float cc_done, cc_trials, cc_blocked;

void(float fraction) CameraChaseCandidate =
{
    cc_trials = cc_trials + 1;
    if (fraction < 1) cc_blocked = cc_blocked + 1;
};

void() CameraChaseFixture =
{
    local entity actor, client, brush, wall, saved;
    local vector center, seat, oldpos, expected, observed_forward, observed_right;
    local float angle, blend, basis_error, position_error, radius, span;
    if (cc_done || time < 2) return;
    cc_done = 1;
    actor = spawn (); client = spawn ();
    actor.classname = "camera_fixture_target"; actor.health = 100;
    actor.solid = SOLID_NOT; actor.movetype = MOVETYPE_NONE;
    setorigin (actor, '625 1425 24');
    saved = self; self = actor; brush = Argus_NearestMover (320); self = saved;
    if (brush.classname != "plat") error ("CAMFIX missing brush platform");
    seat = '625 1425 344'; setorigin (actor, seat);
    center = (brush.mins + brush.maxs) * 0.5;
    angle = 0;
    while (angle < 360)
    {
        makevectors ('0 0 0' + angle * '0 1 0');
        // Put the near face 24u down each probe ray using the real brush
        // dimensions. Do not assume the platform is a square.
        radius = 99999;
        if (fabs (v_forward_x) > 0.01)
            radius = (brush.maxs_x - brush.mins_x) * 0.5 / fabs (v_forward_x);
        if (fabs (v_forward_y) > 0.01)
        {
            span = (brush.maxs_y - brush.mins_y) * 0.5 / fabs (v_forward_y);
            if (span < radius) radius = span;
        }
        wall = spawn (); wall.movetype = MOVETYPE_PUSH; wall.solid = SOLID_BSP;
        setmodel (wall, brush.model);
        setorigin (wall, seat + '0 0 32' + v_forward * (radius + 24) - center);
        angle = angle + 45;
    }
    client.classname = "labcamera"; client.cam_active = 1;
    client.cam_dist = 135; client.cam_smooth_dist = 16;
    client.cam_angles = '8 0 0'; client.cam_pinch_time = time - 1;
    oldpos = seat + '-100 0 36'; client.cam_pos = oldpos;
    dprint ("BHVRPL begin camera_chase\nCAMFIX begin dt_ms ");
    dprint (ftos (frametime * 1000)); dprint (" layout 1\n");
    ArgusCam_SmartChase (client, actor);
    observed_forward = v_forward; observed_right = v_right;
    // Oracle uses the camera's final angles, independent of whichever probe
    // last touched the shared makevectors globals inside production code.
    makevectors (client.cam_angles);
    basis_error = vlen (observed_forward - v_forward) + vlen (observed_right - v_right);
    expected = seat + '0 0 22' - v_forward * client.cam_smooth_dist;
    blend = frametime * 14; if (blend > 1) blend = 1;
    expected = oldpos + (expected - oldpos) * blend;
    position_error = vlen (client.cam_pos - expected);
    dprint ("CAMFIX result candidates "); dprint (ftos (cc_trials));
    dprint (" blocked "); dprint (ftos (cc_blocked));
    dprint (" basis_error "); dprint (ftos (basis_error));
    dprint (" position_error "); dprint (ftos (position_error));
    dprint (" distance "); dprint (ftos (client.cam_smooth_dist));
    dprint (" position "); dprint (vtos (client.cam_pos));
    dprint (" expected "); dprint (vtos (expected)); dprint ("\n");
};
