Here are the features (in no particular order) that I would
like to add:

1.  ~~Internationalization - externalize all user visible
    strings for translation~~

2.  ~~Localization - Add a language switcher to the UI
    and translate all externalized strings~~

3.  ~~Validate security of login process~~

4.  ~~Validate security of communication between agent
    and server~~

5.  ~~Heartbeat - Add a configurable heartbeat from
    the clients to the server to know when a client
    goes offline~~

6.  ~~Agent config push - Allow the server to push
    configuration files to the agent~~

7.  ~~Auto-discovery - If an agent is unconfigured
    as to where its server is, have it try to
    do a network discovery and get a default
    config pushed to it by the server~~

8.  ~~Hardware inventory - Server can request on
    demand that an agent do a hardware inveentory
    and send that information to the server.  This
    should be done the first time an agent registers
    with the server.  It should include the CPU
    information (vendor, model, speed, cores, etc.),
    the amount of RAM, the number of hard drives,
    their capacity, type and any hardware info that
    can be obtained (vendor, etc.), the network
    hardware as well.~~

9.  ~~OS Version Capture - Server can request on
    demand that an agent determine the version of
    its operating system and transmit it to the
    server for storage.  This should be done the
    first time an agent registers with the server.~~

10. Installer for agent - There should be a text-
    based command-line installer for the agent that
    work on MacOS, Windows, Linux and BSD.  The
    installer should be able to configure the
    local system to run the agent at startup and
    shut it down cleanly at shutdown.

11. ~~UI Fallback - When the server goes down, the
    current code just displays a cryptic error 
    message.  There should be some sort of fallback
    message that is displayed saying the server is
    down.  Perhaps a popup that says the connection
    to the server has been interrupted, retrying in
    x seconds/minutes that has an exponential back-
    off in terms of the time between retries and
    a maximum number of retries with a final failure
    saying that the server is down and you need to
    contact support.~~

12. ~~Recreate DB - Make sure that all activities
    resulting in data being stored in the server
    db can be asked for by either the server or
    pushed proactively to the server by the client
    so that even if the server's database is
    cleared out it can recreate it point in time
    by making a series of requests to all clients.~~

13. Scripts - Add the ability to run scripts as
    a specified user.  Scripts can either be
    entered ad-hoc, or be ran from a saved list
    that is stored on the server.  Make this a
    feature that has to be turned on for each
    client and defaults to "off" if not specified.

14. ~~User List - Query the list of users on the
    agent system and provide it to the server
    for storage in the database.~~

15. Updates - Query the list of available updates
    on the agent and provide it as a list to the
    server for storage in the database.  The server
    UI needs to alert the user when there are
    updates that need to be applied (perhaps like
    a messages list with an unread count thing
    driven by a bell icon in the toolbar?) and
    then the UI needs to allow the user to tell
    the server to instruct the agent to apply
    those updates.  Then the agent needs to 
    actually kick off the update process and
    communicate back the results of it.

16. ~~Software Inventory - Query the list of
    installed software and supply it to the
    server for storage in the database.  This
    needs to show up in the UI for the hosts
    and perhaps a global "Software Inventory"
    that shows aggregated packages installed
    across the enterprise with version
    differences called out.~~

17. Broadcast - Allow the server to send a
    broadcast request out to all agents to
    perform actions.  This ensures that the
    server doesn't have to scale message
    sends linearly with the number of
    registered agents.

18. Reboot - Allow the server to send a
    request to an agent to reboot itself.

19. Shutdown - Allow the server to send a 
    request to an agent to shut down the
    local machine.

20. Install Software - Allow the server to
    request that an agent install a particular
    piece of software or particular version
    locally.

21. Dashboard - Make the dashboard actually
    work showing (among other things) the
    status of all connected agent machines
    (flagging yellow those machines that
    need some action taken).  Show the
    overall security health of the total
    enterprise.

22. Reboot Check - If a machine needs a
    reboot to allow updates to be installed
    detect this and communicate it back to
    the server where it can be stored.

