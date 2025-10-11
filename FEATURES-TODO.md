Here are the features (in no particular order) that I would
like to add:

1.  Installer for agent - There should be a text-
    based command-line installer for the agent that
    work on MacOS, Windows, Linux and BSD.  The
    installer should be able to configure the
    local system to run the agent at startup and
    shut it down cleanly at shutdown.

2.  Broadcast - Allow the server to send a
    broadcast request out to all agents to
    perform actions.  This ensures that the
    server doesn't have to scale message
    sends linearly with the number of
    registered agents.

3.  Firewall Rules - Manage firewall rules
    on the agent machines.

4.  Versioning of the API - We need to make
    sure that older clients can talk to
    newer servers and degrade gracefully.

5.  User Management - Ability to manage
    add/edit/delete users and groups on
    the agent hosts.

6.  We need a MFA mechanism using an
    authenticator app on someone's
    mobile device as well as the ability
    to send a code via email to their
    registered email address.

7.  Have the agent and the server log
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

8.  Add an automation tab between
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

9. Add the ability to issue and
    manage SysManage API keys with
    View/Edit/Admin roles.  They
    should be stored in the vault
    and have an expiration date
    after which they are invalid.
    They key should be able to be
    used to get a JWT token for
    the API so there should be
    an endpoint that is not /api/
    prefixed to get the token
    issued / renewed.

10. A cool AI integration would be
    to have the system pull back
    a diagnostics report from a
    remote agent and do a health
    check on what it sees and
    make recommendations about
    best practices config changes
    for that remote host along
    with the opportunity to have
    sysmanage fix the issues.

11. We should have a settings
    screen that allows the user
    to specify default third-
    party repositories that
    should be auto-applied to
    every host that is approved
    on registration.

12. We need an audit table in the
    database that records every
    action the user takes in terms
    of changing anything in the
    sysmanage database or sending
    messages to a remote agent
    that will result in a change
    being made on the remote
    host.  Also should have an
    audit report added to the
    reports tab.

13. Add the ability to hook up a
    remote host to Graylog for
    log aggregation.
