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

3.  Install Software - Allow the server to
    request that an agent install a particular
    piece of software or particular version
    locally.

4.  SSH Keys - Manage SSH keys on the agents
    so that they can be pushed out from a
    central location.  Keys must be stored
    in a secure vault - use the open source
    version of the Hashicorp vault to store
    them.

5.  Firewall Rules - Manage firewall rules
    on the agent machines.

6.  Versioning of the API - We need to make
    sure that older clients can talk to
    newer servers and degrade gracefully.

7.  User Management - Ability to manage
    add/edit/delete users and groups on
    the agent hosts.

8.  Create a github pages hosted static
    website for sysmanage.org domain that
    documents the project, its location,
    and has a "Docs" subsection that
    stores a lot of the stuff we have
    cluttering up the README.md files
    currently.  slim the readme down to
    the basics and direct the reader to
    the url.

9.  We need a reporting infrastructure
    in the server UI that allows us to
    run reports and then turn them into
    PDF files.  The first report will
    be a host status report that lists
    all of the hosts with the OS name,
    version, number of needed security
    updates and number of needed system
    updates as well as whether a reboot
    is needed.

10. We need a MFA mechanism using an
    authenticator app on someone's
    mobile device as well as the ability
    to send a code via email to their
    registered email address.

11. Have the agent and the server log
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

12. OS version upgrades - we need a
    feature that will let us detect
    that there is a new operating
    system major version out there
    and show that fact to the user.
    We then need to, if one is
    available, see if the user wants
    to upgrade.  If so, then we need
    to apply the upgrade.  Include
    syspatch on OpenBSD.

13. Add an automation tab between
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

14. Master Ubuntu Pro Key - Add a
    settings sub-tab for Ubuntu Pro
    where you can save a master key
    that can be used to enroll a
    remote host into pro using the
    stored key.  Obviously we will
    need to add an alembic database
    migration script to modify the
    schema.  For the existing
    dialog for enrolling a remote
    host into pro, if there is a
    master key, pre-fill the dialog
    entry field with it