23. Special Updates - Allow an agent to 
    manage Ubuntu Pro as well as any other
    special paid updates on other platforms.

24. SSH Keys - Manage SSH keys on the agents
    so that they can be pushed out from a
    central location.  Keys must be stored
    in a secure vault - use the open source
    version of the Hashicorp vault to store
    them.

25. Firewall Rules - Manage firewall rules
    on the agent machines.

26. Versioning of the API - We need to make
    sure that older clients can talk to 
    newer servers and degrade gracefully.

27. User Management - Ability to manage
    add/edit/delete users of SysManage
    with email integration.

28. ~~Get a proper logo~~

29. Update the UI

30. ~~Default the language based on browser
    setting detection.~~

31. ~~Add a standard list of locales that we
    support and translate to:  English, 
    Spanish, French, German, Italian, 
    Portuguese, Dutch, Japanese, Simplified
    Chinese, Korean and Russian.~~

32. ~~Move the language dropdown to be on the
    same level as the rest of the toolbar
    buttons but to the left of them.~~

33. Change Logout button to be the user's
    first initial with a circle around it
    that drops down a menu with the users
    name at the top, a profile link that
    takes them to a profile editor and
    a logout link with a separator bar
    between the logout link and the profile
    button.

34. Queue on both server and agent that any
    messages to be sent are written to
    first.  Then, when the message is
    successfully sent, the message is
    removed from the queue.  This queue
    needs to be persistent across any
    possibility of reboot or process kill
    and restart and needs to preserve the
    order in which things are added to it
    with a timestamp in UTC date time
    locale.  This way, if the communication
    is broken between the client and the
    server, messages will be replayed in
    the order they were meant to be sent
    when the communication is restored.
    Use the postgreSQL database (with
    Alembic migrations) for the server's
    queue and just persist the agent's
    queue to the local filesystem.

35. Create a standalone python script on
    both the agent and the server to
    gather diagnostic information that
    can be analyzed to troubleshoot
    configuration or communication
    problems.

36. We need some sort of visual indicator
    of what screen is currently being
    displayed by highlighting the button
    on the main toolbar that was clicked
    by the user to get to the current
    screen.

37. ~~We need to divide up the types of data
    that we store on the server side
    (hardware info, operating system,
    users, etc.) and have separate messages
    that push that info to the server from
    the agent.  That way we aren't over-
    loading any one single communication.
    For example, registering the server
    should just pass the bare minimum of
    information (hostname, IPv4 IPv6) and
    not pass OS name, version, etc.  That
    should come later in separate messages
    after it has successfully registered.
    The server also needs to have the
    ability to ask the agent to push that
    info back if it isn't offering it up.~~

38. Create a github pages hosted static
    website for sysmanage.org domain that
    documents the project, its location,
    and has a "Docs" subsection that
    stores a lot of the stuff we have
    cluttering up the README.md files
    currently.  slim the readme down to
    the basics and direct the reader to
    the url.

39. ~~Groups list - just like the users
    that the agent captures from the
    local system, we need a way to get
    groups and store / display them on
    the server.~~

40. We need a reporting infrastructure
    in the server UI that allows us to
    run reports and then turn them into
    PDF files.

41. We need a password reset capability
    that uses email.  We should confirm
    the user's initial email via an
    email mechanism that won't allow them
    to do anything until they have 
    clicked a link in an email we have
    sent them.  This should also be
    used any time they update the
    email address we have on file.

42. We need a MFA mechanism using an
    authenticator app on someone's
    mobile device as well as the ability
    to send a code via email to their
    registered email address.

43. User image / icon - we need a way
    to allow a user to uplaod an image
    file that will be displayed for
    them in the UI.

44. The agent should be able to run as
    a "regular" user account but have
    limitations imposed on it (can't
    run scripts as root, etc.) and it
    should also be able to run as root
    but that should require "extra"
    configuration effort on the part
    of the person deploying it.

45. For the server and the agent, add
    a debug log verbosity level feature
    to the config file (low / medium /
    high) that controls the amount of
    information logged.

46. Have the agent and the server log
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
