Here are the features (in no particular order) that I would
like to add:

1.  Internationalization - externalize all user visible
    strings for translation

2.  Localization - Add a language switcher to the UI
    and translate all externalized strings

3.  Validate security of login process

4.  Validate security of communication between agent
    and server

5.  Heartbeat - Add a configurable heartbeat from
    the clients to the server to know when a client
    goes offline

6.  Agent config push - Allow the server to push
    configuration files to the agent

7.  Auto-discovery - If an agent is unconfigured
    as to where its server is, have it try to
    do a network discovery and get a default
    config pushed to it by the server

8.  Hardware inventory - Server can request on
    demand that an agent do a hardware inveentory
    and send that information to the server.  This
    should be done the first time an agent registers
    with the server.

9.  OS Version Capture - Server can request on
    demand that an agent determine the version of
    its operating system and transmit it to the
    server for storage.  This should be done the
    first time an agent registers with the server.

10. Installer for agent - There should be a text-
    based command-line installer for the agent that
    work on MacOS, Windows, Linux and BSD.

11. UI Fallback - When the server goes down, the
    current code just displays a cryptic error 
    message.  There should be some sort of fallback
    message that is displayed saying the server is
    down.

12. Recreate DB - Make sure that all activities
    resulting in data being stored in the server
    db can be asked for by either the server or
    pushed proactively to the server by the client
    so that even if the server's database is
    cleared out it can recreate it point in time
    by making a series of requests to all clients.

13. Scripts - Add the ability to run scripts as
    a specified user.  Scripts can either be
    entered ad-hoc, or be ran from a saved list
    that is stored on the server.  Make this a
    feature that has to be turned on for each
    client and defaults to "off" if not specified.

14. User List - Query the list of users on the
    agent system and provide it to the server
    for storage in the database.

15. Updates - Query the list of available updates
    on the agent and provide it as a list to the
    server for storage in the database.

16. Software Inventory - Query the list of
    installed software and supply it to the
    server for storage in the database.

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

28. Get a proper logo

29. Update the UI
