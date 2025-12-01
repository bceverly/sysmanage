Here are the features (in no particular order) that I would
like to add:

1.  Broadcast - Allow the server to send a
    broadcast request out to all agents to
    perform actions.  This ensures that the
    server doesn't have to scale message
    sends linearly with the number of
    registered agents.

2.  We need a MFA mechanism using an
    authenticator app on someone's
    mobile device as well as the ability
    to send a code via email to their
    registered email address.

3.  Have the agent and the server log
    their messages to the operating
    system appropriate location but
    fall back to the local logs dir-
    ectory if they don't have access
    to that OS location or if the
    OS directory (in the case of Linux
    macOS or BSD) doesn't exist.  The
    OS location on those platforms
    needs to have a sysmanage or
    sysmanage-agent subdirectory in
    which the logs should be placed.

4.  Add an automation tab between
    updates and scripts in the main
    navbar.  on that tab, have an
    "Updates" subtab that allows you
    to see a list of the hosts and
    their auto update status where
    you get green pills for a package
    manager if they are enabled for
    auto-update for that package
    manager or yellow if they are not
    so enabled.  add an overall
    "Security" pill that is either
    green (enabled) or red (not
    enabled) and put the "Security"
    pill at the start of the list.
    For each of these hosts, have
    a pencil icon on the right that
    is "edit" mode that allows you
    to check on or off each of the
    package managers (plus security)
    that are enabled for that host
    (since some won't support certain
    package managers) with a save
    button to save that row and go
    back to the normal view of the
    list.  don't have a dialog, make
    the checkbox business inline with
    the item in the list.  the entire
    list should be in a data grid
    like the rest of the app's UX.
    Create the necessary alembic
    migrations and do all necessary
    string externalization /
    translation.

5.  A cool AI integration would be
    to have the system pull back
    a diagnostics report from a
    remote agent and do a health
    check on what it sees and
    make recommendations about
    best practices config changes
    for that remote host along
    with the opportunity to have
    sysmanage fix the issues.

6.  Add the ability to deploy
    a Graylog server as well as
    a Grafana server, given a
    host that it should be
    deployed to.  Perhaps do the
    same with database servers
    of various ilks as well?

7.  Based on server roles that
    we detect, recommend firewall
    configuration for that host.

8.  Add support for WSL, hypervisors
    so that an admin can kick off
    the creation / automatic regist-
    ration of virtual machines from
    the sysmanage ui.
