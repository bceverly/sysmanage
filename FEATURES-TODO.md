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

3.  SSH Keys - Manage SSH keys on the agents
    so that they can be pushed out from a
    central location.  Keys must be stored
    in a secure vault - use the open source
    version of the Hashicorp vault to store
    them.

4.  Firewall Rules - Manage firewall rules
    on the agent machines.

5.  Versioning of the API - We need to make
    sure that older clients can talk to
    newer servers and degrade gracefully.

6.  User Management - Ability to manage
    add/edit/delete users and groups on
    the agent hosts.

7.  We need a MFA mechanism using an
    authenticator app on someone's
    mobile device as well as the ability
    to send a code via email to their
    registered email address.

8.  Have the agent and the server log
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

9.  Add an automation tab between
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

10. Add OpenTelemetry support to
    sysmanage and sysmanage-agent
    so that the performance can be
    monitoried in a large-scale
    production environment.

11. Add the ability to deploy an
    antivirus solution that is
    platform approriate to the
    hosts along with centralized
    configuration file management
    of it.

12. It would be cool for sysmanage-
    docs to have a sysmanage.yaml
    and sysmanage-agent.yaml inter-
    active config builder screen
    where you get to choose your
    values / options from a list
    and press a button and it
    generates the yaml in a window
    that you can then copy from.

13. For Ubuntu (and possibly other
    Linux platforms?) we need to
    be able to push a request to
    add a PPA to a remote host
    from a UI on the server.

14. Get rid of all integer primary
    keys in the database and
    replace them with UUIDs.
